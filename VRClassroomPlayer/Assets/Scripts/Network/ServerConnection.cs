using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using System.Globalization;

namespace VRClassroom
{
    /// <summary>
    /// WebSocket client that connects to the instructor server.
    /// Handles registration, heartbeat status updates, and command reception.
    /// Auto-discovers the server on the local network if not configured.
    /// </summary>
    public class ServerConnection : MonoBehaviour
    {
        [Serializable]
        private class WsCommandMessage
        {
            public string type;
            public string commandId;
            public string action;
            public string file;
            public string mode;
            public bool loop;
            public bool autoRecenterOnOpen = true;
            public float globalVolume;
            public float personalVolume;
            public VideoAdvancedSettings advancedSettings;
            public float globalVolume;
            public float personalVolume;
        }

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
        private const int MessagePreviewLength = 160;
        private const string VerboseNetworkLogsPrefKey = "verbose_network_logs";

        private ClientWebSocket _ws;
        private CancellationTokenSource _cts;
        private readonly ConcurrentQueue<Action> _mainThreadQueue = new ConcurrentQueue<Action>();
        private float _lastHeartbeatTime;
        private bool _connected;
        private string _serverUrl;
        private string _deviceId;
        private bool _discovering;
        private int _connectionFailures;
        private int _reconnectAttempt;
        private int _discoveryAttempt;

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
                _reconnectAttempt++;
                _serverUrl = BuildServerUrl();
                LogInfo("connection_loop_iteration", null, $"reconnectAttempt={_reconnectAttempt}, serverUrl={SafeValue(_serverUrl)}");

                // If no server configured, try to discover it
                if (string.IsNullOrEmpty(_serverUrl))
                {
                    if (!_discovering)
                    {
                        _discovering = true;
                        _discoveryAttempt++;
                        LogInfo("discovery_start", null, $"attempt={_discoveryAttempt}");
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
                            LogInfo("discovery_success", null, $"attempt={_discoveryAttempt}, discovered={discovered}");
                        }
                        else
                        {
                            LogWarning("discovery_not_found", null, $"attempt={_discoveryAttempt}, retryInSec={DiscoveryRetryDelay}");
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
                    LogWarning("connection_error", null, $"attempt={_reconnectAttempt}, reason={e.GetType().Name}: {e.Message}");
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
                    LogInfo("reconnect_scheduled", null, $"attempt={_reconnectAttempt}, retryInSec={ReconnectDelay}, failures={_connectionFailures}");
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
                LogWarning("discovery_error", null, $"attempt={_discoveryAttempt}, reason={e.GetType().Name}: {e.Message}");
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
                catch (Exception e)
                {
                    LogVerbose("discovery_probe_http_error", null, $"attempt={_discoveryAttempt}, ip={ip}, reason={e.GetType().Name}: {e.Message}");
                }
            }
            catch (Exception e)
            {
                LogVerbose("discovery_probe_connect_error", null, $"attempt={_discoveryAttempt}, ip={ip}, reason={e.GetType().Name}: {e.Message}");
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
            sb.AppendFormat(CultureInfo.InvariantCulture, ",\"deviceId\":\"{0}\"", StatusReporter.EscapeJson(_deviceId));
            sb.AppendFormat(CultureInfo.InvariantCulture, ",\"ip\":\"{0}\"", StatusReporter.EscapeJson(ip));
            sb.AppendFormat(CultureInfo.InvariantCulture, ",\"battery\":{0}", battery);
            sb.AppendFormat(CultureInfo.InvariantCulture, ",\"state\":\"idle\"");
            sb.AppendFormat(CultureInfo.InvariantCulture, ",\"playerVersion\":\"{0}\"", StatusReporter.EscapeJson(UnityEngine.Application.version));
            if (!string.IsNullOrEmpty(deviceName))
                sb.AppendFormat(CultureInfo.InvariantCulture, ",\"deviceName\":\"{0}\"", StatusReporter.EscapeJson(deviceName));
            sb.Append('}');

            await SendText(sb.ToString(), token).ConfigureAwait(false);
            Debug.Log("[ServerConnection] Register message sent");
        }

        private async void SendHeartbeat()
        {
            LogVerbose("heartbeat_prepare", null, $"wsState={GetWebSocketState()}");
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
            LogVerbose("send_text_prepare", null, $"wsState={GetWebSocketState()}, payloadLength={text?.Length ?? 0}");
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
            int rawLength = raw?.Length ?? 0;
            string preview = CreatePayloadPreview(raw);

            try
            {
                var command = JsonUtility.FromJson<WsCommandMessage>(raw);
                if (command == null)
                {
                    Debug.LogWarning("[ServerConnection] Ignoring message: failed to deserialize command payload");
                    return;
                }

                if (!string.Equals(command.type, "command", StringComparison.Ordinal))
                {
                    Debug.LogWarning($"[ServerConnection] Ignoring message: unexpected type '{command.type ?? "<null>"}'");
                    return;
                }

                if (string.IsNullOrWhiteSpace(command.action))
                {
                    Debug.LogWarning("[ServerConnection] Ignoring command: 'action' is missing or empty");
                    return;
                }

                Debug.Log($"[ServerConnection] Command received: {command.action}");
                    LogWarning("message_dropped", null, $"reason=invalid json, rawLength={rawLength}, preview={preview}");
                    return;
                }

                string commandId = ResolveCommandId(command);
                LogInfo("message_received", commandId,
                    $"rawLength={rawLength}, preview={preview}, msgType={SafeValue(command.type)}, action={SafeValue(command.action)}");

                if (!string.Equals(command.type, "command", StringComparison.Ordinal))
                {
                    LogWarning("message_dropped", commandId,
                        $"reason=unexpected type, msgType={SafeValue(command.type)}, action={SafeValue(command.action)}");
                    return;
                }

                if (string.IsNullOrWhiteSpace(command.action))
                {
                    LogWarning("message_dropped", commandId, "reason=missing action");
                    return;
                }

                LogInfo("command_received", commandId, $"action={command.action}");
                LogInfo("queue_enqueue", commandId, $"action={command.action}");
                _mainThreadQueue.Enqueue(() => ExecuteCommand(command, raw));
            }
            catch (Exception e)
            {
                LogWarning("message_dropped", null,
                    $"reason=invalid json, rawLength={rawLength}, preview={preview}, parseError={e.GetType().Name}: {e.Message}");
            }
        }

        private void ExecuteCommand(WsCommandMessage command, string raw)
        {
            string action = command.action;
            string commandId = ResolveCommandId(command);
            try
            {
                switch (action.ToLowerInvariant())
                {
                    case "open":
                        {
                            string file = command.file;
                            string mode = command.mode;
                            bool loop = command.loop;
                            bool autoRecenterOnOpen = command.autoRecenterOnOpen;
                            LogInfo("command_start", commandId,
                                $"action=open, file={SafeValue(file)}, mode={SafeValue(mode)}, loop={loop}");

                            ViewMode targetMode = viewModeManager != null ? viewModeManager.CurrentMode : PlayerConfig.DefaultViewMode;
                            if (viewModeManager != null && !string.IsNullOrEmpty(mode))
                            {
                                targetMode = ADBCommandRouter.ParseMode(mode);
                                if (targetMode != viewModeManager.CurrentMode)
                                    viewModeManager.SetMode(targetMode);
                            }

                            if (viewModeManager != null)
                            {
                                viewModeManager.ApplyAdvancedSettingsOverride(targetMode, command.advancedSettings);
                            }

                            if (videoPlayer != null)
                            bool openInvoked = false;
                            if (videoPlayer != null && !string.IsNullOrEmpty(file))
                            {
                                videoPlayer.IsLooping = loop;
                                openInvoked = true;
                            }

                            if (autoRecenterOnOpen)
                            {
                                orientationManager?.Recenter();
                            }

                            if (string.IsNullOrEmpty(file))
                            {
                                Debug.LogWarning("[ServerConnection] OPEN command ignored: 'file' is missing or empty");
                                break;
                            }

                            if (videoPlayer != null)
                            {
                                videoPlayer.Open(file);
                            }
                            LogInfo("command_end", commandId,
                                $"action=open, file={SafeValue(file)}, mode={SafeValue(mode)}, loop={loop}, openInvoked={openInvoked}");
                            break;
                        }
                    case "play":
                        LogInfo("command_start", commandId, "action=play");
                        videoPlayer?.Play();
                        LogInfo("command_end", commandId, "action=play");
                        break;
                    case "pause":
                        LogInfo("command_start", commandId, "action=pause");
                        videoPlayer?.Pause();
                        LogInfo("command_end", commandId, "action=pause");
                        break;
                    case "stop":
                        LogInfo("command_start", commandId, "action=stop");
                        videoPlayer?.Stop();
                        if (viewModeManager != null)
                            viewModeManager.SetMode(ViewMode.None);
                        LogInfo("command_end", commandId, "action=stop");
                        break;
                    case "recenter":
                        LogInfo("command_start", commandId, "action=recenter");
                        orientationManager?.Recenter();
                        LogInfo("command_end", commandId, "action=recenter");
                        break;
                    case "set_volume":
                        {
                            float globalVol = HasJsonField(raw, "globalVolume") ? command.globalVolume : 1f;
                            float personalVol = HasJsonField(raw, "personalVolume") ? command.personalVolume : 1f;
                            LogInfo("command_start", commandId,
                                $"action=set_volume, globalVolume={globalVol}, personalVolume={personalVol}");
                            videoPlayer?.SetVolume(globalVol, personalVol);
                            LogInfo("command_end", commandId,
                                $"action=set_volume, globalVolume={globalVol}, personalVolume={personalVol}");
                            break;
                        }
                    case "set_mode":
                        {
                            string mode = command.mode;
                            LogInfo("command_start", commandId, $"action=set_mode, mode={SafeValue(mode)}");
                            if (viewModeManager != null && !string.IsNullOrEmpty(mode))
                            {
                                ViewMode vm = ADBCommandRouter.ParseMode(mode);
                                viewModeManager.SetMode(vm);
                            }
                            LogInfo("command_end", commandId, $"action=set_mode, mode={SafeValue(mode)}");
                            break;
                        }
                    case "ping":
                        LogInfo("command_start", commandId, "action=ping");
                        PlayPingSound();
                        LogInfo("command_end", commandId, "action=ping");
                        break;
                    case "toggle_debug":
                        {
                            LogInfo("command_start", commandId, "action=toggle_debug");
                            var debugPanel = FindObjectOfType<DebugLogPanel>();
                            if (debugPanel != null) debugPanel.Toggle();
                            LogInfo("command_end", commandId, "action=toggle_debug");
                            break;
                        }
                    default:
                        LogWarning("command_unknown", commandId, $"action={SafeValue(action)}");
                        break;
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[ServerConnection][event=command_error][commandId={commandId}] action={SafeValue(action)}, reason={e.GetType().Name}: {e.Message}");
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
            LogVerbose("close_ws_prepare", null, $"wsState={GetWebSocketState()}");
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

        // ─── Minimal JSON fallback helpers ───────────────────────────────────

        private static bool HasJsonField(string json, string key)
        {
            return json.IndexOf($"\"{key}\"", StringComparison.Ordinal) >= 0;

        private static bool HasJsonField(string json, string key)
        {
            return json.IndexOf($"\"{key}\"", StringComparison.Ordinal) >= 0;
        }

        private static string ResolveCommandId(WsCommandMessage command)
        {
            if (command == null || string.IsNullOrWhiteSpace(command.commandId))
                return "n/a";

            return command.commandId;
        }

        private static string CreatePayloadPreview(string raw)
        {
            if (string.IsNullOrEmpty(raw))
                return "<empty>";

            return raw.Length <= MessagePreviewLength
                ? raw
                : raw.Substring(0, MessagePreviewLength) + "...";
        }

        private static string SafeValue(string value)
        {
            return string.IsNullOrWhiteSpace(value) ? "<null>" : value;
        }

        private string GetWebSocketState()
        {
            return _ws?.State.ToString() ?? "<null>";
        }

        private bool IsVerboseNetworkLogsEnabled()
        {
            return PlayerPrefs.GetInt(VerboseNetworkLogsPrefKey, 0) == 1;
        }

        private void LogInfo(string stage, string commandId, string details)
        {
            Debug.Log($"[ServerConnection][stage={stage}][commandId={commandId ?? "n/a"}] {details}");
        }

        private void LogWarning(string stage, string commandId, string details)
        {
            Debug.LogWarning($"[ServerConnection][stage={stage}][commandId={commandId ?? "n/a"}] {details}");
        }

        private void LogVerbose(string stage, string commandId, string details)
        {
            if (!IsVerboseNetworkLogsEnabled())
                return;

            LogInfo(stage, commandId, details);
        }
    }
}
