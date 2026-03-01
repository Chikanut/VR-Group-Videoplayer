using System;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace VRClassroom
{
    public class StatusReporter : MonoBehaviour
    {
        [SerializeField] private VideoPlayerController videoPlayer;
        [SerializeField] private ViewModeManager viewModeManager;

        private float _lastReportTime;
        private string _pushEndpoint;

        private void Start()
        {
            // Check for instructor push endpoint
            _pushEndpoint = PlayerPrefs.GetString("instructor_ip", string.Empty);
        }

        private void Update()
        {
            if (Time.time - _lastReportTime < PlayerConfig.StatusInterval)
                return;

            _lastReportTime = Time.time;

            // Only auto-report if not Idle
            if (videoPlayer != null && videoPlayer.CurrentState != PlayerState.Idle)
            {
                ReportNow();
            }

            // Push to instructor if configured
            if (!string.IsNullOrEmpty(_pushEndpoint))
            {
                PushStatus();
            }
        }

        public void ReportNow()
        {
            string json = GetStatusJson();

#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var logClass = new AndroidJavaClass("android.util.Log"))
                {
                    logClass.CallStatic<int>("i", "VRPlayer", json);
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[StatusReporter] Android Log failed: {e.Message}");
            }
#else
            Debug.Log($"[VRPlayer] {json}");
#endif
        }

        public string GetStatusJson()
        {
            string state = "idle";
            string file = "";
            string mode = "2d";
            float time = 0f;
            float duration = 0f;
            bool loop = false;
            bool locked = false;

            if (videoPlayer != null)
            {
                state = videoPlayer.CurrentState.ToString().ToLowerInvariant();
                file = videoPlayer.CurrentFile ?? "";
                time = videoPlayer.CurrentTime;
                duration = videoPlayer.Duration;
                loop = videoPlayer.IsLooping;
            }

            if (viewModeManager != null)
            {
                mode = viewModeManager.CurrentMode == ViewMode.Sphere360 ? "360" : "2d";
            }

            var stateManager = PlayerStateManager.Instance;
            if (stateManager != null)
            {
                locked = stateManager.IsLocked;
            }

            int battery = GetBatteryPercent();
            bool charging = GetBatteryCharging();
            string deviceId = GetDeviceId();
            string ip = GetLocalIPAddress();
            int uptimeMinutes = Mathf.FloorToInt(Time.realtimeSinceStartup / 60f);

            // Build JSON manually to avoid external dependencies
            var sb = new StringBuilder(512);
            sb.Append('{');
            sb.AppendFormat("\"deviceId\":\"{0}\",", EscapeJson(deviceId));
            sb.AppendFormat("\"ip\":\"{0}\",", EscapeJson(ip));
            sb.Append("\"online\":true,");
            sb.AppendFormat("\"state\":\"{0}\",", EscapeJson(state));
            sb.AppendFormat("\"file\":\"{0}\",", EscapeJson(file));
            sb.AppendFormat("\"mode\":\"{0}\",", EscapeJson(mode));
            sb.AppendFormat("\"time\":{0:F1},", time);
            sb.AppendFormat("\"duration\":{0:F1},", duration);
            sb.AppendFormat("\"loop\":{0},", loop ? "true" : "false");
            sb.AppendFormat("\"locked\":{0},", locked ? "true" : "false");
            sb.AppendFormat("\"battery\":{0},", battery);
            sb.AppendFormat("\"batteryCharging\":{0},", charging ? "true" : "false");
            sb.AppendFormat("\"uptimeMinutes\":{0}", uptimeMinutes);
            sb.Append('}');

            return sb.ToString();
        }

        private void PushStatus()
        {
            string ip = PlayerPrefs.GetString("instructor_ip", string.Empty);
            if (string.IsNullOrEmpty(ip)) return;

            string url = $"http://{ip}:9090/device_status";
            string json = GetStatusJson();

            try
            {
                var request = new UnityWebRequest(url, "POST");
                byte[] bodyRaw = Encoding.UTF8.GetBytes(json);
                request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                request.timeout = 2;
                request.SendWebRequest();
                // Fire and forget — we don't wait for the result
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[StatusReporter] Push to instructor failed: {e.Message}");
            }
        }

        private static int GetBatteryPercent()
        {
            float level = SystemInfo.batteryLevel;
            if (level < 0) return -1;
            return Mathf.RoundToInt(level * 100f);
        }

        private static bool GetBatteryCharging()
        {
            return SystemInfo.batteryStatus == BatteryStatus.Charging;
        }

        private static string GetDeviceId()
        {
            string saved = PlayerPrefs.GetString("device_id", string.Empty);
            if (!string.IsNullOrEmpty(saved)) return saved;

            string uid = SystemInfo.deviceUniqueIdentifier;
            if (!string.IsNullOrEmpty(uid) && uid.Length >= 4)
                return uid.Substring(uid.Length - 4);

            return SystemInfo.deviceName;
        }

        public static string GetLocalIPAddress()
        {
            try
            {
                foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
                {
                    if (ni.OperationalStatus != OperationalStatus.Up) continue;
                    if (ni.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;

                    foreach (var addr in ni.GetIPProperties().UnicastAddresses)
                    {
                        if (addr.Address.AddressFamily == AddressFamily.InterNetwork)
                        {
                            string ip = addr.Address.ToString();
                            if (!ip.StartsWith("127.")) return ip;
                        }
                    }
                }
            }
            catch
            {
                // Network API not available
            }

            return "0.0.0.0";
        }

        private static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return s;
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }
    }
}
