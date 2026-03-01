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

                    switch (path)
                    {
                        case "/play":
                            QueueCommand(() => videoPlayer?.Play());
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/pause":
                            QueueCommand(() => videoPlayer?.Pause());
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/restart":
                            QueueCommand(() => videoPlayer?.Restart());
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/stop":
                            QueueCommand(() => videoPlayer?.Stop());
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/open":
                            return; // Handled below
                        case "/recenter":
                            QueueCommand(() => orientationManager?.Recenter());
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/lock":
                            QueueCommand(() =>
                            {
                                var sm = PlayerStateManager.Instance;
                                if (sm != null) sm.IsLocked = true;
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/unlock":
                            QueueCommand(() =>
                            {
                                var sm = PlayerStateManager.Instance;
                                if (sm != null) sm.IsLocked = false;
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                        case "/emergencystop":
                            QueueCommand(() =>
                            {
                                videoPlayer?.Stop();
                                var sm = PlayerStateManager.Instance;
                                if (sm != null) sm.IsLocked = false;
                            });
                            SendJson(response, 200, "{\"ok\":true}");
                            return;
                    }

                    // Handle /open separately since it needs body parsing
                    if (path == "/open")
                    {
                        HandlePostOpen(response, body);
                        return;
                    }
                }

                // Unknown route
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
                SendJson(response, 400, "{\"error\":\"missing body\"}");
                return;
            }

            try
            {
                var data = JsonUtility.FromJson<OpenRequest>(body);
                if (string.IsNullOrEmpty(data.file))
                {
                    SendJson(response, 400, "{\"error\":\"missing file parameter\"}");
                    return;
                }

                string file = data.file;
                string mode = data.mode;

                QueueCommand(() =>
                {
                    if (!string.IsNullOrEmpty(mode) && viewModeManager != null)
                    {
                        viewModeManager.SetMode(ADBCommandRouter.ParseMode(mode));
                    }
                    videoPlayer?.Open(file);
                });

                SendJson(response, 200, "{\"ok\":true}");
            }
            catch (Exception e)
            {
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

        [Serializable]
        private class OpenRequest
        {
            public string file;
            public string mode;
        }

        private class PendingResponse
        {
            public HttpListenerResponse Response;
            public string Json;
        }
    }
}
