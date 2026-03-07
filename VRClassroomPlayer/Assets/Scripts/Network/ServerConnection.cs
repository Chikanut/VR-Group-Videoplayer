using System;
using System.Collections.Concurrent;
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
    /// </summary>
    public class ServerConnection : MonoBehaviour
    {
        [SerializeField] private StatusReporter statusReporter;
        [SerializeField] private VideoPlayerController videoPlayer;
        [SerializeField] private ViewModeManager viewModeManager;
        [SerializeField] private OrientationManager orientationManager;

        private const float HeartbeatInterval = 5f;
        private const float ReconnectDelay = 3f;
        private const int ReceiveBufferSize = 8192;

        private ClientWebSocket _ws;
        private CancellationTokenSource _cts;
        private readonly ConcurrentQueue<Action> _mainThreadQueue = new ConcurrentQueue<Action>();
        private float _lastHeartbeatTime;
        private bool _connected;
        private string _serverUrl;
        private string _deviceId;

        private void Start()
        {
            _deviceId = StatusReporter.GetAndroidId();
            _serverUrl = BuildServerUrl();

            if (string.IsNullOrEmpty(_serverUrl))
            {
                Debug.Log("[ServerConnection] No instructor_ip configured, WS disabled. Will retry when set.");
            }

            _cts = new CancellationTokenSource();
            StartConnectionLoop();
        }

        private void Update()
        {
            // Process queued main-thread actions
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

            // Send heartbeat
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
                // Force reconnect attempt
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
                return $"ws://{server}:8000/ws/device";
        }

        private async void StartConnectionLoop()
        {
            var token = _cts.Token;

            while (!token.IsCancellationRequested)
            {
                _serverUrl = BuildServerUrl();

                if (string.IsNullOrEmpty(_serverUrl))
                {
                    await Task.Delay(TimeSpan.FromSeconds(ReconnectDelay), token).ConfigureAwait(false);
                    continue;
                }

                try
                {
                    await ConnectAndRun(token).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[ServerConnection] Connection error: {e.Message}");
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

        private async Task ConnectAndRun(CancellationToken token)
        {
            CloseWebSocket();
            _ws = new ClientWebSocket();

            Debug.Log($"[ServerConnection] Connecting to {_serverUrl}...");
            await _ws.ConnectAsync(new Uri(_serverUrl), token).ConfigureAwait(false);
            _connected = true;
            Debug.Log($"[ServerConnection] Connected to {_serverUrl}");

            // Send register message
            await SendRegister(token).ConfigureAwait(false);

            // Receive loop
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
                // Get status JSON from StatusReporter (must be called on main thread)
                string statusJson = statusReporter != null ? statusReporter.GetStatusJson() : "{}";

                // Wrap in status message
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

        private void HandleServerMessage(string raw)
        {
            try
            {
                // Simple JSON parsing for command messages
                string msgType = ExtractJsonString(raw, "type");
                if (msgType != "command") return;

                string action = ExtractJsonString(raw, "action");
                if (string.IsNullOrEmpty(action)) return;

                Debug.Log($"[ServerConnection] Command received: {action}");

                // Queue command execution on main thread
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
