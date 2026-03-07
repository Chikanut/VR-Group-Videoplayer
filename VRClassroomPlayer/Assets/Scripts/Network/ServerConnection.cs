using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// WebSocket client that connects to the instructor server.
    /// Handles registration, heartbeat status updates, and command reception.
    /// Auto-discovers the server on the local network if not configured.
    /// </summary>
    public class ServerConnection : MonoBehaviour
    {
        [SerializeField] private StatusReporter statusReporter;
        [SerializeField] private VideoPlayerController videoPlayer;
        [SerializeField] private ViewModeManager viewModeManager;
        [SerializeField] private OrientationManager orientationManager;

        private const float HeartbeatInterval = 5f;
        private const float ReconnectDelay = 3f;
        private const float DiscoveryRetryDelay = 10f;
        private const int ReceiveBufferSize = 8192;
        private const int ServerPort = 8000;
        private const int DiscoveryConcurrency = 30;
        private const int DiscoveryTimeoutMs = 2000;

        private ClientWebSocket _ws;
        private CancellationTokenSource _cts;
        private readonly ConcurrentQueue<Action> _mainThreadQueue = new ConcurrentQueue<Action>();
        private float _lastHeartbeatTime;
        private bool _connected;
        private string _serverUrl;
        private string _deviceId;
        private bool _discovering;
        private int _connectionFailures;

        private void Start()
        {
            _deviceId = StatusReporter.GetAndroidId();
            _serverUrl = BuildServerUrl();

            if (string.IsNullOrEmpty(_serverUrl))
            {
                Debug.Log("[ServerConnection] No instructor_ip configured. Will auto-discover server on network.");
            }

            _cts = new CancellationTokenSource();
            StartConnectionLoop();
        }

        private void Update()
        {
            while (_mainThreadQueue.TryDequeue(out var action))
            {
                try
                {
                    action.Invoke();
                }
                catch (Exception e)
                {
                    Debug.LogError($"[ServerConnection] Main thread action error: {e}");
                }
            }

            if (_connected && Time.time - _lastHeartbeatTime >= HeartbeatInterval)
            {
                _lastHeartbeatTime = Time.time;
                SendHeartbeat();
            }
        }

        private void OnApplicationFocus(bool hasFocus)
        {
            if (hasFocus && !_connected)
            {
                Debug.Log("[ServerConnection] App focused, attempting immediate reconnect");
                _serverUrl = BuildServerUrl();
                CloseWebSocket();
                StartConnectionLoop();
            }
        }

        private void OnDestroy()
        {
            _cts?.Cancel();
            CloseWebSocket();
        }

        private string BuildServerUrl()
        {
            string server = PlayerPrefs.GetString("instructor_ip", string.Empty);
            if (string.IsNullOrEmpty(server)) return null;

            if (server.Contains(":"))
                return $"ws://{server}/ws/device";
            else
                return $"ws://{server}:{ServerPort}/ws/device";
        }

        private async void StartConnectionLoop()
        {
            var token = _cts.Token;

            while (!token.IsCancellationRequested)
            {
                _serverUrl = BuildServerUrl();

                // If no server configured, try to discover it
                if (string.IsNullOrEmpty(_serverUrl))
                {
                    if (!_discovering)
                    {
                        _discovering = true;
                        string discovered = await DiscoverServer(token);
                        _discovering = false;

                        if (!string.IsNullOrEmpty(discovered))
                        {
                            _mainThreadQueue.Enqueue(() =>
                            {
                                PlayerPrefs.SetString("instructor_ip", discovered);
                                PlayerPrefs.Save();
                                Debug.Log($"[ServerConnection] Server discovered and saved: {discovered}");
                            });
                            _serverUrl = $"ws://{discovered}/ws/device";
                            _connectionFailures = 0;
                        }
                        else
                        {
                            Debug.Log($"[ServerConnection] Server not found on network. Retrying in {DiscoveryRetryDelay}s...");
                            try
                            {
                                await Task.Delay(TimeSpan.FromSeconds(DiscoveryRetryDelay), token).ConfigureAwait(false);
                            }
                            catch (OperationCanceledException) { break; }
                            continue;
                        }
                    }
                    else
                    {
                        await Task.Delay(TimeSpan.FromSeconds(ReconnectDelay), token).ConfigureAwait(false);
                        continue;
                    }
                }

                try
                {
                    await ConnectAndRun(token).ConfigureAwait(false);
                    // If we get here, WS closed normally
                    _connectionFailures = 0;
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[ServerConnection] Connection error: {e.Message}");
                    _connectionFailures++;

                    // After 3 consecutive failures, clear saved IP and re-discover
                    if (_connectionFailures >= 3)
                    {
                        Debug.Log("[ServerConnection] Too many failures, clearing saved server IP to re-discover");
                        _mainThreadQueue.Enqueue(() =>
                        {
                            PlayerPrefs.SetString("instructor_ip", string.Empty);
                            PlayerPrefs.Save();
                        });
                        _connectionFailures = 0;
                    }
                }

                _connected = false;

                if (!token.IsCancellationRequested)
                {
                    Debug.Log($"[ServerConnection] Disconnected, reconnecting in {ReconnectDelay}s...");
                    try
                    {
                        await Task.Delay(TimeSpan.FromSeconds(ReconnectDelay), token).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }
                }
            }
        }

        // ─── Server Auto-Discovery ──────────────────────────────────────────

        private async Task<string> DiscoverServer(CancellationToken token)
        {
            string localIp = StatusReporter.GetLocalIPAddress();
            if (string.IsNullOrEmpty(localIp) || localIp == "0.0.0.0")
            {
                Debug.LogWarning("[ServerConnection] Cannot discover server: no local IP");
                return null;
            }

            string[] parts = localIp.Split('.');
            if (parts.Length != 4)
            {
                Debug.LogWarning($"[ServerConnection] Cannot discover server: unexpected IP format {localIp}");
                return null;
            }

            string subnet = $"{parts[0]}.{parts[1]}.{parts[2]}";
            Debug.Log($"[ServerConnection] Scanning subnet {subnet}.0/24 for server on port {ServerPort}...");

            var semaphore = new SemaphoreSlim(DiscoveryConcurrency);
            var foundServer = new TaskCompletionSource<string>();
            var tasks = new Task[254];

            for (int i = 1; i <= 254; i++)
            {
                string ip = $"{subnet}.{i}";
                tasks[i - 1] = ProbeServerAt(ip, semaphore, foundServer, token);
            }

            try
            {
                // Race: either we find a server or all probes complete
                var allDone = Task.WhenAll(tasks);
                var winner = await Task.WhenAny(foundServer.Task, allDone).ConfigureAwait(false);

                if (foundServer.Task.IsCompleted && foundServer.Task.Result != null)
                {
                    Debug.Log($"[ServerConnection] Found server at {foundServer.Task.Result}");
                    return foundServer.Task.Result;
                }
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[ServerConnection] Discovery scan error: {e.Message}");
            }

            Debug.Log("[ServerConnection] No server found on subnet");
            return null;
        }

        private async Task ProbeServerAt(string ip, SemaphoreSlim semaphore, TaskCompletionSource<string> found, CancellationToken token)
        {
            // If already found, skip
            if (found.Task.IsCompleted) return;

            await semaphore.WaitAsync(token).ConfigureAwait(false);
            try
            {
                if (found.Task.IsCompleted) return;

                // Quick TCP connect check
                using (var client = new TcpClient())
                {
                    var connectTask = client.ConnectAsync(ip, ServerPort);
                    var completed = await Task.WhenAny(
                        connectTask,
                        Task.Delay(DiscoveryTimeoutMs, token)
                    ).ConfigureAwait(false);

                    if (completed != connectTask || !client.Connected)
                        return;
                }

                if (found.Task.IsCompleted) return;

                // Verify it's our server by hitting /api/server-info
                string url = $"http://{ip}:{ServerPort}/api/server-info";
                var request = WebRequest.CreateHttp(url);
                request.Timeout = DiscoveryTimeoutMs;
                request.Method = "GET";

                try
                {
                    using (var response = (HttpWebResponse)await request.GetResponseAsync().ConfigureAwait(false))
                    {
                        if (response.StatusCode == HttpStatusCode.OK)
                        {
                            using (var reader = new System.IO.StreamReader(response.GetResponseStream()))
                            {
                                string body = await reader.ReadToEndAsync().ConfigureAwait(false);
                                if (body.Contains("\"ip\"") && body.Contains("\"port\""))
                                {
                                    found.TrySetResult($"{ip}:{ServerPort}");
                                    return;
                                }
                            }
                        }
                    }
                }
                catch
                {
                    // Not our server
                }
            }
            catch
            {
                // Connection failed
            }
            finally
            {
                semaphore.Release();
            }
        }

        // ─── WebSocket Connection ───────────────────────────────────────────

        private async Task ConnectAndRun(CancellationToken token)
        {
            CloseWebSocket();
            _ws = new ClientWebSocket();

            Debug.Log($"[ServerConnection] Connecting to {_serverUrl}...");
            await _ws.ConnectAsync(new Uri(_serverUrl), token).ConfigureAwait(false);
            _connected = true;
            _connectionFailures = 0;
            Debug.Log($"[ServerConnection] Connected to {_serverUrl}");

            await SendRegister(token).ConfigureAwait(false);

            var buffer = new byte[ReceiveBufferSize];
            var messageBuilder = new StringBuilder();

            while (_ws.State == WebSocketState.Open && !token.IsCancellationRequested)
            {
                var result = await _ws.ReceiveAsync(new ArraySegment<byte>(buffer), token).ConfigureAwait(false);

                if (result.MessageType == WebSocketMessageType.Close)
                {
                    Debug.Log("[ServerConnection] Server closed connection");
                    break;
                }

                if (result.MessageType == WebSocketMessageType.Text)
                {
                    messageBuilder.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));

                    if (result.EndOfMessage)
                    {
                        string message = messageBuilder.ToString();
                        messageBuilder.Clear();
                        HandleServerMessage(message);
                    }
                }
            }
        }

        private async Task SendRegister(CancellationToken token)
        {
            string ip = StatusReporter.GetLocalIPAddress();
            int battery = StatusReporter.GetBatteryPercent();
            string deviceName = StatusReporter.GetDeviceName();

            var sb = new StringBuilder(256);
            sb.Append("{\"type\":\"register\"");
            sb.AppendFormat(",\"deviceId\":\"{0}\"", StatusReporter.EscapeJson(_deviceId));
            sb.AppendFormat(",\"ip\":\"{0}\"", StatusReporter.EscapeJson(ip));
            sb.AppendFormat(",\"battery\":{0}", battery);
            sb.AppendFormat(",\"state\":\"idle\"");
            sb.AppendFormat(",\"playerVersion\":\"{0}\"", StatusReporter.EscapeJson(StatusReporter.PlayerVersion));
            if (!string.IsNullOrEmpty(deviceName))
                sb.AppendFormat(",\"deviceName\":\"{0}\"", StatusReporter.EscapeJson(deviceName));
            sb.Append('}');

            await SendText(sb.ToString(), token).ConfigureAwait(false);
            Debug.Log("[ServerConnection] Register message sent");
        }

        private async void SendHeartbeat()
        {
            if (_ws == null || _ws.State != WebSocketState.Open) return;

            try
            {
                string statusJson = statusReporter != null ? statusReporter.GetStatusJson() : "{}";
                string message = "{\"type\":\"status\"," + statusJson.Substring(1);

                var token = _cts?.Token ?? CancellationToken.None;
                await SendText(message, token).ConfigureAwait(false);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[ServerConnection] Heartbeat send failed: {e.Message}");
                _connected = false;
            }
        }

        private async Task SendText(string text, CancellationToken token)
        {
            if (_ws == null || _ws.State != WebSocketState.Open) return;

            var bytes = Encoding.UTF8.GetBytes(text);
            await _ws.SendAsync(
                new ArraySegment<byte>(bytes),
                WebSocketMessageType.Text,
                true,
                token
            ).ConfigureAwait(false);
        }

        // ─── Command Handling ───────────────────────────────────────────────

        private void HandleServerMessage(string raw)
        {
            try
            {
                string msgType = ExtractJsonString(raw, "type");
                if (msgType != "command") return;

                string action = ExtractJsonString(raw, "action");
                if (string.IsNullOrEmpty(action)) return;

                Debug.Log($"[ServerConnection] Command received: {action}");
                _mainThreadQueue.Enqueue(() => ExecuteCommand(action, raw));
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[ServerConnection] Failed to parse server message: {e.Message}");
            }
        }

        private void ExecuteCommand(string action, string raw)
        {
            try
            {
                switch (action.ToLowerInvariant())
                {
                    case "open":
                        {
                            string file = ExtractJsonString(raw, "file");
                            string mode = ExtractJsonString(raw, "mode");
                            bool loop = ExtractJsonBool(raw, "loop");

                            if (viewModeManager != null && !string.IsNullOrEmpty(mode))
                            {
                                ViewMode vm = ADBCommandRouter.ParseMode(mode);
                                if (vm != viewModeManager.CurrentMode)
                                    viewModeManager.SetMode(vm);
                            }

                            if (videoPlayer != null && !string.IsNullOrEmpty(file))
                            {
                                videoPlayer.Open(file);
                                videoPlayer.IsLooping = loop;
                            }
                            break;
                        }
                    case "play":
                        videoPlayer?.Play();
                        break;
                    case "pause":
                        videoPlayer?.Pause();
                        break;
                    case "stop":
                        videoPlayer?.Stop();
                        if (viewModeManager != null)
                            viewModeManager.SetMode(ViewMode.None);
                        break;
                    case "recenter":
                        orientationManager?.Recenter();
                        break;
                    case "set_volume":
                        {
                            float globalVol = ExtractJsonFloat(raw, "globalVolume", 1f);
                            float personalVol = ExtractJsonFloat(raw, "personalVolume", 1f);
                            if (videoPlayer != null)
                            {
                                videoPlayer.GlobalVolume = globalVol;
                                videoPlayer.PersonalVolume = personalVol;
                            }
                            break;
                        }
                    case "set_mode":
                        {
                            string mode = ExtractJsonString(raw, "mode");
                            if (viewModeManager != null && !string.IsNullOrEmpty(mode))
                            {
                                ViewMode vm = ADBCommandRouter.ParseMode(mode);
                                viewModeManager.SetMode(vm);
                            }
                            break;
                        }
                    case "ping":
                        PlayPingSound();
                        break;
                    case "toggle_debug":
                        {
                            var debugPanel = FindObjectOfType<DebugLogPanel>();
                            if (debugPanel != null) debugPanel.Toggle();
                            break;
                        }
                    default:
                        Debug.LogWarning($"[ServerConnection] Unknown command: {action}");
                        break;
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[ServerConnection] Command execution failed ({action}): {e}");
            }
        }

        private void PlayPingSound()
        {
            try
            {
                int sampleRate = 44100;
                float duration = 0.5f;
                float frequency = 880f;
                int sampleCount = Mathf.CeilToInt(sampleRate * duration);
                var clip = AudioClip.Create("Ping", sampleCount, 1, sampleRate, false);
                float[] samples = new float[sampleCount];
                for (int i = 0; i < sampleCount; i++)
                {
                    float t = (float)i / sampleRate;
                    float envelope = 1f - (t / duration);
                    samples[i] = Mathf.Sin(2f * Mathf.PI * frequency * t) * envelope * 0.8f;
                }
                clip.SetData(samples, 0);

                var audioSource = gameObject.GetComponent<AudioSource>();
                if (audioSource == null)
                    audioSource = gameObject.AddComponent<AudioSource>();
                audioSource.PlayOneShot(clip);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[ServerConnection] Ping sound failed: {e.Message}");
            }
        }

        private void CloseWebSocket()
        {
            if (_ws != null)
            {
                try
                {
                    if (_ws.State == WebSocketState.Open || _ws.State == WebSocketState.Connecting)
                    {
                        _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "closing", CancellationToken.None)
                            .ConfigureAwait(false);
                    }
                }
                catch { }
                try { _ws.Dispose(); } catch { }
                _ws = null;
            }
        }

        // ─── Simple JSON helpers (avoid dependency on external JSON libs) ────

        private static string ExtractJsonString(string json, string key)
        {
            string search = $"\"{key}\":\"";
            int start = json.IndexOf(search, StringComparison.Ordinal);
            if (start < 0) return null;
            start += search.Length;
            int end = json.IndexOf('"', start);
            if (end < 0) return null;
            return json.Substring(start, end - start).Replace("\\\"", "\"").Replace("\\\\", "\\");
        }

        private static bool ExtractJsonBool(string json, string key)
        {
            string search = $"\"{key}\":";
            int start = json.IndexOf(search, StringComparison.Ordinal);
            if (start < 0) return false;
            start += search.Length;
            return json.Substring(start).TrimStart().StartsWith("true", StringComparison.OrdinalIgnoreCase);
        }

        private static float ExtractJsonFloat(string json, string key, float defaultValue)
        {
            string search = $"\"{key}\":";
            int start = json.IndexOf(search, StringComparison.Ordinal);
            if (start < 0) return defaultValue;
            start += search.Length;
            string rest = json.Substring(start).TrimStart();
            int end = 0;
            while (end < rest.Length && (char.IsDigit(rest[end]) || rest[end] == '.' || rest[end] == '-'))
                end++;
            if (end == 0) return defaultValue;
            if (float.TryParse(rest.Substring(0, end), System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out float result))
                return result;
            return defaultValue;
        }
    }
}
