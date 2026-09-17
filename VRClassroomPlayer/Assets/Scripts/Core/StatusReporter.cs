using System;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using System.Globalization;

namespace VRClassroom
{
    /// <summary>
    /// Collects device status into JSON.
    ///
    /// Thread model: everything that touches Unity APIs (VideoPlayer, SystemInfo,
    /// PlayerPrefs, JNI) runs on the main thread. The HTTP listener thread and the
    /// WebSocket thread-pool continuations only ever read the cached JSON string,
    /// so a background request can never trip Unity's main-thread checks (which
    /// used to surface as an empty "{}" status and, on the server, as a device that
    /// suddenly lost its ID and name).
    /// </summary>
    public class StatusReporter : MonoBehaviour
    {
        /// <summary>Raised on the main thread whenever the persisted device name changes.</summary>
        public static event Action<string> OnDeviceNameChanged;

        /// <summary>Stable device ID (android_id), resolved once on the main thread.</summary>
        public static string DeviceId => _cachedDeviceId ?? string.Empty;

        /// <summary>Instructor-assigned name/number, persisted on the headset.</summary>
        public static string DeviceName => _cachedDeviceName ?? string.Empty;

        /// <summary>Last known LAN IPv4 address (refreshed periodically on the main thread).</summary>
        public static string LocalIp => _cachedIp ?? "0.0.0.0";

        [SerializeField] private VideoPlayerController videoPlayer;
        [SerializeField] private ViewModeManager viewModeManager;

        public string PlayerVersion => UnityEngine.Application.version;

        private const float StatusRefreshInterval = 0.5f;
        private const float IpRefreshInterval = 5f;
        private const string DeviceNamePrefKey = "device_name";
        private const string DeviceIdPrefKey = "device_id";

        private static volatile string _cachedDeviceId;
        private static volatile string _cachedDeviceName;
        private static volatile string _cachedIp;
        private static string _cachedDeviceModel = string.Empty;
        private static string _cachedMacAddress = string.Empty;
        private static int _mainThreadId = -1;

        private volatile string _cachedStatusJson = "{}";
        private float _nextStatusRefresh;
        private float _nextIpRefresh;
        private bool _dirty = true;

        private void Awake()
        {
            _mainThreadId = Thread.CurrentThread.ManagedThreadId;

            // Resolve static identity once, on the main thread.
            _cachedDeviceId = ResolveAndroidId();
            _cachedDeviceName = PlayerPrefs.GetString(DeviceNamePrefKey, string.Empty);
            _cachedDeviceModel = SystemInfo.deviceModel ?? string.Empty;
            _cachedMacAddress = ReadMacAddress();
            _cachedIp = ReadLocalIPAddress();

            RebuildStatusJson();
        }

        private void Start()
        {
            if (videoPlayer == null)
                Debug.LogError("[StatusReporter] VideoPlayerController reference is NOT assigned!");
            if (viewModeManager == null)
                Debug.LogError("[StatusReporter] ViewModeManager reference is NOT assigned!");

            if (videoPlayer != null)
                videoPlayer.OnStateChanged += HandleVideoStateChanged;
            if (viewModeManager != null)
                viewModeManager.OnModeChanged += HandleModeChanged;

            Debug.Log($"[StatusReporter] Initialized. DeviceID={_cachedDeviceId}, Name='{_cachedDeviceName}', IP={_cachedIp}");
        }

        private void OnDestroy()
        {
            if (videoPlayer != null)
                videoPlayer.OnStateChanged -= HandleVideoStateChanged;
            if (viewModeManager != null)
                viewModeManager.OnModeChanged -= HandleModeChanged;
        }

        private void Update()
        {
            float now = Time.unscaledTime;

            if (now >= _nextIpRefresh)
            {
                _nextIpRefresh = now + IpRefreshInterval;
                string ip = ReadLocalIPAddress();
                if (ip != _cachedIp)
                {
                    _cachedIp = ip;
                    _dirty = true;
                }
            }

            if (_dirty || now >= _nextStatusRefresh)
            {
                RebuildStatusJson();
            }
        }

        private void HandleVideoStateChanged(PlayerState state) => _dirty = true;
        private void HandleModeChanged(ViewMode mode) => _dirty = true;

        public static bool IsMainThread => _mainThreadId == Thread.CurrentThread.ManagedThreadId;

        /// <summary>
        /// Returns the status JSON. On the main thread the value is rebuilt on demand so
        /// heartbeats always carry fresh playback time; on any other thread the last
        /// snapshot (at most ~0.5s old) is returned without touching Unity APIs.
        /// </summary>
        public string GetStatusJson()
        {
            if (IsMainThread)
            {
                RebuildStatusJson();
            }
            return _cachedStatusJson;
        }

        private void RebuildStatusJson()
        {
            _dirty = false;
            _nextStatusRefresh = Time.unscaledTime + StatusRefreshInterval;

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
            int uptimeMinutes = Mathf.FloorToInt(Time.realtimeSinceStartup / 60f);

            string deviceId = _cachedDeviceId ?? string.Empty;
            string deviceName = _cachedDeviceName ?? string.Empty;
            string ip = _cachedIp ?? "0.0.0.0";

            var sb = new StringBuilder(640);
            sb.Append('{');
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"deviceId\":\"{0}\",", EscapeJson(deviceId));
            // Always present (possibly empty) so the server can tell "no name yet" from
            // "old player that does not report names".
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"deviceName\":\"{0}\",", EscapeJson(deviceName));
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"ip\":\"{0}\",", EscapeJson(ip));
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"androidId\":\"{0}\",", EscapeJson(deviceId));
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"deviceModel\":\"{0}\",", EscapeJson(_cachedDeviceModel));
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"macAddress\":\"{0}\",", EscapeJson(_cachedMacAddress));
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

            _cachedStatusJson = sb.ToString();
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
        /// Returns the cached android_id. Safe to call from any thread once the
        /// component has run Awake; before that (or in tests) it resolves on demand.
        /// </summary>
        public static string GetAndroidId()
        {
            string cached = _cachedDeviceId;
            if (!string.IsNullOrEmpty(cached)) return cached;
            if (!IsMainThread && _mainThreadId != -1) return string.Empty;
            _cachedDeviceId = ResolveAndroidId();
            return _cachedDeviceId;
        }

        /// <summary>
        /// Resolves android_id via Android Settings.Secure API (main thread only).
        /// This matches what the server reads via "adb shell settings get secure android_id".
        /// Falls back to a persisted SystemInfo identifier so the ID never changes between runs.
        /// </summary>
        private static string ResolveAndroidId()
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
            string saved = PlayerPrefs.GetString(DeviceIdPrefKey, string.Empty);
            if (!string.IsNullOrEmpty(saved)) return saved;

            string uid = SystemInfo.deviceUniqueIdentifier;
            if (!string.IsNullOrEmpty(uid) && uid != SystemInfo.unsupportedIdentifier)
            {
                PlayerPrefs.SetString(DeviceIdPrefKey, uid);
                PlayerPrefs.Save();
                return uid;
            }

            string fallback = $"{SystemInfo.deviceModel}_{SystemInfo.deviceName}";
            PlayerPrefs.SetString(DeviceIdPrefKey, fallback);
            PlayerPrefs.Save();
            return fallback;
        }

        /// <summary>Cached device name; safe from any thread.</summary>
        public static string GetDeviceName()
        {
            return _cachedDeviceName ?? string.Empty;
        }

        public static string GetDeviceModel()
        {
            return _cachedDeviceModel ?? string.Empty;
        }

        public static string GetMacAddress()
        {
            return _cachedMacAddress ?? string.Empty;
        }

        /// <summary>
        /// Persists the instructor-assigned name on the headset. Must be called on the
        /// main thread (PlayerPrefs). Raises OnDeviceNameChanged when the value changes.
        /// </summary>
        public static void SetDeviceName(string name)
        {
            string normalized = (name ?? string.Empty).Trim();
            string previous = _cachedDeviceName ?? string.Empty;

            PlayerPrefs.SetString(DeviceNamePrefKey, normalized);
            PlayerPrefs.Save();
            _cachedDeviceName = normalized;
            Debug.Log($"[StatusReporter] Device name saved: '{normalized}' (was '{previous}')");

            if (normalized != previous)
            {
                try
                {
                    OnDeviceNameChanged?.Invoke(normalized);
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[StatusReporter] OnDeviceNameChanged handler failed: {e.Message}");
                }
            }
        }

        private static string ReadMacAddress()
        {
            try
            {
                foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
                {
                    if (ni.OperationalStatus != OperationalStatus.Up) continue;
                    if (ni.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;
                    var address = ni.GetPhysicalAddress();
                    if (address == null) continue;
                    var bytes = address.GetAddressBytes();
                    if (bytes == null || bytes.Length == 0) continue;
                    return BitConverter.ToString(bytes).Replace("-", ":").ToLowerInvariant();
                }
            }
            catch
            {
                // ignore
            }

            return string.Empty;
        }

        /// <summary>Cached LAN IP; safe from any thread. Refreshed every few seconds.</summary>
        public static string GetLocalIPAddress()
        {
            string cached = _cachedIp;
            if (!string.IsNullOrEmpty(cached)) return cached;
            _cachedIp = ReadLocalIPAddress();
            return _cachedIp;
        }

        private static string ReadLocalIPAddress()
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
            if (string.IsNullOrEmpty(s)) return s ?? string.Empty;
            var sb = new StringBuilder(s.Length + 8);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '\\': sb.Append("\\\\"); break;
                    case '"': sb.Append("\\\""); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20)
                            sb.AppendFormat(CultureInfo.InvariantCulture, "\\u{0:x4}", (int)c);
                        else
                            sb.Append(c);
                        break;
                }
            }
            return sb.ToString();
        }
    }
}
