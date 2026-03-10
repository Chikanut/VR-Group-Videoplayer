using System;
using UnityEngine;

namespace VRClassroom
{
    public class PlayerStateManager : MonoBehaviour
    {
        public event Action OnPlayerStateUpdated;

        public PlayerState State { get; private set; } = PlayerState.Idle;
        public string CurrentFile { get; private set; } = string.Empty;
        public ViewMode CurrentMode { get; private set; } = PlayerConfig.DefaultViewMode;
        public bool IsLocked { get; set; }

        private PlayerState _previousStateBeforeError;
        private string _previousFileBeforeError;
        private ViewMode _previousModeBeforeError;

        private static PlayerStateManager _instance;
        public static PlayerStateManager Instance
        {
            get
            {
                if (_instance == null)
                {
#if UNITY_6000_0_OR_NEWER
                    _instance = FindFirstObjectByType<PlayerStateManager>();
#else
                    _instance = FindObjectOfType<PlayerStateManager>();
#endif
                }
                return _instance;
            }
        }

        [SerializeField] private VideoPlayerController videoPlayerController;
        [SerializeField] private ViewModeManager viewModeManager;
        [SerializeField] private OrientationManager orientationManager;

        private void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Debug.LogError("[PlayerStateManager] Duplicate instance detected, destroying this one.");
                Destroy(gameObject);
                return;
            }

            _instance = this;
            Debug.Log("[PlayerStateManager] Instance initialized.");
        }

        private void Start()
        {
            TryDisableGuardian();

            if (videoPlayerController != null)
            {
                videoPlayerController.OnStateChanged += HandleStateChanged;
                videoPlayerController.OnVideoLoaded += HandleVideoLoaded;
                videoPlayerController.OnVideoCompleted += HandleVideoCompleted;
                videoPlayerController.OnRenderTextureResized += HandleRenderTextureResized;
                Debug.Log("[PlayerStateManager] Subscribed to VideoPlayerController events.");
            }
            else
            {
                Debug.LogError("[PlayerStateManager] VideoPlayerController reference is NOT assigned!");
            }

            if (viewModeManager != null)
            {
                viewModeManager.OnModeChanged += HandleModeChanged;
                Debug.Log("[PlayerStateManager] Subscribed to ViewModeManager events.");
            }
            else
            {
                Debug.LogError("[PlayerStateManager] ViewModeManager reference is NOT assigned!");
            }

            // Connect the RenderTexture from VideoPlayerController to ViewModeManager
            if (videoPlayerController != null && viewModeManager != null)
            {
                var rt = videoPlayerController.TargetTexture;
                if (rt != null)
                {
                    viewModeManager.SetRenderTexture(rt);
                    Debug.Log($"[PlayerStateManager] Connected RenderTexture ({rt.width}x{rt.height}) to ViewModeManager.");
                }
                else
                {
                    Debug.LogError("[PlayerStateManager] VideoPlayerController.TargetTexture is null!");
                }
            }
        }

        private void OnDestroy()
        {
            if (videoPlayerController != null)
            {
                videoPlayerController.OnStateChanged -= HandleStateChanged;
                videoPlayerController.OnVideoLoaded -= HandleVideoLoaded;
                videoPlayerController.OnVideoCompleted -= HandleVideoCompleted;
                videoPlayerController.OnRenderTextureResized -= HandleRenderTextureResized;
            }

            if (viewModeManager != null)
            {
                viewModeManager.OnModeChanged -= HandleModeChanged;
            }

            if (_instance == this)
                _instance = null;
        }

        private void HandleStateChanged(PlayerState newState)
        {
            Debug.Log($"[PlayerStateManager] State changed: {State} -> {newState}");

            if (newState == PlayerState.Error)
            {
                // Preserve previous state info for recovery
                _previousStateBeforeError = State;
                _previousFileBeforeError = CurrentFile;
                _previousModeBeforeError = CurrentMode;
                Debug.LogError($"[PlayerStateManager] Error state entered. Previous: state={_previousStateBeforeError}, file={_previousFileBeforeError}, mode={_previousModeBeforeError}");
            }

            State = newState;
            OnPlayerStateUpdated?.Invoke();
        }

        private void HandleVideoLoaded(string filename)
        {
            Debug.Log($"[PlayerStateManager] Video loaded: {filename}");
            CurrentFile = filename;
            OnPlayerStateUpdated?.Invoke();

            // Auto-recenter when a new video is opened (after prepare completes)
            if (orientationManager != null)
            {
                Debug.Log("[PlayerStateManager] Auto-recentering on new video open.");
                orientationManager.Recenter();
            }
        }

        private void HandleVideoCompleted()
        {
            Debug.Log($"[PlayerStateManager] Video completed: {CurrentFile}");

            bool isLooping = videoPlayerController != null && videoPlayerController.IsLooping;
            if (!isLooping)
            {
                CurrentFile = string.Empty;
                viewModeManager?.SetMode(ViewMode.None);
                Debug.Log("[PlayerStateManager] Non-looping playback completed, cleared current file and switched to ViewMode.None.");
            }
            else
            {
                Debug.Log("[PlayerStateManager] Looping playback reached loop point, keeping current file and view mode.");
            }

            OnPlayerStateUpdated?.Invoke();
        }

        private void HandleModeChanged(ViewMode mode)
        {
            Debug.Log($"[PlayerStateManager] View mode changed: {CurrentMode} -> {mode}");
            CurrentMode = mode;
            OnPlayerStateUpdated?.Invoke();
        }

        /// <summary>
        /// Attempt to disable Guardian boundary to prevent passthrough camera
        /// from interrupting video playback. Uses OVRBoundary if available,
        /// otherwise tries Android system properties.
        /// </summary>
        private void TryDisableGuardian()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                // Try OVRManager.boundary if Meta XR SDK is present at runtime
                var ovrManagerType = System.Type.GetType("OVRManager, Assembly-CSharp");
                if (ovrManagerType != null)
                {
                    var instanceProp = ovrManagerType.GetProperty("instance",
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
                    if (instanceProp != null)
                    {
                        var instance = instanceProp.GetValue(null);
                        if (instance != null)
                        {
                            var boundaryProp = ovrManagerType.GetProperty("boundary");
                            if (boundaryProp != null)
                            {
                                var boundary = boundaryProp.GetValue(instance);
                                if (boundary != null)
                                {
                                    var setVisibleMethod = boundary.GetType().GetMethod("SetVisible");
                                    if (setVisibleMethod != null)
                                    {
                                        setVisibleMethod.Invoke(boundary, new object[] { false });
                                        Debug.Log("[PlayerStateManager] Guardian boundary hidden via OVRManager.");
                                        return;
                                    }
                                }
                            }
                        }
                    }
                }

                // Fallback: try Android system property
                using (var runtime = new AndroidJavaClass("java.lang.Runtime"))
                using (var instance = runtime.CallStatic<AndroidJavaObject>("getRuntime"))
                {
                    var process = instance.Call<AndroidJavaObject>("exec",
                        new string[] { "setprop", "debug.oculus.guardian_pause", "1" });
                    process.Call<int>("waitFor");
                    Debug.Log("[PlayerStateManager] Attempted Guardian disable via setprop (may require root).");
                }
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"[PlayerStateManager] Guardian disable not available: {e.Message}");
            }
#endif
        }

        private void HandleRenderTextureResized(RenderTexture newTexture)
        {
            if (viewModeManager != null && newTexture != null)
            {
                viewModeManager.SetRenderTexture(newTexture);
                Debug.Log($"[PlayerStateManager] Forwarded resized RenderTexture ({newTexture.width}x{newTexture.height}) to ViewModeManager.");
            }
        }
    }
}
