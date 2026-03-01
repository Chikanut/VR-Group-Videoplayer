using UnityEngine;
using UnityEngine.UI;

namespace VRClassroom
{
    public class PlayerHUD : MonoBehaviour
    {
        [SerializeField] private Transform vrCamera;

        private Canvas _canvas;
        private Text _stateText;
        private Text _fileText;
        private Text _modeText;
        private Text _ipText;

        private const float CanvasDistance = 3f;
        private const float CanvasScale = 0.005f;
        private const int MaxFilenameLength = 30;

        private void Awake()
        {
            if (vrCamera == null)
                vrCamera = Camera.main != null ? Camera.main.transform : transform;

            CreateCanvas();
            CreateUI();
        }

        private void Start()
        {
            var stateManager = PlayerStateManager.Instance;
            if (stateManager != null)
            {
                stateManager.OnPlayerStateUpdated += UpdateHUD;
            }

            // Initial update
            UpdateHUD();
        }

        private void OnDestroy()
        {
            var stateManager = PlayerStateManager.Instance;
            if (stateManager != null)
            {
                stateManager.OnPlayerStateUpdated -= UpdateHUD;
            }
        }

        private void UpdateHUD()
        {
            var stateManager = PlayerStateManager.Instance;
            PlayerState state = stateManager != null ? stateManager.State : PlayerState.Idle;

            // Hide during Playing and Paused
            bool visible = state != PlayerState.Playing && state != PlayerState.Paused;
            _canvas.gameObject.SetActive(visible);

            if (!visible) return;

            // State text
            string stateStr;
            Color stateColor = Color.white;

            switch (state)
            {
                case PlayerState.Idle:
                    stateStr = "Ready";
                    break;
                case PlayerState.Loading:
                    stateStr = "Loading...";
                    break;
                case PlayerState.Ready:
                    stateStr = "Ready";
                    break;
                case PlayerState.Completed:
                    stateStr = "Completed";
                    break;
                case PlayerState.Error:
                    stateStr = "Error";
                    stateColor = Color.red;
                    break;
                default:
                    stateStr = state.ToString();
                    break;
            }

            _stateText.text = stateStr;
            _stateText.color = stateColor;

            // File name
            string file = stateManager != null ? stateManager.CurrentFile : "";
            if (string.IsNullOrEmpty(file))
            {
                _fileText.text = "";
            }
            else if (file.Length > MaxFilenameLength)
            {
                _fileText.text = file.Substring(0, MaxFilenameLength) + "...";
            }
            else
            {
                _fileText.text = file;
            }

            // Mode
            ViewMode mode = stateManager != null ? stateManager.CurrentMode : PlayerConfig.DefaultViewMode;
            _modeText.text = mode == ViewMode.Sphere360 ? "360\u00b0" : "2D";

            // IP address
            string ip = StatusReporter.GetLocalIPAddress();
            _ipText.text = ip == "0.0.0.0" ? "No Network" : ip;
        }

        private void CreateCanvas()
        {
            var canvasGo = new GameObject("PlayerHUDCanvas");
            canvasGo.transform.SetParent(vrCamera);
            canvasGo.transform.localPosition = new Vector3(0f, 0f, CanvasDistance);
            canvasGo.transform.localRotation = Quaternion.identity;
            canvasGo.transform.localScale = Vector3.one * CanvasScale;

            _canvas = canvasGo.AddComponent<Canvas>();
            _canvas.renderMode = RenderMode.WorldSpace;

            var rectTransform = _canvas.GetComponent<RectTransform>();
            rectTransform.sizeDelta = new Vector2(800f, 400f);

            // Don't block raycasts
            var raycaster = canvasGo.GetComponent<GraphicRaycaster>();
            if (raycaster != null) Destroy(raycaster);

            // Add CanvasScaler for consistent text sizing
            canvasGo.AddComponent<CanvasScaler>();
        }

        private void CreateUI()
        {
            var canvasTransform = _canvas.transform;

            // Background panel
            var panelGo = new GameObject("Background");
            panelGo.transform.SetParent(canvasTransform, false);
            var panelImage = panelGo.AddComponent<Image>();
            panelImage.color = new Color(0f, 0f, 0f, 0.6f);
            panelImage.raycastTarget = false;
            var panelRect = panelGo.GetComponent<RectTransform>();
            panelRect.anchorMin = Vector2.zero;
            panelRect.anchorMax = Vector2.one;
            panelRect.offsetMin = Vector2.zero;
            panelRect.offsetMax = Vector2.zero;

            // State text (large, centered top)
            _stateText = CreateText(canvasTransform, "StateText",
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -20f),
                new Vector2(700f, 120f), 72, TextAnchor.MiddleCenter);

            // File text
            _fileText = CreateText(canvasTransform, "FileText",
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, 30f),
                new Vector2(700f, 60f), 36, TextAnchor.MiddleCenter);

            // Mode text
            _modeText = CreateText(canvasTransform, "ModeText",
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, -30f),
                new Vector2(700f, 60f), 36, TextAnchor.MiddleCenter);

            // IP text (bottom)
            _ipText = CreateText(canvasTransform, "IPText",
                new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 50f),
                new Vector2(700f, 50f), 28, TextAnchor.MiddleCenter);
            _ipText.color = new Color(0.7f, 0.7f, 0.7f, 1f);
        }

        private Text CreateText(Transform parent, string name,
            Vector2 anchorMin, Vector2 anchorMax, Vector2 anchoredPos,
            Vector2 sizeDelta, int fontSize, TextAnchor alignment)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);

            var text = go.AddComponent<Text>();
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            text.fontSize = fontSize;
            text.alignment = alignment;
            text.color = Color.white;
            text.raycastTarget = false;

            var rect = go.GetComponent<RectTransform>();
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.anchoredPosition = anchoredPos;
            rect.sizeDelta = sizeDelta;

            return text;
        }
    }
}
