using UnityEngine;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
#endif

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

        private Text _version;

        private const float CanvasDistance = 3f;
        private const float CanvasScale = 0.005f;
        private const int MaxFilenameLength = 30;

#if UNITY_EDITOR
        // Editor-only controls state
        private string _editorVideoPath = "";
        private int _editorModeIndex; // 0 = 360, 1 = 2D
        private bool _editorLoop;
        private readonly string[] _editorModeNames = { "360", "2D" };
        private VideoPlayerController _editorVideoPlayer;
        private ViewModeManager _editorViewModeManager;
        private OrientationManager _editorOrientationManager;
#endif

        private void Awake()
        {
            if (vrCamera == null)
                vrCamera = Camera.main != null ? Camera.main.transform : transform;

            CreateCanvas();
            CreateUI();

#if UNITY_EDITOR
            // Auto-find controllers for editor playback
            _editorVideoPlayer = FindFirstObjectByTypeCompat<VideoPlayerController>();
            _editorViewModeManager = FindFirstObjectByTypeCompat<ViewModeManager>();
            _editorOrientationManager = FindFirstObjectByTypeCompat<OrientationManager>();
#endif
        }

        private void Start()
        {
            var stateManager = PlayerStateManager.Instance;
            if (stateManager != null)
            {
                stateManager.OnPlayerStateUpdated += UpdateHUD;
                Debug.Log("[PlayerHUD] Subscribed to PlayerStateManager updates.");
            }
            else
            {
                Debug.LogError("[PlayerHUD] PlayerStateManager.Instance is null! HUD will not update.");
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

            Debug.Log($"[PlayerHUD] UpdateHUD: state={state}, visible={visible}");

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
            _version.text = UnityEngine.Application.version;
        }

#if UNITY_EDITOR
        private void OnGUI()
        {
            float panelWidth = 360f;
            float panelX = Screen.width - panelWidth - 10f;
            float y = 10f;
            float lineH = 24f;
            float spacing = 4f;

            // Background
            GUI.Box(new Rect(panelX - 5f, y - 5f, panelWidth + 10f, 230f), "");

            // Title
            GUI.Label(new Rect(panelX, y, panelWidth, lineH), "<b>Editor Playback Controls</b>",
                new GUIStyle(GUI.skin.label) { richText = true, fontSize = 14 });
            y += lineH + spacing;

            // State display
            var stateManager = PlayerStateManager.Instance;
            string currentState = stateManager != null ? stateManager.State.ToString() : "N/A";
            GUI.Label(new Rect(panelX, y, panelWidth, lineH), $"State: {currentState}");
            y += lineH + spacing;

            // File path + Browse
            GUI.Label(new Rect(panelX, y, 70f, lineH), "Video:");
            _editorVideoPath = GUI.TextField(new Rect(panelX + 70f, y, panelWidth - 145f, lineH), _editorVideoPath);
            if (GUI.Button(new Rect(panelX + panelWidth - 70f, y, 70f, lineH), "Browse"))
            {
                string path = EditorUtility.OpenFilePanel("Select Video", "", "mp4,webm,mkv,avi,mov");
                if (!string.IsNullOrEmpty(path))
                    _editorVideoPath = path;
            }
            y += lineH + spacing;

            // Video type + Loop
            GUI.Label(new Rect(panelX, y, 50f, lineH), "Type:");
            _editorModeIndex = GUI.SelectionGrid(
                new Rect(panelX + 50f, y, 120f, lineH),
                _editorModeIndex, _editorModeNames, 2);
            _editorLoop = GUI.Toggle(new Rect(panelX + 185f, y, 80f, lineH), _editorLoop, "Loop");
            y += lineH + spacing + 4f;

            // Open button
            bool canOpen = !string.IsNullOrEmpty(_editorVideoPath) && _editorVideoPlayer != null;
            GUI.enabled = canOpen;
            if (GUI.Button(new Rect(panelX, y, panelWidth, lineH + 4f), "Open Video"))
            {
                EditorOpenVideo();
            }
            GUI.enabled = true;
            y += lineH + spacing + 6f;

            // Playback buttons row
            float btnW = (panelWidth - spacing * 3f) / 4f;
            bool hasPlayer = _editorVideoPlayer != null;

            GUI.enabled = hasPlayer && stateManager != null &&
                          (stateManager.State == PlayerState.Ready ||
                           stateManager.State == PlayerState.Paused ||
                           stateManager.State == PlayerState.Completed);
            if (GUI.Button(new Rect(panelX, y, btnW, lineH + 4f), "Play"))
                _editorVideoPlayer.Play();

            GUI.enabled = hasPlayer && stateManager != null &&
                          stateManager.State == PlayerState.Playing;
            if (GUI.Button(new Rect(panelX + btnW + spacing, y, btnW, lineH + 4f), "Pause"))
                _editorVideoPlayer.Pause();

            GUI.enabled = hasPlayer && stateManager != null &&
                          stateManager.State != PlayerState.Idle;
            if (GUI.Button(new Rect(panelX + (btnW + spacing) * 2f, y, btnW, lineH + 4f), "Stop"))
                _editorVideoPlayer.Stop();

            GUI.enabled = _editorOrientationManager != null;
            if (GUI.Button(new Rect(panelX + (btnW + spacing) * 3f, y, btnW, lineH + 4f), "Recenter"))
                _editorOrientationManager.Recenter();

            GUI.enabled = true;
        }

        private void EditorOpenVideo()
        {
            if (_editorVideoPlayer == null || string.IsNullOrEmpty(_editorVideoPath))
                return;

            // Set mode
            if (_editorViewModeManager != null)
            {
                ViewMode mode = _editorModeIndex == 0 ? ViewMode.Sphere360 : ViewMode.Flat2D;
                _editorViewModeManager.SetMode(mode);
            }

            // Set loop
            _editorVideoPlayer.IsLooping = _editorLoop;

            // Open video — use full path directly since we're on PC
            Debug.Log($"[PlayerHUD] Editor: opening video path={_editorVideoPath}, mode={_editorModeNames[_editorModeIndex]}, loop={_editorLoop}");
            _editorVideoPlayer.Open(_editorVideoPath);
        }

        private static T FindFirstObjectByTypeCompat<T>() where T : UnityEngine.Object
        {
#if UNITY_6000_0_OR_NEWER
            return FindFirstObjectByType<T>();
#else
            return FindObjectOfType<T>();
#endif
        }
#endif

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

            _version = CreateText(canvasTransform, "VersionText",  new Vector2(1f, 0f), new Vector2(1f, 0f), new Vector2(-100f, 15f), new Vector2(700f, 50f), 28, TextAnchor.MiddleCenter);
            _version.color = new Color(0.7f, 0.7f, 0.7f, 1f);
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
