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
            if (videoPlayerController != null)
            {
                videoPlayerController.OnStateChanged += HandleStateChanged;
                videoPlayerController.OnVideoLoaded += HandleVideoLoaded;
                videoPlayerController.OnVideoCompleted += HandleVideoCompleted;
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
        }

        private void HandleVideoCompleted()
        {
            Debug.Log($"[PlayerStateManager] Video completed: {CurrentFile}");
            OnPlayerStateUpdated?.Invoke();
        }

        private void HandleModeChanged(ViewMode mode)
        {
            Debug.Log($"[PlayerStateManager] View mode changed: {CurrentMode} -> {mode}");
            CurrentMode = mode;
            OnPlayerStateUpdated?.Invoke();
        }
    }
}
