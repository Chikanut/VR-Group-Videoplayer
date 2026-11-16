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
    ///
    /// Protocol (client -> server):
    ///   {"type":"register", ...full status fields...}   right after connect
    ///   {"type":"status",   ...full status fields...}   immediately after register, then
    ///                                                   every HeartbeatInterval seconds and
    ///                                                   whenever the device name changes
    /// Protocol (server -> client):
    ///   {"type":"command","action":"open|play|pause|stop|recenter|seek|set_volume|set_mode|set_name|ping|toggle_debug|update", ...}
    ///   update: {"url":"/api/player/apk","sha256":"..."} - silent self-update, skipped if already installed
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
            public string placementMode;
            public string name;
            public bool loop;
            public bool autoRecenterOnOpen = true;
            public float globalVolume;
            public float personalVolume;
            public float time;
            public string url;
            public string sha256;
            public string settings;
            public VideoAdvancedSettings advancedSettings;
        }

        [SerializeField] private StatusReporter statusReporter;
        [SerializeField] private VideoPlayerController videoPlayer;
        [SerializeField] private ViewModeManager viewModeManager;
        [SerializeField] private OrientationManager orientationManager;

        private const float HeartbeatInterval = 5f;
        private const float ReconnectDelay = 3f;
        private const float NudgeReconnectDelay = 0.25f;
        private const float DiscoveryRetryDelay = 10f;
        private const int FailuresBeforeDiscovery = 3;
        private const int ReceiveBufferSize = 8192;
        private const int ServerPort = 8000;
        private const int DiscoveryConcurrency = 30;
        private const int DiscoveryTimeoutMs = 2000;
        private const int MessagePreviewLength = 160;
        private const string VerboseNetworkLogsPrefKey = "verbose_network_logs";
        private const string InstructorIpPrefKey = "instructor_ip";

        private readonly object _wsLock = new object();
        private readonly SemaphoreSlim _sendLock = new SemaphoreSlim(1, 1);
        private readonly SemaphoreSlim _wake = new SemaphoreSlim(0, 1); // interrupts reconnect/discovery delays
        private readonly ConcurrentQueue<Action> _mainThreadQueue = new ConcurrentQueue<Action>();

        private ClientWebSocket _ws;
        private CancellationTokenSource _sessionCts;
        private CancellationTokenSource _cts;

        private float _lastHeartbeatTime;
        private volatile bool _connected;
        private volatile bool _sendStatusNow;
        private volatile bool _nudgeRequested;
        private int _heartbeatInFlight; // 0/1, guards against overlapping heartbeats
        private volatile string _savedServerAddress; // "ip:port", mirrors PlayerPrefs (main-thread only)
        private string _serverUrl;
        private string _deviceId;
        private bool _verboseLogs;
        private int _connectionFailures;
        private int _reconnectAttempt;
        private int _discoveryAttempt;

        // Sleep handling: while the headset sleeps Wi-Fi goes down, so every reconnect
        // fails and after a few failures the loop used to start 254-host subnet scans.
        // On wake the app then had a half-dead socket plus a scan in flight and lagged
        // badly. Now the session is closed when the app pauses, the loop idles until the
        // app resumes, and discovery is held off while Wi-Fi reconnects after wake.
        private volatile bool _appPaused;
        private long _discoveryHoldUntilTicks; // DateTime.UtcNow.Ticks, via Interlocked
        private const float WakeDiscoveryHoldSeconds = 30f;

        // The headset must not fall asleep while the instructor server is connected (sleep
        // leaks video memory and drops the session). Released only after a longer outage so
        // short Wi-Fi blips do not toggle it.
        private const float KeepAwakeReleaseDelay = 60f;
        private bool _keepAwake;
        private bool _sleepRequested; // instructor "sleep": never re-assert keep-awake (process restarts after wake)
        private float _disconnectedSince = -1f;
        private int _updateInFlight; // 0/1

        private void Start()
        {
            PlayerSystem.StartWatchdog();

            _deviceId = StatusReporter.GetAndroidId();
            _savedServerAddress = PlayerPrefs.GetString(InstructorIpPrefKey, string.Empty);
            _verboseLogs = PlayerPrefs.GetInt(VerboseNetworkLogsPrefKey, 0) == 1;

            if (string.IsNullOrEmpty(_savedServerAddress))
            {
                Debug.Log("[ServerConnection] No instructor_ip configured. Will auto-discover server on network.");
            }

            StatusReporter.OnDeviceNameChanged += HandleDeviceNameChanged;
            LanServer.ServerIpChanged += HandleServerIpChanged;

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

            if (_connected && (_sendStatusNow || Time.time - _lastHeartbeatTime >= HeartbeatInterval))
            {
                _sendStatusNow = false;
                _lastHeartbeatTime = Time.time;
                SendHeartbeat();
            }

            UpdateKeepAwake();
        }

        private void UpdateKeepAwake()
        {
            if (_sleepRequested) return;
            if (_connected)
            {
                _disconnectedSince = -1f;
                if (_keepAwake) return;
                _keepAwake = true;
                PlayerSystem.SetKeepAwake(true);
                return;
            }

            if (!_keepAwake) return;
            if (_disconnectedSince < 0f) _disconnectedSince = Time.time;
            if (Time.time - _disconnectedSince < KeepAwakeReleaseDelay) return;

            _keepAwake = false;
            PlayerSystem.SetKeepAwake(false);
        }

        private void OnApplicationQuit()
        {
            if (_keepAwake) PlayerSystem.SetKeepAwake(false);
        }

        private void OnApplicationPause(bool paused)
        {
            if (paused)
            {
                Debug.Log("[ServerConnection] Application paused (sleep): closing server session until wake");
                _appPaused = true;
                _connected = false;
                // Off the main thread: nothing inside the pause callback may block, or the
                // app stays frozen after wake.
                ThreadPool.QueueUserWorkItem(_ =>
                {
                    try { AbortSession(wakeLoop: false); }
                    catch (Exception e) { Debug.LogWarning($"[ServerConnection] Abort on pause failed: {e.Message}"); }
                });
                return;
            }

            Debug.Log("[ServerConnection] Application resumed: reconnecting to server");
            _appPaused = false;
            Interlocked.Exchange(ref _discoveryHoldUntilTicks,
                DateTime.UtcNow.AddSeconds(WakeDiscoveryHoldSeconds).Ticks);
            _sendStatusNow = true;
            NudgeReconnect();
        }

        private void OnApplicationFocus(bool hasFocus)
        {
            if (!hasFocus || _appPaused) return;

            WebSocketState? state;
            lock (_wsLock)
            {
                state = _ws?.State;
            }

            if (state == WebSocketState.Open)
            {
                // Socket survived the pause: resume heartbeats and report right away so the
                // dashboard does not wait a full interval for fresh data.
                _connected = true;
                _sendStatusNow = true;
                return;
            }

            if (state == WebSocketState.Connecting)
            {
                // A connect attempt is already in flight; interrupting it would only add a
                // failure and delay the reconnect.
                return;
            }

            Debug.Log("[ServerConnection] App focused without an open socket, nudging reconnect");
            NudgeReconnect();
        }

        private void OnDestroy()
        {
            StatusReporter.OnDeviceNameChanged -= HandleDeviceNameChanged;
            LanServer.ServerIpChanged -= HandleServerIpChanged;
            _cts?.Cancel();
            lock (_wsLock)
            {
                CloseWebSocketLocked();
            }
        }

        // ─── Main-thread event handlers ──────────────────────────────────────

        private void HandleDeviceNameChanged(string name)
        {
            // Push the new name to the server immediately (it is persisted on the headset,
            // the server only mirrors it).
            _sendStatusNow = true;
        }

        private void HandleServerIpChanged(string serverIp)
        {
            string normalized = serverIp ?? string.Empty;
            if (normalized == _savedServerAddress) return;

            Debug.Log($"[ServerConnection] Server address changed via LAN API: '{_savedServerAddress}' -> '{normalized}'");
            _savedServerAddress = normalized;
            NudgeReconnect();
        }

        /// <summary>Abort the current session (if any) so the connection loop retries at once.</summary>
        private void NudgeReconnect()
        {
            AbortSession(wakeLoop: true);
        }

        private void AbortSession(bool wakeLoop)
        {
            lock (_wsLock)
            {
                if (_ws != null)
                {
                    // Only flag a nudge when there is a session to abort; otherwise a later
                    // genuine failure would be misattributed to us.
                    _nudgeRequested = true;
                }
                try { _sessionCts?.Cancel(); } catch { }
                CloseWebSocketLocked();
            }

            if (!wakeLoop) return;

            // Wake the connection loop if it is sitting in a reconnect/discovery delay.
            try
            {
                if (_wake.CurrentCount == 0) _wake.Release();
            }
            catch (SemaphoreFullException) { }
        }

        private bool IsDiscoveryHeld()
        {
            return _appPaused || DateTime.UtcNow.Ticks < Interlocked.Read(ref _discoveryHoldUntilTicks);
        }

        private void SaveServerAddress(string address)
        {
            _savedServerAddress = address ?? string.Empty;
            _mainThreadQueue.Enqueue(() =>
            {
                PlayerPrefs.SetString(InstructorIpPrefKey, address ?? string.Empty);
                PlayerPrefs.Save();
                LanServer.NotifyServerIpChanged(address);
                Debug.Log($"[ServerConnection] Server address saved: {address}");
            });
        }

        private string BuildServerUrl()
        {
            string server = _savedServerAddress;
            if (string.IsNullOrEmpty(server)) return null;

            if (server.Contains(":"))
                return $"ws://{server}/ws/device";
            else
                return $"ws://{server}:{ServerPort}/ws/device";
        }

        // ─── Connection loop ────────────────────────────────────────────────

        private async void StartConnectionLoop()
        {
            var token = _cts.Token;

            while (!token.IsCancellationRequested)
            {
                if (_appPaused)
                {
                    // Headset is asleep: no reconnects or scans until OnApplicationPause(false)
                    // wakes the loop.
                    _connectionFailures = 0;
                    if (!await DelaySafe(5f, token).ConfigureAwait(false)) break;
                    continue;
                }

                _reconnectAttempt++;
                _serverUrl = BuildServerUrl();
                LogVerbose("connection_loop_iteration", null, $"reconnectAttempt={_reconnectAttempt}, serverUrl={SafeValue(_serverUrl)}");

                // No server configured: discover it first.
                if (string.IsNullOrEmpty(_serverUrl))
                {
                    string discovered = await RunDiscovery(token).ConfigureAwait(false);
                    if (token.IsCancellationRequested) break;

                    if (!string.IsNullOrEmpty(discovered))
                    {
                        SaveServerAddress(discovered);
                        _serverUrl = $"ws://{discovered}/ws/device";
                        _connectionFailures = 0;
                    }
                    else
                    {
                        LogWarning("discovery_not_found", null, $"attempt={_discoveryAttempt}, retryInSec={DiscoveryRetryDelay}");
                        if (!await DelaySafe(DiscoveryRetryDelay, token).ConfigureAwait(false)) break;
                        continue;
                    }
                }

                bool nudged = false;
                try
                {
                    await ConnectAndRun(_serverUrl, token).ConfigureAwait(false);
                    // Server closed the socket normally (e.g. replaced by a newer connection
                    // or server restart). Not a failure of the saved address.
                    _connectionFailures = 0;
                }
                catch (OperationCanceledException) when (token.IsCancellationRequested)
                {
                    break;
                }
                catch (Exception e)
                {
                    if (_nudgeRequested)
                    {
                        // We aborted the session ourselves (focus regained / address changed).
                        nudged = true;
                        _nudgeRequested = false;
                        LogInfo("session_aborted", null, "reason=nudge");
                    }
                    else
                    {
                        _connectionFailures++;
                        LogWarning("connection_error", null,
                            $"attempt={_reconnectAttempt}, failures={_connectionFailures}, reason={e.GetType().Name}: {e.Message}");
                    }
                }

                _connected = false;

                if (!nudged && _connectionFailures >= FailuresBeforeDiscovery && IsDiscoveryHeld())
                {
                    LogInfo("discovery_held", null, $"failures={_connectionFailures}, reason={(_appPaused ? "app paused" : "recent wake, waiting for Wi-Fi")}");
                }
                else if (!nudged && _connectionFailures >= FailuresBeforeDiscovery)
                {
                    // The saved server is not answering. Look around for a server on the
                    // subnet, but keep the saved address unless something else answers —
                    // throwing it away used to force a full 254-host scan after every short
                    // server restart and made devices come back one by one.
                    _connectionFailures = 0;
                    string discovered = await RunDiscovery(token).ConfigureAwait(false);
                    if (token.IsCancellationRequested) break;

                    if (!string.IsNullOrEmpty(discovered) && discovered != _savedServerAddress)
                    {
                        LogInfo("discovery_switch", null, $"from={SafeValue(_savedServerAddress)}, to={discovered}");
                        SaveServerAddress(discovered);
                    }
                }

                if (token.IsCancellationRequested) break;

                float delay = nudged ? NudgeReconnectDelay : ReconnectDelay;
                LogVerbose("reconnect_scheduled", null, $"attempt={_reconnectAttempt}, retryInSec={delay}, failures={_connectionFailures}");
                if (!await DelaySafe(delay, token).ConfigureAwait(false)) break;
            }

            LogInfo("connection_loop_exit", null, "cancelled");
        }

        /// <summary>
        /// Waits up to <paramref name="seconds"/>, returning early when NudgeReconnect()
        /// fires. Returns false only when the component is being destroyed.
        /// </summary>
        private async Task<bool> DelaySafe(float seconds, CancellationToken token)
        {
            try
            {
                await _wake.WaitAsync(TimeSpan.FromSeconds(seconds), token).ConfigureAwait(false);
                return true;
            }
            catch (OperationCanceledException)
            {
                return false;
            }
            catch (ObjectDisposedException)
            {
                return false;
            }
        }

        private async Task<string> RunDiscovery(CancellationToken token)
        {
            _discoveryAttempt++;
            LogInfo("discovery_start", null, $"attempt={_discoveryAttempt}");
            try
            {
                string discovered = await DiscoverServer(token).ConfigureAwait(false);
                if (!string.IsNullOrEmpty(discovered))
                    LogInfo("discovery_success", null, $"attempt={_discoveryAttempt}, discovered={discovered}");
                return discovered;
            }
            catch (OperationCanceledException)
            {
                return null;
            }
            catch (Exception e)
            {
                LogWarning("discovery_error", null, $"attempt={_discoveryAttempt}, reason={e.GetType().Name}: {e.Message}");
                return null;
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
                await Task.WhenAny(foundServer.Task, allDone).ConfigureAwait(false);

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
            if (found.Task.IsCompleted) return;

            await semaphore.WaitAsync(token).ConfigureAwait(false);
            try
            {
                // Stop scanning as soon as the headset goes to sleep.
                if (found.Task.IsCompleted || _appPaused) return;

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

        // ─── WebSocket session ──────────────────────────────────────────────

        private async Task ConnectAndRun(string serverUrl, CancellationToken token)
        {
            var sessionCts = CancellationTokenSource.CreateLinkedTokenSource(token);
            var ws = new ClientWebSocket();
            try
            {
                // Client-side keep-alive pings: lets a half-open Wi-Fi link be detected in
                // seconds instead of waiting for the OS TCP timeout.
                ws.Options.KeepAliveInterval = TimeSpan.FromSeconds(15);
            }
            catch (Exception e)
            {
                LogVerbose("keepalive_unsupported", null, e.Message);
            }

            lock (_wsLock)
            {
                CloseWebSocketLocked();
                _ws = ws;
                _sessionCts = sessionCts;
            }

            try
            {
                Debug.Log($"[ServerConnection] Connecting to {serverUrl}...");
                await ws.ConnectAsync(new Uri(serverUrl), sessionCts.Token).ConfigureAwait(false);
                Debug.Log($"[ServerConnection] Connected to {serverUrl}");

                await SendRegister(ws, sessionCts.Token).ConfigureAwait(false);
                // Real status right away: the dashboard should show playing/paused
                // immediately after a reconnect rather than "idle" until the next heartbeat.
                await SendStatus(ws, sessionCts.Token).ConfigureAwait(false);

                _connectionFailures = 0;
                _connected = true;

                var buffer = new byte[ReceiveBufferSize];
                var messageBuilder = new StringBuilder();

                while (ws.State == WebSocketState.Open && !sessionCts.IsCancellationRequested)
                {
                    var result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), sessionCts.Token).ConfigureAwait(false);

                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        Debug.Log($"[ServerConnection] Server closed connection ({result.CloseStatus}: {result.CloseStatusDescription})");
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
            finally
            {
                _connected = false;
                lock (_wsLock)
                {
                    if (ReferenceEquals(_ws, ws))
                    {
                        _ws = null;
                        _sessionCts = null;
                    }
                }
                try { ws.Dispose(); } catch { }
                try { sessionCts.Dispose(); } catch { }
            }
        }

        private Task SendRegister(ClientWebSocket ws, CancellationToken token)
        {
            string statusJson = statusReporter != null ? statusReporter.GetStatusJson() : "{}";
            string message = WrapWithType("register", statusJson);
            LogInfo("register_send", null, $"deviceId={_deviceId}, name='{StatusReporter.DeviceName}'");
            return SendText(ws, message, token);
        }

        private Task SendStatus(ClientWebSocket ws, CancellationToken token)
        {
            string statusJson = statusReporter != null ? statusReporter.GetStatusJson() : "{}";
            return SendText(ws, WrapWithType("status", statusJson), token);
        }

        private static string WrapWithType(string type, string statusJson)
        {
            if (string.IsNullOrEmpty(statusJson) || statusJson.Length < 2 || statusJson[0] != '{')
                return "{\"type\":\"" + type + "\"}";
            if (statusJson == "{}")
                return "{\"type\":\"" + type + "\"}";
            return "{\"type\":\"" + type + "\"," + statusJson.Substring(1);
        }

        private async void SendHeartbeat()
        {
            ClientWebSocket ws;
            lock (_wsLock)
            {
                ws = _ws;
            }
            if (ws == null || ws.State != WebSocketState.Open) return;

            // Skip this tick if the previous heartbeat is still being flushed (slow Wi-Fi)
            // instead of queueing up sends.
            if (Interlocked.CompareExchange(ref _heartbeatInFlight, 1, 0) != 0)
            {
                LogVerbose("heartbeat_skipped", null, "previous heartbeat still in flight");
                return;
            }

            try
            {
                // Called from Update(): GetStatusJson() rebuilds on the main thread here.
                await SendStatus(ws, _cts?.Token ?? CancellationToken.None).ConfigureAwait(false);
            }
            catch (Exception e)
            {
                LogVerbose("heartbeat_failed", null, e.Message);
                // The receive loop notices a dead socket and the connection loop reconnects;
                // nothing else to do here.
            }
            finally
            {
                Interlocked.Exchange(ref _heartbeatInFlight, 0);
            }
        }

        private async Task SendText(ClientWebSocket ws, string text, CancellationToken token)
        {
            if (ws == null || ws.State != WebSocketState.Open) return;

            var bytes = Encoding.UTF8.GetBytes(text);

            // ClientWebSocket allows only one outstanding SendAsync per socket.
            await _sendLock.WaitAsync(token).ConfigureAwait(false);
            try
            {
                if (ws.State != WebSocketState.Open) return;
                await ws.SendAsync(
                    new ArraySegment<byte>(bytes),
                    WebSocketMessageType.Text,
                    true,
                    token
                ).ConfigureAwait(false);
            }
            finally
            {
                _sendLock.Release();
            }
        }

        private void CloseWebSocketLocked()
        {
            var ws = _ws;
            if (ws == null) return;
            _ws = null;
            _sessionCts = null;

            try
            {
                if (ws.State == WebSocketState.Open)
                {
                    // Fire-and-forget close handshake; Dispose below aborts if it stalls.
                    _ = ws.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "closing", CancellationToken.None);
                }
            }
            catch { }
            try { ws.Dispose(); } catch { }
        }

        // ─── Command Handling ───────────────────────────────────────────────

        private void HandleServerMessage(string raw)
        {
            int rawLength = raw?.Length ?? 0;

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
                    LogVerbose("message_ignored", null, $"type={SafeValue(command.type)}");
                    return;
                }

                if (string.IsNullOrWhiteSpace(command.action))
                {
                    Debug.LogWarning("[ServerConnection] Ignoring command: 'action' is missing or empty");
                    return;
                }

                string commandId = ResolveCommandId(command);
                LogInfo("command_received", commandId, $"action={command.action}, rawLength={rawLength}, preview={CreatePayloadPreview(raw)}");
                _mainThreadQueue.Enqueue(() => ExecuteCommand(command, raw));
            }
            catch (Exception e)
            {
                LogWarning("message_dropped", null,
                    $"reason=invalid json, rawLength={rawLength}, preview={CreatePayloadPreview(raw)}, parseError={e.GetType().Name}: {e.Message}");
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
                            string placementMode = command.placementMode;
                            bool loop = command.loop;
                            bool autoRecenterOnOpen = command.autoRecenterOnOpen;
                            LogInfo("command_start", commandId,
                                $"action=open, file={SafeValue(file)}, mode={SafeValue(mode)}, placementMode={SafeValue(placementMode)}, loop={loop}");

                            if (string.IsNullOrEmpty(file))
                            {
                                Debug.LogWarning("[ServerConnection] OPEN command ignored: 'file' is missing or empty");
                                break;
                            }

                            ViewMode targetMode = viewModeManager != null ? viewModeManager.CurrentMode : PlayerConfig.DefaultViewMode;
                            if (viewModeManager != null && !string.IsNullOrEmpty(mode))
                            {
                                targetMode = ViewModeParser.Parse(mode);
                                if (targetMode != viewModeManager.CurrentMode)
                                    viewModeManager.SetMode(targetMode);
                            }

                            if (viewModeManager != null)
                            {
                                viewModeManager.ApplyAdvancedSettingsOverride(targetMode, command.advancedSettings);
                                viewModeManager.ApplyPlacementOverride(targetMode, placementMode);
                            }

                            if (autoRecenterOnOpen)
                            {
                                orientationManager?.Recenter();
                            }

                            if (videoPlayer != null)
                            {
                                videoPlayer.IsLooping = loop;
                                videoPlayer.Open(file);
                            }

                            LogInfo("command_end", commandId, $"action=open, file={SafeValue(file)}");
                            _sendStatusNow = true;
                            break;
                        }
                    case "play":
                        LogInfo("command_start", commandId, "action=play");
                        videoPlayer?.Play();
                        _sendStatusNow = true;
                        break;
                    case "pause":
                        LogInfo("command_start", commandId, "action=pause");
                        videoPlayer?.Pause();
                        _sendStatusNow = true;
                        break;
                    case "stop":
                        LogInfo("command_start", commandId, "action=stop");
                        videoPlayer?.Stop();
                        if (viewModeManager != null)
                            viewModeManager.SetMode(ViewMode.None);
                        _sendStatusNow = true;
                        break;
                    case "recenter":
                        LogInfo("command_start", commandId, "action=recenter");
                        orientationManager?.Recenter();
                        break;
                    case "set_volume":
                        {
                            float globalVol = HasJsonField(raw, "globalVolume") ? command.globalVolume : 1f;
                            float personalVol = HasJsonField(raw, "personalVolume") ? command.personalVolume : 1f;
                            LogInfo("command_start", commandId,
                                $"action=set_volume, globalVolume={globalVol}, personalVolume={personalVol}");
                            videoPlayer?.SetVolume(globalVol, personalVol);
                            _sendStatusNow = true;
                            break;
                        }
                    case "seek":
                        {
                            float seekTime = HasJsonField(raw, "time") ? command.time : 0f;
                            LogInfo("command_start", commandId, $"action=seek, time={seekTime}");
                            videoPlayer?.Seek(seekTime);
                            _sendStatusNow = true;
                            break;
                        }
                    case "set_mode":
                        {
                            string mode = command.mode;
                            LogInfo("command_start", commandId, $"action=set_mode, mode={SafeValue(mode)}");
                            if (viewModeManager != null && !string.IsNullOrEmpty(mode))
                            {
                                ViewMode vm = ViewModeParser.Parse(mode);
                                viewModeManager.SetMode(vm);
                            }
                            break;
                        }
                    case "set_name":
                        {
                            if (!HasJsonField(raw, "name"))
                            {
                                Debug.LogWarning("[ServerConnection] set_name ignored: 'name' field missing");
                                break;
                            }
                            string name = command.name ?? string.Empty;
                            LogInfo("command_start", commandId, $"action=set_name, name='{name}'");
                            // Persisted on the headset; OnDeviceNameChanged triggers an
                            // immediate status push so the server can confirm it.
                            StatusReporter.SetDeviceName(name);
                            _sendStatusNow = true;
                            break;
                        }
                    case "sleep":
                        LogInfo("command_start", commandId, "action=sleep");
                        videoPlayer?.Stop();
                        if (viewModeManager != null)
                            viewModeManager.SetMode(ViewMode.None);
                        _sleepRequested = true;
                        _keepAwake = false;
                        PlayerSystem.Sleep();
                        break;
                    case "ping":
                        LogInfo("command_start", commandId, "action=ping");
                        PingSound.Play(gameObject);
                        break;
                    case "update":
                        {
                            // url is a server path ("/api/player/apk"): resolve it against the
                            // server we are connected to, so the server never has to guess its own IP.
                            string url = command.url ?? string.Empty;
                            if (url.StartsWith("/"))
                            {
                                string server = _savedServerAddress ?? string.Empty;
                                if (!server.Contains(":")) server += ":" + ServerPort;
                                url = $"http://{server}{url}";
                            }
                            LogInfo("command_start", commandId, $"action=update, url={SafeValue(url)}");
                            if (string.IsNullOrEmpty(command.url) || string.IsNullOrEmpty(command.sha256))
                            {
                                Debug.LogWarning("[ServerConnection] update ignored: 'url' or 'sha256' missing");
                                break;
                            }
                            StartUpdate(url, command.sha256.Trim().ToLowerInvariant(), commandId);
                            break;
                        }
                    case "apply_settings":
                        if (!HasJsonField(raw, "settings"))
                        {
                            Debug.LogWarning("[ServerConnection] apply_settings ignored: 'settings' field missing");
                            break;
                        }
                        StatusReporter.SettingsProfile = PlayerSystem.ApplySettings(command.settings);
                        LogInfo("command_start", commandId, $"action=apply_settings, result={StatusReporter.SettingsProfile}");
                        _sendStatusNow = true;
                        break;
                    case "toggle_debug":
                        {
                            LogInfo("command_start", commandId, "action=toggle_debug");
                            var debugPanel = FindFirstObjectByTypeCompat<DebugLogPanel>();
                            if (debugPanel != null) debugPanel.Toggle();
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

        /// <summary>
        /// Self-update: skip if the installed APK already has sha256, else download it here
        /// (Mono sockets may use plain HTTP; Java may not) and hand the file to Java to install.
        /// </summary>
        private void StartUpdate(string url, string sha256, string commandId)
        {
            if (Interlocked.CompareExchange(ref _updateInFlight, 1, 0) != 0)
            {
                LogWarning("update_skipped", commandId, "an update is already running");
                return;
            }

            string installedApk = PlayerSystem.InstalledApkPath();
            string downloadPath = System.IO.Path.Combine(Application.temporaryCachePath, "player-update.apk");
            Task.Run(async () =>
            {
                try
                {
                    if (!string.IsNullOrEmpty(installedApk) && Sha256Of(installedApk) == sha256)
                    {
                        LogInfo("update_skipped", commandId, "installed APK already matches");
                        return;
                    }

                    var request = WebRequest.CreateHttp(url);
                    request.Timeout = 30000;
                    request.ReadWriteTimeout = 60000;
                    using (var response = await request.GetResponseAsync().ConfigureAwait(false))
                    using (var source = response.GetResponseStream())
                    using (var target = System.IO.File.Create(downloadPath))
                    {
                        await source.CopyToAsync(target).ConfigureAwait(false);
                    }

                    LogInfo("update_downloaded", commandId, downloadPath);
                    _mainThreadQueue.Enqueue(() => PlayerSystem.InstallUpdate(downloadPath, sha256));
                }
                catch (Exception e)
                {
                    LogWarning("update_failed", commandId, $"{e.GetType().Name}: {e.Message}");
                }
                finally
                {
                    Interlocked.Exchange(ref _updateInFlight, 0);
                }
            });
        }

        private static string Sha256Of(string path)
        {
            using (var sha = System.Security.Cryptography.SHA256.Create())
            using (var stream = System.IO.File.OpenRead(path))
            {
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            }
        }

        private static T FindFirstObjectByTypeCompat<T>() where T : UnityEngine.Object
        {
#if UNITY_6000_0_OR_NEWER
            return FindFirstObjectByType<T>();
#else
            return FindObjectOfType<T>();
#endif
        }

        // ─── Minimal JSON fallback helpers ───────────────────────────────────

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
            // Cached in Start(): PlayerPrefs must not be read from the thread pool.
            if (!_verboseLogs)
                return;

            LogInfo(stage, commandId, details);
        }
    }
}
