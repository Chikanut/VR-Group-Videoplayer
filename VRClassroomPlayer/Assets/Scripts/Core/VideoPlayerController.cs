using System;
using System.IO;
using UnityEngine;
using UnityEngine.Video;

namespace VRClassroom
{
    [RequireComponent(typeof(VideoPlayer))]
    public class VideoPlayerController : MonoBehaviour
    {
        public event Action<PlayerState> OnStateChanged;
        public event Action<string> OnVideoLoaded;
        public event Action OnVideoCompleted;

        public PlayerState CurrentState { get; private set; } = PlayerState.Idle;
        public string CurrentFile { get; private set; } = string.Empty;
        public RenderTexture TargetTexture { get; private set; }

        public float CurrentTime
        {
            get
            {
                if (_videoPlayer == null) return 0f;
                return (float)_videoPlayer.time;
            }
        }

        public float Duration
        {
            get
            {
                if (_videoPlayer == null || _videoPlayer.frameCount == 0) return 0f;
                return (float)(_videoPlayer.frameCount / _videoPlayer.frameRate);
            }
        }

        public bool IsLooping
        {
            get => _videoPlayer != null && _videoPlayer.isLooping;
            set
            {
                if (_videoPlayer != null)
                    _videoPlayer.isLooping = value;
            }
        }

        private VideoPlayer _videoPlayer;

        private void Awake()
        {
            Debug.Log("[VideoPlayerController] Awake: initializing...");

            _videoPlayer = GetComponent<VideoPlayer>();
            if (_videoPlayer == null)
            {
                _videoPlayer = gameObject.AddComponent<VideoPlayer>();
                Debug.Log("[VideoPlayerController] VideoPlayer component added dynamically.");
            }
            else
            {
                Debug.Log("[VideoPlayerController] VideoPlayer component found on GameObject.");
            }

            TargetTexture = new RenderTexture(
                PlayerConfig.RenderTextureSize,
                PlayerConfig.RenderTextureSize,
                0,
                RenderTextureFormat.ARGB32
            );
            TargetTexture.Create();
            Debug.Log($"[VideoPlayerController] RenderTexture created: {TargetTexture.width}x{TargetTexture.height}, isCreated={TargetTexture.IsCreated()}");

            _videoPlayer.source = VideoSource.Url;
            _videoPlayer.renderMode = VideoRenderMode.RenderTexture;
            _videoPlayer.targetTexture = TargetTexture;
            _videoPlayer.playOnAwake = false;
            _videoPlayer.skipOnDrop = true;

            _videoPlayer.prepareCompleted += OnPrepareCompleted;
            _videoPlayer.loopPointReached += OnLoopPointReached;
            _videoPlayer.errorReceived += OnErrorReceived;

            Debug.Log($"[VideoPlayerController] VideoPlayer configured: source=Url, renderMode=RenderTexture, videoPath={PlayerConfig.VideoPath}");
        }

        private void OnDestroy()
        {
            if (_videoPlayer != null)
            {
                _videoPlayer.prepareCompleted -= OnPrepareCompleted;
                _videoPlayer.loopPointReached -= OnLoopPointReached;
                _videoPlayer.errorReceived -= OnErrorReceived;
            }

            if (TargetTexture != null)
            {
                TargetTexture.Release();
                Destroy(TargetTexture);
            }
        }

        public void Open(string filename)
        {
            if (string.IsNullOrEmpty(filename))
            {
                Debug.LogWarning("[VideoPlayerController] Open called with empty filename, ignoring.");
                return;
            }

            Debug.Log($"[VideoPlayerController] Open requested: {filename}");

            // Stop current playback if any
            if (CurrentState == PlayerState.Playing || CurrentState == PlayerState.Paused || CurrentState == PlayerState.Loading)
            {
                Debug.Log($"[VideoPlayerController] Stopping current playback (state={CurrentState})");
                _videoPlayer.Stop();
            }

            string fullPath = PlayerConfig.VideoPath + filename;
            Debug.Log($"[VideoPlayerController] Full path: {fullPath}");

            if (!File.Exists(fullPath))
            {
                Debug.LogError($"[VideoPlayerController] File not found: {fullPath}");
                SetState(PlayerState.Error);
                return;
            }

            Debug.Log("[VideoPlayerController] File exists, preparing playback...");
            CurrentFile = filename;
            _videoPlayer.url = "file://" + fullPath;

            SetState(PlayerState.Loading);
            _videoPlayer.Prepare();
        }

        public void Play()
        {
            if (CurrentState == PlayerState.Ready || CurrentState == PlayerState.Paused || CurrentState == PlayerState.Completed)
            {
                _videoPlayer.Play();
                SetState(PlayerState.Playing);
            }
            else
            {
                Debug.LogWarning($"[VideoPlayerController] Play() ignored in state {CurrentState}");
            }
        }

        public void Pause()
        {
            if (CurrentState == PlayerState.Playing)
            {
                _videoPlayer.Pause();
                SetState(PlayerState.Paused);
            }
        }

        public void Restart()
        {
            if (_videoPlayer == null || string.IsNullOrEmpty(CurrentFile)) return;

            _videoPlayer.time = 0;
            _videoPlayer.Play();
            SetState(PlayerState.Playing);
        }

        public void Stop()
        {
            if (_videoPlayer != null)
            {
                _videoPlayer.Stop();
            }

            ClearRenderTexture();
            CurrentFile = string.Empty;
            SetState(PlayerState.Idle);
        }

        private void OnPrepareCompleted(VideoPlayer source)
        {
            Debug.Log($"[VideoPlayerController] Prepare completed for: {CurrentFile}, " +
                      $"width={source.width}, height={source.height}, " +
                      $"frameCount={source.frameCount}, frameRate={source.frameRate:F1}, " +
                      $"canSetTime={source.canSetTime}, audioTrackCount={source.audioTrackCount}");
            SetState(PlayerState.Ready);
            OnVideoLoaded?.Invoke(CurrentFile);

            // Auto-play after preparation
            Debug.Log("[VideoPlayerController] Auto-playing video...");
            source.Play();
            SetState(PlayerState.Playing);
        }

        private void OnLoopPointReached(VideoPlayer source)
        {
            if (!source.isLooping)
            {
                SetState(PlayerState.Completed);
                OnVideoCompleted?.Invoke();
            }
        }

        private void OnErrorReceived(VideoPlayer source, string message)
        {
            Debug.LogError($"[VideoPlayerController] VideoPlayer error: {message}");
            SetState(PlayerState.Error);
        }

        private void SetState(PlayerState newState)
        {
            if (CurrentState == newState) return;
            Debug.Log($"[VideoPlayerController] State: {CurrentState} -> {newState}");
            CurrentState = newState;
            OnStateChanged?.Invoke(newState);
        }

        private void ClearRenderTexture()
        {
            if (TargetTexture == null) return;
            RenderTexture prev = RenderTexture.active;
            RenderTexture.active = TargetTexture;
            GL.Clear(true, true, Color.black);
            RenderTexture.active = prev;
        }
    }
}
