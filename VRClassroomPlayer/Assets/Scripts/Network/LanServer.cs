using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using UnityEngine;

namespace VRClassroom
{
    public class LanServer : MonoBehaviour
    {
        [SerializeField] private VideoPlayerController videoPlayer;
        [SerializeField] private ViewModeManager viewModeManager;
        [SerializeField] private OrientationManager orientationManager;
        [SerializeField] private StatusReporter statusReporter;
        [SerializeField] private DebugLogPanel debugLogPanel;

        private HttpListener _listener;
        private Thread _listenerThread;
        private volatile bool _isRunning;
        private readonly ConcurrentQueue<Action> _mainThreadQueue = new ConcurrentQueue<Action>();

        // For request-response synchronization (status/battery requests)
        private readonly ConcurrentQueue<PendingResponse> _pendingResponses = new ConcurrentQueue<PendingResponse>();

        private const int MaxRetries = 3;
        private const int RetryDelayMs = 5000;

        private void Start()
        {
            Debug.Log("[LanServer] Initializing...");
            if (videoPlayer == null) Debug.LogError("[LanServer] VideoPlayerController reference is NOT assigned!");
            if (viewModeManager == null) Debug.LogError("[LanServer] ViewModeManager reference is NOT assigned!");
            if (orientationManager == null) Debug.LogError("[LanServer] OrientationManager reference is NOT assigned!");
            if (statusReporter == null) Debug.LogError("[LanServer] StatusReporter reference is NOT assigned!");
            if (debugLogPanel == null) Debug.LogWarning("[LanServer] DebugLogPanel reference is not assigned (debug toggle will not work).");
            StartServer();
        }

        private void Update()
        {
            // Process queued actions on the main thread
            while (_mainThreadQueue.TryDequeue(out Action action))
            {
                try
                {
                    action?.Invoke();
                }
                catch (Exception e)
                {
                    Debug.LogError($"[LanServer] Error executing queued action: {e.Message}");
                }
            }
        }

        private void OnDestroy()
        {
            StopServer();
        }

        private void StartServer()
        {
            _listenerThread = new Thread(ListenerLoop)
            {
                IsBackground = true,
                Name = "LanServer"
            };
            _isRunning = true;
            _listenerThread.Start();
        }

        private void StopServer()
        {
            _isRunning = false;

            if (_listener != null)
            {
                try
                {
                    _listener.Stop();
                    _listener.Close();
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[LanServer] Error stopping listener: {e.Message}");
                }
                _listener = null;
            }

            if (_listenerThread != null && _listenerThread.IsAlive)
            {
                _listenerThread.Join(2000);
            }
        }

        private void ListenerLoop()
        {
            int retries = 0;

            while (_isRunning && retries < MaxRetries)
            {
                try
                {
                    _listener = new HttpListener();
                    _listener.Prefixes.Add($"http://*:{PlayerConfig.HttpPort}/");
                    _listener.Start();

                    Debug.Log($"[LanServer] HTTP server started on port {PlayerConfig.HttpPort}");
                    retries = 0; // Reset retries on success

                    while (_isRunning && _listener.IsListening)
                    {
                        try
                        {
                            var context = _listener.GetContext();
                            HandleRequest(context);
                        }
                        catch (HttpListenerException) when (!_isRunning)
                        {
                            // Expected when stopping
                            break;
                        }
                        catch (Exception e)
                        {
                            if (_isRunning)
                                Debug.LogWarning($"[LanServer] Request error: {e.Message}");
                        }
                    }
                }
                catch (HttpListenerException e)
                {
                    retries++;
                    Debug.LogError($"[LanServer] Failed to start on port {PlayerConfig.HttpPort}: {e.Message} (attempt {retries}/{MaxRetries})");

                    if (retries < MaxRetries && _isRunning)
                    {
                        Thread.Sleep(RetryDelayMs);
                    }
                }
                catch (Exception e)
                {
                    Debug.LogError($"[LanServer] Unexpected error: {e.Message}");
                    break;
                }
            }

            Debug.Log("[LanServer] Listener thread exiting.");
        }

        private void HandleRequest(HttpListenerContext context)
        {
            var request = context.Request;
            var response = context.Response;
            string path = request.Url.AbsolutePath.TrimEnd('/').ToLowerInvariant();
            string method = request.HttpMethod.ToUpperInvariant();

            Debug.Log($"[LanServer] {method} {path} from {request.RemoteEndPoint}");

            try
            {
                // GET endpoints — can be answered directly from the listener thread
                if (method == "GET")
                {
                    switch (path)
                    {
                        case "/status":
                            HandleGetStatus(response);
                            return;
                        case "/battery":
                            HandleGetBattery(response);
                            return;
                        case "/files":
                            HandleGetFiles(response);
                            return;
                        case "/debug":
                            HandleGetDebugToggle(response);
                            return;
                    }
                }

                // POST endpoints — queue to main thread
                if (method == "POST")
                {
                    string body = null;
                    if (request.HasEntityBody)
                    {
                        using (var reader = new StreamReader(request.InputStream, request.ContentEncoding))
                        {
                            body = reader.ReadToEnd();
                        }
                    }

                    Debug.Log($"[LanServer] POST {path} body: {body ?? "(empty)"}");

                    switch (path)
                    {
                        case "/play":
                            QueueCommand(() =>
                            {
                                Debug.Log("[LanServer] Executing: play");
                                videoPlayer?.Play();
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/pause":
                            QueueCommand(() =>
                            {
                                Debug.Log("[LanServer] Executing: pause");
                                videoPlayer?.Pause();
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/restart":
                            QueueCommand(() =>
                            {
                                Debug.Log("[LanServer] Executing: restart");
                                videoPlayer?.Restart();
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/stop":
                            QueueCommand(() =>
                            {
                                Debug.Log("[LanServer] Executing: stop");
                                videoPlayer?.Stop();
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/open":
                            HandlePostOpen(response, body);
                            return;
                        case "/recenter":
                            QueueCommand(() =>
                            {
                                Debug.Log("[LanServer] Executing: recenter");
                                orientationManager?.Recenter();
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/lock":
                            QueueCommand(() =>
                            {
                                Debug.Log("[LanServer] Executing: lock");
                                var sm = PlayerStateManager.Instance;
                                if (sm != null) sm.IsLocked = true;
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/unlock":
                            QueueCommand(() =>
                            {
                                Debug.Log("[LanServer] Executing: unlock");
                                var sm = PlayerStateManager.Instance;
                                if (sm != null) sm.IsLocked = false;
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/emergencystop":
                            QueueCommand(() =>
                            {
                                Debug.Log("[LanServer] Executing: emergencystop");
                                videoPlayer?.Stop();
                                var sm = PlayerStateManager.Instance;
                                if (sm != null) sm.IsLocked = false;
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/ping":
                            QueueCommand(() =>
                            {
                                Debug.Log("[LanServer] Executing: ping (audio beep)");
                                PlayPingSound();
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/debug":
                            HandlePostDebugToggle(response, body);
                            return;
                    }
                }

                // Unknown route
                Debug.LogWarning($"[LanServer] Unknown route: {method} {path}");
                SendJson(response, 404, "{\"error\":\"not found\"}");
            }
            catch (Exception e)
            {
                Debug.LogError($"[LanServer] Error handling {method} {path}: {e.Message}");
                try
                {
                    SendJson(response, 500, $"{{\"error\":\"{EscapeJson(e.Message)}\"}}");
                }
                catch { /* Response may already be closed */ }
            }
        }

        private void HandlePostOpen(HttpListenerResponse response, string body)
        {
            if (string.IsNullOrEmpty(body))
            {
                Debug.LogWarning("[LanServer] POST /open: missing body");
                SendJson(response, 400, "{\"error\":\"missing body\"}");
                return;
            }

            try
            {
                var data = JsonUtility.FromJson<OpenRequest>(body);
                if (string.IsNullOrEmpty(data.file))
                {
                    Debug.LogWarning("[LanServer] POST /open: missing file parameter");
                    SendJson(response, 400, "{\"error\":\"missing file parameter\"}");
                    return;
                }

                string file = data.file;
                string mode = data.mode;
                bool loop = data.loop;

                Debug.Log($"[LanServer] POST /open: file={file}, mode={mode ?? "(default)"}, loop={loop}");

                QueueCommand(() =>
                {
                    Debug.Log($"[LanServer] Executing: open file={file} mode={mode ?? "(default)"} loop={loop}");
                    if (!string.IsNullOrEmpty(mode) && viewModeManager != null)
                    {
                        viewModeManager.SetMode(ADBCommandRouter.ParseMode(mode));
                    }
                    if (videoPlayer != null)
                    {
                        videoPlayer.IsLooping = loop;
                    }
                    videoPlayer?.Open(file);
                });

                SendJson(response, 200, "{\"ok\":true}");
            }
            catch (Exception e)
            {
                Debug.LogError($"[LanServer] POST /open: invalid json: {e.Message}");
                SendJson(response, 400, $"{{\"error\":\"invalid json: {EscapeJson(e.Message)}\"}}");
            }
        }

        private void HandleGetStatus(HttpListenerResponse response)
        {
            // StatusReporter may need main-thread data, but GetStatusJson reads properties
            // that are set on the main thread; reading them from another thread is acceptable
            // for status reporting purposes (slightly stale data is fine).
            string json = "{}";
            if (statusReporter != null)
            {
                try
                {
                    json = statusReporter.GetStatusJson();
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[LanServer] Error getting status: {e.Message}");
                }
            }
            SendJson(response, 200, json);
        }

        private void HandleGetBattery(HttpListenerResponse response)
        {
            int battery = Mathf.RoundToInt(SystemInfo.batteryLevel * 100f);
            if (SystemInfo.batteryLevel < 0) battery = -1;
            bool charging = SystemInfo.batteryStatus == BatteryStatus.Charging;

            string json = $"{{\"battery\":{battery},\"charging\":{(charging ? "true" : "false")}}}";
            SendJson(response, 200, json);
        }

        private void HandleGetDebugToggle(HttpListenerResponse response)
        {
            bool currentState = false;
            QueueCommand(() =>
            {
                if (debugLogPanel != null)
                    debugLogPanel.Toggle();
            });

            string json = "{\"ok\":true,\"debug\":\"toggled\"}";
            SendJson(response, 200, json);
        }

        private void HandlePostDebugToggle(HttpListenerResponse response, string body)
        {
            QueueCommand(() =>
            {
                if (debugLogPanel != null)
                {
                    if (!string.IsNullOrEmpty(body) && body.Contains("\"on\""))
                        debugLogPanel.SetVisible(true);
                    else if (!string.IsNullOrEmpty(body) && body.Contains("\"off\""))
                        debugLogPanel.SetVisible(false);
                    else
                        debugLogPanel.Toggle();
                }
            });

            SendJson(response, 200, "{\"ok\":true}");
        }

        private void QueueCommand(Action action)
        {
            _mainThreadQueue.Enqueue(action);
        }

        private static void SendJson(HttpListenerResponse response, int statusCode, string json)
        {
            response.StatusCode = statusCode;
            response.ContentType = "application/json";
            byte[] buffer = Encoding.UTF8.GetBytes(json);
            response.ContentLength64 = buffer.Length;
            response.OutputStream.Write(buffer, 0, buffer.Length);
            response.OutputStream.Close();
        }

        private static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return s;
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        private void HandleGetFiles(HttpListenerResponse response)
        {
            try
            {
                string videoDir = PlayerConfig.VideoPath;
                var sb = new StringBuilder(1024);
                sb.Append("{\"files\":[");

                if (Directory.Exists(videoDir))
                {
                    string[] files = Directory.GetFiles(videoDir);
                    for (int i = 0; i < files.Length; i++)
                    {
                        if (i > 0) sb.Append(',');
                        var fi = new FileInfo(files[i]);
                        sb.Append('{');
                        sb.AppendFormat("\"name\":\"{0}\",", EscapeJson(fi.Name));
                        sb.AppendFormat("\"path\":\"{0}\",", EscapeJson(files[i]));
                        sb.AppendFormat("\"size\":{0}", fi.Length);
                        sb.Append('}');
                    }
                }

                sb.Append("]}");
                SendJson(response, 200, sb.ToString());
            }
            catch (Exception e)
            {
                Debug.LogError($"[LanServer] Error listing files: {e.Message}");
                SendJson(response, 500, $"{{\"error\":\"{EscapeJson(e.Message)}\"}}");
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
                Debug.LogWarning($"[LanServer] Ping sound failed: {e.Message}");
            }
        }

        [Serializable]
        private class OpenRequest
        {
            public string file;
            public string mode;
            public bool loop;
        }

        private class PendingResponse
        {
            public HttpListenerResponse Response;
            public string Json;
        }
    }
}
