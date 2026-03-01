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
        }

        private void Start()
        {
            if (videoPlayerController != null)
            {
                videoPlayerController.OnStateChanged += HandleStateChanged;
                videoPlayerController.OnVideoLoaded += HandleVideoLoaded;
                videoPlayerController.OnVideoCompleted += HandleVideoCompleted;
            }

            if (viewModeManager != null)
            {
                viewModeManager.OnModeChanged += HandleModeChanged;
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
            if (newState == PlayerState.Error)
            {
                // Preserve previous state info for recovery
                _previousStateBeforeError = State;
                _previousFileBeforeError = CurrentFile;
                _previousModeBeforeError = CurrentMode;
            }

            State = newState;
            OnPlayerStateUpdated?.Invoke();
        }

        private void HandleVideoLoaded(string filename)
        {
            CurrentFile = filename;
            OnPlayerStateUpdated?.Invoke();
        }

        private void HandleVideoCompleted()
        {
            OnPlayerStateUpdated?.Invoke();
        }

        private void HandleModeChanged(ViewMode mode)
        {
            CurrentMode = mode;
            OnPlayerStateUpdated?.Invoke();
        }
    }
}
