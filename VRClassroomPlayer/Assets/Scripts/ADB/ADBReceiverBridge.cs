using System;
using System.Collections.Generic;
using UnityEngine;

namespace VRClassroom
{
    public class ADBReceiverBridge : MonoBehaviour
    {
        public event Action<string, Dictionary<string, string>> OnCommandReceived;

        private void Start()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var bridge = new AndroidJavaClass("com.vrclass.player.ADBBridge"))
                {
                    bridge.CallStatic("initialize");
                }
                Debug.Log("[ADBReceiverBridge] ADB bridge initialized on Android.");
            }
            catch (Exception e)
            {
                Debug.LogError($"[ADBReceiverBridge] Failed to initialize ADB bridge: {e.Message}");
            }
#else
            Debug.Log("[ADBReceiverBridge] ADB receiver not available on this platform");
#endif
        }

        private void OnDestroy()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var bridge = new AndroidJavaClass("com.vrclass.player.ADBBridge"))
                {
                    bridge.CallStatic("shutdown");
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[ADBReceiverBridge] Error shutting down ADB bridge: {e.Message}");
            }
#endif
        }

        /// <summary>
        /// Called from Java via UnitySendMessage. JSON format:
        /// {"action":"PLAY","extras":{"file":"lesson01.mp4","mode":"360"}}
        /// </summary>
        public void OnBroadcastReceived(string json)
        {
            try
            {
                var data = JsonUtility.FromJson<BroadcastData>(json);
                if (data == null || string.IsNullOrEmpty(data.action))
                {
                    Debug.LogWarning("[ADBReceiverBridge] Received empty or invalid broadcast data.");
                    return;
                }

                // Parse extras from the raw JSON since JsonUtility doesn't handle Dictionary
                var extras = ParseExtras(json);

                Debug.Log($"[ADBReceiverBridge] Command: {data.action}, Extras: {json}");
                OnCommandReceived?.Invoke(data.action, extras);
            }
            catch (Exception e)
            {
                Debug.LogError($"[ADBReceiverBridge] Error parsing broadcast: {e.Message}");
            }
        }

        private Dictionary<string, string> ParseExtras(string json)
        {
            var extras = new Dictionary<string, string>();

            // Simple JSON parser for the extras object
            int extrasStart = json.IndexOf("\"extras\"", StringComparison.Ordinal);
            if (extrasStart < 0) return extras;

            int braceStart = json.IndexOf('{', extrasStart);
            if (braceStart < 0) return extras;

            int braceEnd = json.IndexOf('}', braceStart);
            if (braceEnd < 0) return extras;

            string extrasJson = json.Substring(braceStart + 1, braceEnd - braceStart - 1);
            if (string.IsNullOrWhiteSpace(extrasJson)) return extras;

            // Parse key-value pairs: "key":"value"
            string[] pairs = extrasJson.Split(',');
            foreach (string pair in pairs)
            {
                string[] kv = pair.Split(new[] { ':' }, 2);
                if (kv.Length != 2) continue;

                string key = kv[0].Trim().Trim('"');
                string value = kv[1].Trim().Trim('"');

                if (!string.IsNullOrEmpty(key))
                    extras[key] = value;
            }

            return extras;
        }

        [Serializable]
        private class BroadcastData
        {
            public string action;
        }
    }
}
