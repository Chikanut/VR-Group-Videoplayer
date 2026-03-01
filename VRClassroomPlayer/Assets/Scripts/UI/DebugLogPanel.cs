using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace VRClassroom
{
    /// <summary>
    /// On-screen debug log panel for VR. Captures Unity debug logs and displays them
    /// on a world-space canvas anchored to the right side of the VR camera view.
    /// Toggle via: HTTP GET/POST /debug, ADB broadcast TOGGLE_DEBUG, or 3 quick
    /// taps on the right controller trigger.
    /// </summary>
    public class DebugLogPanel : MonoBehaviour
    {
        [SerializeField] private Transform vrCamera;

        private Canvas _canvas;
        private Text _logText;
        private Text _headerText;
        private Image _background;
        private GameObject _panelRoot;

        private readonly List<LogEntry> _logEntries = new List<LogEntry>();
        private bool _dirty;

        private const int MaxEntries = 80;
        private const bool CaptureAllLogs = true;
        private const float CanvasDistance = 2.5f;
        private const float CanvasScale = 0.003f;
        private const float PanelOffsetX = 0f; // Centered in view

        // Multi-tap toggle: 3 taps within 1.5 seconds
        private const int TapsRequired = 3;
        private const float TapWindow = 1.5f;
        private readonly List<float> _tapTimes = new List<float>();

        private void Awake()
        {
            if (vrCamera == null)
                vrCamera = Camera.main != null ? Camera.main.transform : transform;

            CreateCanvas();
            CreateUI();

            // Start visible so logs are immediately accessible for debugging
            _panelRoot.SetActive(true);

            AddPanelInfo("Panel initialized");
        }

        private void OnEnable()
        {
            // Keep callback on main thread so UI update signal is always observed.
            Application.logMessageReceived += OnLogMessageReceived;
        }

        private void OnDisable()
        {
            Application.logMessageReceived -= OnLogMessageReceived;
        }

        private void Update()
        {
            // Multi-tap detection via right controller primary button (A button on Quest)
            if (OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.RTouch) ||
                Input.GetKeyDown(KeyCode.BackQuote))
            {
                RegisterTap();
            }

            if (_dirty && _panelRoot.activeSelf)
            {
                RefreshText();
                _dirty = false;
            }
        }

        private void RegisterTap()
        {
            float now = Time.unscaledTime;
            _tapTimes.Add(now);

            // Remove taps outside window
            while (_tapTimes.Count > 0 && now - _tapTimes[0] > TapWindow)
                _tapTimes.RemoveAt(0);

            if (_tapTimes.Count >= TapsRequired)
            {
                _tapTimes.Clear();
                Toggle();
            }
        }

        public void Toggle()
        {
            SetVisible(!_panelRoot.activeSelf);
        }

        public void SetVisible(bool visible)
        {
            _panelRoot.SetActive(visible);
            if (visible)
            {
                _dirty = true;
                Debug.Log("[DebugLogPanel] Panel opened");
            }
            else
            {
                Debug.Log("[DebugLogPanel] Panel closed");
            }
        }

        public bool IsVisible => _panelRoot != null && _panelRoot.activeSelf;

        private void OnLogMessageReceived(string condition, string stackTrace, LogType type)
        {
            condition ??= "<null log message>";

            // Filter: only capture logs with relevant prefixes or errors/warnings
            bool relevant = IsRelevantLog(condition, type);
            if (!relevant) return;

            lock (_logEntries)
            {
                _logEntries.Add(new LogEntry
                {
                    Time = DateTime.Now,
                    Message = condition,
                    Type = type
                });

                while (_logEntries.Count > MaxEntries)
                    _logEntries.RemoveAt(0);
            }

            _dirty = true;
        }

        private void AddPanelInfo(string message)
        {
            lock (_logEntries)
            {
                _logEntries.Add(new LogEntry
                {
                    Time = DateTime.Now,
                    Message = $"[DebugLogPanel] {message}",
                    Type = LogType.Log
                });
            }

            _dirty = true;
        }

        private static bool IsRelevantLog(string message, LogType type)
        {
            if (CaptureAllLogs)
                return true;

            // Always capture errors and warnings
            if (type == LogType.Error || type == LogType.Exception)
                return true;

            if (type == LogType.Warning)
                return true;

            // Capture logs from our components
            if (message.StartsWith("[LanServer]", StringComparison.Ordinal)) return true;
            if (message.StartsWith("[ADBCommandRouter]", StringComparison.Ordinal)) return true;
            if (message.StartsWith("[ADBReceiverBridge]", StringComparison.Ordinal)) return true;
            if (message.StartsWith("[VideoPlayerController]", StringComparison.Ordinal)) return true;
            if (message.StartsWith("[ViewModeManager]", StringComparison.Ordinal)) return true;
            if (message.StartsWith("[OrientationManager]", StringComparison.Ordinal)) return true;
            if (message.StartsWith("[StatusReporter]", StringComparison.Ordinal)) return true;
            if (message.StartsWith("[PlayerStateManager]", StringComparison.Ordinal)) return true;
            if (message.StartsWith("[DebugLogPanel]", StringComparison.Ordinal)) return true;
            if (message.StartsWith("[PlayerHUD]", StringComparison.Ordinal)) return true;
            if (message.StartsWith("[VRPlayer]", StringComparison.Ordinal)) return true;

            return false;
        }

        private void RefreshText()
        {
            if (_logText == null) return;

            var sb = new System.Text.StringBuilder(4096);

            lock (_logEntries)
            {
                for (int i = 0; i < _logEntries.Count; i++)
                {
                    var entry = _logEntries[i];
                    string color = GetColorTag(entry.Type);
                    string timeStr = entry.Time.ToString("HH:mm:ss");
                    string msg = entry.Message;

                    // Truncate long messages
                    if (msg.Length > 120)
                        msg = msg.Substring(0, 117) + "...";

                    sb.Append($"<color={color}>{timeStr} {msg}</color>\n");
                }
            }

            _logText.text = sb.ToString();
        }

        private static string GetColorTag(LogType type)
        {
            switch (type)
            {
                case LogType.Error:
                case LogType.Exception:
                    return "#FF4444";
                case LogType.Warning:
                    return "#FFAA00";
                case LogType.Log:
                default:
                    return "#CCCCCC";
            }
        }

        private void CreateCanvas()
        {
            _panelRoot = new GameObject("DebugLogPanelCanvas");
            _panelRoot.transform.SetParent(vrCamera);
            _panelRoot.transform.localPosition = new Vector3(PanelOffsetX, 0f, CanvasDistance);
            _panelRoot.transform.localRotation = Quaternion.identity;
            _panelRoot.transform.localScale = Vector3.one * CanvasScale;

            _canvas = _panelRoot.AddComponent<Canvas>();
            _canvas.renderMode = RenderMode.WorldSpace;

            var rectTransform = _canvas.GetComponent<RectTransform>();
            rectTransform.sizeDelta = new Vector2(700f, 900f);

            // Don't block raycasts
            var raycaster = _panelRoot.GetComponent<GraphicRaycaster>();
            if (raycaster != null) Destroy(raycaster);

            _panelRoot.AddComponent<CanvasScaler>();
        }

        private void CreateUI()
        {
            var canvasTransform = _canvas.transform;

            // Background panel
            var bgGo = new GameObject("DebugBg");
            bgGo.transform.SetParent(canvasTransform, false);
            _background = bgGo.AddComponent<Image>();
            _background.color = new Color(0f, 0f, 0f, 0.75f);
            _background.raycastTarget = false;
            var bgRect = bgGo.GetComponent<RectTransform>();
            bgRect.anchorMin = Vector2.zero;
            bgRect.anchorMax = Vector2.one;
            bgRect.offsetMin = Vector2.zero;
            bgRect.offsetMax = Vector2.zero;

            // Header
            var headerGo = new GameObject("DebugHeader");
            headerGo.transform.SetParent(canvasTransform, false);
            _headerText = headerGo.AddComponent<Text>();
            _headerText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            _headerText.fontSize = 28;
            _headerText.alignment = TextAnchor.MiddleCenter;
            _headerText.color = new Color(0.3f, 1f, 0.3f, 1f);
            _headerText.raycastTarget = false;
            _headerText.text = "DEBUG LOG (B x3 to close)";
            var headerRect = headerGo.GetComponent<RectTransform>();
            headerRect.anchorMin = new Vector2(0f, 1f);
            headerRect.anchorMax = new Vector2(1f, 1f);
            headerRect.anchoredPosition = new Vector2(0f, -20f);
            headerRect.sizeDelta = new Vector2(0f, 40f);

            // Log text area
            var logGo = new GameObject("DebugLogText");
            logGo.transform.SetParent(canvasTransform, false);
            _logText = logGo.AddComponent<Text>();
            _logText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            _logText.fontSize = 18;
            _logText.alignment = TextAnchor.LowerLeft;
            _logText.color = Color.white;
            _logText.raycastTarget = false;
            _logText.supportRichText = true;
            _logText.verticalOverflow = VerticalWrapMode.Truncate;
            _logText.horizontalOverflow = HorizontalWrapMode.Wrap;
            var logRect = logGo.GetComponent<RectTransform>();
            logRect.anchorMin = new Vector2(0f, 0f);
            logRect.anchorMax = new Vector2(1f, 1f);
            logRect.offsetMin = new Vector2(10f, 10f);
            logRect.offsetMax = new Vector2(-10f, -45f);
        }

        private struct LogEntry
        {
            public DateTime Time;
            public string Message;
            public LogType Type;
        }
    }
}
