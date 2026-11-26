using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// The player's link to the headset agent (Assets/Plugins/Android/Agent.java, process
    /// ":watchdog"), which alone talks to the instructor server. A local TCP socket,
    /// 127.0.0.1:8082, one JSON object per line - it never drops with Wi-Fi.
    ///
    /// Player -> agent: {"type":"register", ...status} on connect, then {"type":"status", ...}
    ///                  every HeartbeatInterval seconds and right after anything changes.
    /// Agent -> player: {"type":"command","action":"open|play|pause|stop|recenter|seek|set_volume|set_mode|set_name|sleep|ping|toggle_debug", ...}
    /// Discovery, keep-awake, self-update, content downloads and the settings profile all live
    /// in the agent, so they also work while the player is closed.
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
            public VideoAdvancedSettings advancedSettings;
        }

        [SerializeField] private StatusReporter statusReporter;
        [SerializeField] private VideoPlayerController videoPlayer;
        [SerializeField] private ViewModeManager viewModeManager;
        [SerializeField] private OrientationManager orientationManager;

        private const string AgentHost = "127.0.0.1";
        private const int AgentPort = 8082;
        private const float HeartbeatInterval = 5f;
        private const int ReconnectDelayMs = 1000;
        private const int MessagePreviewLength = 160;

        private readonly ConcurrentQueue<Action> _mainThreadQueue = new ConcurrentQueue<Action>();
        private readonly object _writeLock = new object();
        private CancellationTokenSource _cts;
        private volatile StreamWriter _writer;
        private volatile bool _connected;
        private volatile bool _sendStatusNow;
        private volatile bool _sendRegister;
        private float _lastHeartbeatTime;

        private void Start()
        {
            // Starts the watchdog + agent if the player was opened before they were running.
            PlayerSystem.StartWatchdog();
            StatusReporter.OnDeviceNameChanged += HandleDeviceNameChanged;
            _cts = new CancellationTokenSource();
            var token = _cts.Token;
            Task.Run(() => LinkLoop(token));
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

            if (!_connected) return;
            // GetStatusJson() must run on the main thread; the write is quick (localhost).
            if (_sendRegister)
            {
                _sendRegister = false;
                Send(WrapWithType("register", CurrentStatusJson()));
                _sendStatusNow = true;
            }
            if (_sendStatusNow || Time.time - _lastHeartbeatTime >= HeartbeatInterval)
            {
                _sendStatusNow = false;
                _lastHeartbeatTime = Time.time;
                Send(WrapWithType("status", CurrentStatusJson()));
            }
        }

        private string CurrentStatusJson()
        {
            return statusReporter != null ? statusReporter.GetStatusJson() : "{}";
        }

        private void OnApplicationFocus(bool hasFocus)
        {
            if (hasFocus) _sendStatusNow = true;
        }

        private void OnDestroy()
        {
            StatusReporter.OnDeviceNameChanged -= HandleDeviceNameChanged;
            _cts?.Cancel();
            CloseWriter();
        }

        private void HandleDeviceNameChanged(string name)
        {
            _sendStatusNow = true;
        }

        // ─── Link to the agent ──────────────────────────────────────────────

        private async Task LinkLoop(CancellationToken token)
        {
            bool loggedWaiting = false;
            while (!token.IsCancellationRequested)
            {
                try
                {
                    using (var client = new TcpClient())
                    {
                        client.NoDelay = true;
                        await client.ConnectAsync(AgentHost, AgentPort).ConfigureAwait(false);
                        using (var stream = client.GetStream())
                        using (var reader = new StreamReader(stream, new UTF8Encoding(false)))
                        {
                            _writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true, NewLine = "\n" };
                            _sendRegister = true;
                            _connected = true;
                            loggedWaiting = false;
                            LogInfo("agent_connected", null, $"{AgentHost}:{AgentPort}");

                            while (!token.IsCancellationRequested)
                            {
                                string line = await reader.ReadLineAsync().ConfigureAwait(false);
                                if (line == null) break;
                                if (line.Length > 0) HandleServerMessage(line);
                            }
                        }
                    }
                }
                catch (Exception e)
                {
                    if (!loggedWaiting)
                    {
                        // In the Editor there is no agent: say it once, not every second.
                        LogWarning("agent_unavailable", null, $"{e.GetType().Name}: {e.Message}");
                        loggedWaiting = true;
                    }
                }
                finally
                {
                    if (_connected) LogInfo("agent_disconnected", null, "reconnecting");
                    _connected = false;
                    CloseWriter();
                }

                try { await Task.Delay(ReconnectDelayMs, token).ConfigureAwait(false); }
                catch (OperationCanceledException) { break; }
            }
        }

        private void Send(string line)
        {
            var writer = _writer;
            if (writer == null) return;
            try
            {
                lock (_writeLock) writer.WriteLine(line);
            }
            catch (Exception e)
            {
                LogWarning("send_failed", null, e.Message);
                _connected = false; // the reader sees the closed socket and the loop reconnects
            }
        }

        private void CloseWriter()
        {
            var writer = _writer;
            _writer = null;
            try { writer?.Dispose(); } catch { }
        }

        private static string WrapWithType(string type, string statusJson)
        {
            if (string.IsNullOrEmpty(statusJson) || statusJson.Length < 2 || statusJson[0] != '{' || statusJson == "{}")
                return "{\"type\":\"" + type + "\"}";
            return "{\"type\":\"" + type + "\"," + statusJson.Substring(1);
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
                    return;

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
                    case "sleep": // the agent puts the headset to sleep; the player only stops the video
                        LogInfo("command_start", commandId, $"action={action}");
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
                            // The agent owns the name; the player keeps a copy for its HUD.
                            string name = command.name ?? string.Empty;
                            LogInfo("command_start", commandId, $"action=set_name, name='{name}'");
                            StatusReporter.SetDeviceName(name);
                            _sendStatusNow = true;
                            break;
                        }
                    case "ping":
                        LogInfo("command_start", commandId, "action=ping");
                        PingSound.Play(gameObject);
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
    }
}
