using System;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using System.Globalization;

namespace VRClassroom
{
    public class StatusReporter : MonoBehaviour
    {
        [SerializeField] private VideoPlayerController videoPlayer;
        [SerializeField] private ViewModeManager viewModeManager;

        private float _lastReportTime;
        private float _lastRegistrationTime;
        private string _pushEndpoint;
        private const float RegistrationInterval = 10f;
        public const string PlayerVersion = "1.0.0";

        private void Start()
        {
            // Check for instructor push endpoint
            _pushEndpoint = PlayerPrefs.GetString("instructor_ip", string.Empty);

            if (videoPlayer == null)
                Debug.LogError("[StatusReporter] VideoPlayerController reference is NOT assigned!");
            else
                Debug.Log("[StatusReporter] VideoPlayerController reference OK.");

            if (viewModeManager == null)
                Debug.LogError("[StatusReporter] ViewModeManager reference is NOT assigned!");
            else
                Debug.Log("[StatusReporter] ViewModeManager reference OK.");

            string ip = GetLocalIPAddress();
            string deviceId = GetDeviceId();
            Debug.Log($"[StatusReporter] Initialized. DeviceID={deviceId}, IP={ip}, InstructorIP={(_pushEndpoint == "" ? "(not set)" : _pushEndpoint)}");
        }

        private void Update()
        {
            if (Time.time - _lastReportTime >= PlayerConfig.StatusInterval)
            {
                _lastReportTime = Time.time;

                // Only auto-report if not Idle
                if (videoPlayer != null && videoPlayer.CurrentState != PlayerState.Idle)
                {
                    ReportNow();
                }
            }

            // Self-registration / heartbeat to instructor server
            if (!string.IsNullOrEmpty(_pushEndpoint) && Time.time - _lastRegistrationTime >= RegistrationInterval)
            {
                _lastRegistrationTime = Time.time;
                PushRegistration();
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
            string deviceName = GetDeviceName();
            string ip = GetLocalIPAddress();
            int uptimeMinutes = Mathf.FloorToInt(Time.realtimeSinceStartup / 60f);

            // Build JSON manually to avoid external dependencies
            var sb = new StringBuilder(512);
            sb.Append('{');
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"deviceId\":\"{0}\",", EscapeJson(deviceId));
            if (!string.IsNullOrEmpty(deviceName))
                sb.AppendFormat(CultureInfo.InvariantCulture, "\"deviceName\":\"{0}\",", EscapeJson(deviceName));
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"ip\":\"{0}\",", EscapeJson(ip));
            sb.Append("\"online\":true,");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"state\":\"{0}\",", EscapeJson(state));
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"file\":\"{0}\",", EscapeJson(file));
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"mode\":\"{0}\",", EscapeJson(mode));

            // Ось ці два рядки були головними винуватцями:
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"time\":{0:F1},", time);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"duration\":{0:F1},", duration);

            sb.AppendFormat(CultureInfo.InvariantCulture, "\"loop\":{0},", loop ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"locked\":{0},", locked ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"battery\":{0},", battery);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"batteryCharging\":{0},", charging ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"uptimeMinutes\":{0}", uptimeMinutes);
            sb.Append('}');

            return sb.ToString();
        }

        private void PushRegistration()
        {
            string server = PlayerPrefs.GetString("instructor_ip", string.Empty);
            if (string.IsNullOrEmpty(server)) return;

            // Support both "IP" and "IP:PORT" format
            string url;
            if (server.Contains(":"))
                url = $"http://{server}/api/devices/register";
            else
                url = $"http://{server}:8000/api/devices/register";

            string deviceId = GetDeviceId();
            string deviceName = GetDeviceName();
            string ip = GetLocalIPAddress();
            int battery = GetBatteryPercent();

            var sb = new StringBuilder(256);
            sb.Append('{');
            sb.AppendFormat("\"deviceId\":\"{0}\",", EscapeJson(deviceId));
            if (!string.IsNullOrEmpty(deviceName))
                sb.AppendFormat("\"deviceName\":\"{0}\",", EscapeJson(deviceName));
            sb.AppendFormat("\"ip\":\"{0}\",", EscapeJson(ip));
            sb.AppendFormat("\"battery\":{0},", battery);
            sb.AppendFormat("\"playerVersion\":\"{0}\",", EscapeJson(PlayerVersion));
            sb.Append("\"installedPackages\":[\"com.vrclassroom.player\"]");
            sb.Append('}');

            try
            {
                var request = new UnityWebRequest(url, "POST");
                byte[] bodyRaw = Encoding.UTF8.GetBytes(sb.ToString());
                request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                request.timeout = 3;
                request.SendWebRequest();
                // Fire and forget
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[StatusReporter] Registration push failed: {e.Message}");
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

            // Use full SystemInfo.deviceUniqueIdentifier for stable, collision-free ID.
            // Save to PlayerPrefs so it never changes for this device.
            string uid = SystemInfo.deviceUniqueIdentifier;
            if (!string.IsNullOrEmpty(uid) && uid != SystemInfo.unsupportedIdentifier)
            {
                PlayerPrefs.SetString("device_id", uid);
                PlayerPrefs.Save();
                return uid;
            }

            // Fallback: use device model + name as pseudo-unique ID
            string fallback = $"{SystemInfo.deviceModel}_{SystemInfo.deviceName}";
            PlayerPrefs.SetString("device_id", fallback);
            PlayerPrefs.Save();
            return fallback;
        }

        /// <summary>
        /// Returns the custom device name stored in PlayerPrefs, or empty if not set.
        /// </summary>
        public static string GetDeviceName()
        {
            return PlayerPrefs.GetString("device_name", string.Empty);
        }

        /// <summary>
        /// Saves a custom device name to PlayerPrefs so it persists across sessions.
        /// </summary>
        public static void SetDeviceName(string name)
        {
            PlayerPrefs.SetString("device_name", name ?? string.Empty);
            PlayerPrefs.Save();
            Debug.Log($"[StatusReporter] Device name saved: {name}");
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
