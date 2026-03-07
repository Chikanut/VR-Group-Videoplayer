using System;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using UnityEngine;
using System.Globalization;

namespace VRClassroom
{
    /// <summary>
    /// Utility class that collects device status into JSON.
    /// No longer pushes status via HTTP or logcat — that is handled by ServerConnection via WebSocket.
    /// </summary>
    public class StatusReporter : MonoBehaviour
    {
        [SerializeField] private VideoPlayerController videoPlayer;
        [SerializeField] private ViewModeManager viewModeManager;

        public string PlayerVersion => UnityEngine.Application.version;

        private void Start()
        {
            if (videoPlayer == null)
                Debug.LogError("[StatusReporter] VideoPlayerController reference is NOT assigned!");
            if (viewModeManager == null)
                Debug.LogError("[StatusReporter] ViewModeManager reference is NOT assigned!");

            string ip = GetLocalIPAddress();
            string deviceId = GetAndroidId();
            Debug.Log($"[StatusReporter] Initialized. DeviceID={deviceId}, IP={ip}");
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
            float globalVolume = 1f;
            float personalVolume = 1f;
            float effectiveVolume = 1f;

            if (videoPlayer != null)
            {
                state = videoPlayer.CurrentState.ToString().ToLowerInvariant();
                file = videoPlayer.CurrentFile ?? "";
                time = videoPlayer.CurrentTime;
                duration = videoPlayer.Duration;
                loop = videoPlayer.IsLooping;
                globalVolume = videoPlayer.GlobalVolume;
                personalVolume = videoPlayer.PersonalVolume;
                effectiveVolume = videoPlayer.EffectiveVolume;
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
            string deviceId = GetAndroidId();
            string deviceName = GetDeviceName();
            string ip = GetLocalIPAddress();
            int uptimeMinutes = Mathf.FloorToInt(Time.realtimeSinceStartup / 60f);

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
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"time\":{0:F1},", time);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"duration\":{0:F1},", duration);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"loop\":{0},", loop ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"locked\":{0},", locked ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"battery\":{0},", battery);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"batteryCharging\":{0},", charging ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"uptimeMinutes\":{0},", uptimeMinutes);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"globalVolume\":{0:F2},", globalVolume);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"personalVolume\":{0:F2},", personalVolume);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"effectiveVolume\":{0:F2},", effectiveVolume);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"playerVersion\":\"{0}\"", EscapeJson(PlayerVersion));
            sb.Append('}');

            return sb.ToString();
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
            catch (System.Exception e)
            {
                Debug.LogWarning($"[StatusReporter] Android Log failed: {e.Message}");
            }
        #else
            Debug.Log($"[VRPlayer] {json}");
        #endif
        }

        public static int GetBatteryPercent()
        {
            float level = SystemInfo.batteryLevel;
            if (level < 0) return -1;
            return Mathf.RoundToInt(level * 100f);
        }

        public static bool GetBatteryCharging()
        {
            return SystemInfo.batteryStatus == BatteryStatus.Charging;
        }

        /// <summary>
        /// Returns android_id via Android Settings.Secure API.
        /// This matches what the server reads via "adb shell settings get secure android_id".
        /// Falls back to SystemInfo.deviceUniqueIdentifier or PlayerPrefs.
        /// </summary>
        public static string GetAndroidId()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using (var activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
                using (var contentResolver = activity.Call<AndroidJavaObject>("getContentResolver"))
                using (var settingsSecure = new AndroidJavaClass("android.provider.Settings$Secure"))
                {
                    string androidId = settingsSecure.CallStatic<string>("getString", contentResolver, "android_id");
                    if (!string.IsNullOrEmpty(androidId) && androidId.ToLower() != "null")
                    {
                        return androidId;
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[StatusReporter] Failed to read android_id: {e.Message}");
            }
#endif
            // Fallback: use saved device_id or SystemInfo
            string saved = PlayerPrefs.GetString("device_id", string.Empty);
            if (!string.IsNullOrEmpty(saved)) return saved;

            string uid = SystemInfo.deviceUniqueIdentifier;
            if (!string.IsNullOrEmpty(uid) && uid != SystemInfo.unsupportedIdentifier)
            {
                PlayerPrefs.SetString("device_id", uid);
                PlayerPrefs.Save();
                return uid;
            }

            string fallback = $"{SystemInfo.deviceModel}_{SystemInfo.deviceName}";
            PlayerPrefs.SetString("device_id", fallback);
            PlayerPrefs.Save();
            return fallback;
        }

        public static string GetDeviceName()
        {
            return PlayerPrefs.GetString("device_name", string.Empty);
        }

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

        public static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return s;
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }
    }
}
