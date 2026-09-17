using System;
using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.Video;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine.Android;
#endif

namespace VRClassroom
{
    public class VideoPlayerController : MonoBehaviour
    {
        public event Action<PlayerState> OnStateChanged;
        public event Action<string> OnVideoLoaded;
        public event Action OnVideoCompleted;
        public event Action<RenderTexture> OnRenderTextureResized;

        public PlayerState CurrentState { get; private set; } = PlayerState.Idle;
        public string CurrentFile { get; private set; } = string.Empty;
        public RenderTexture TargetTexture { get; private set; }
        public float GlobalVolume { get; private set; } = 1f;
        public float PersonalVolume { get; private set; } = 1f;
        public float EffectiveVolume => Mathf.Clamp01(GlobalVolume * PersonalVolume);

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
            get => _isLooping;
            set
            {
                _isLooping = value;
                if (_videoPlayer != null)
                    _videoPlayer.isLooping = value;
            }
        }

        // Decoder lifecycle. Every Prepare() on Android grabs a hardware MediaCodec
        // instance plus a SurfaceTexture/GL output; those are scarce on Quest. Reusing
        // one VideoPlayer and only swapping its url, or calling Stop() and Prepare() in
        // the same frame, left native decoder resources behind: after 5-7 long videos
        // the next open hung in Loading or the app was killed. So every opened video
        // gets its own VideoPlayer on a child GameObject; the previous one is stopped
        // and destroyed, and the new one is prepared only after a short pause so the
        // media server has actually released the old decoder.
        private VideoPlayer _videoPlayer;
        private GameObject _videoPlayerHost;
        private bool _isLooping;
        private Coroutine _openRoutine;
        private int _openGeneration;

        private bool _releaseDecoderNextFrame;
        private float _loadingStartedAt = -1f;
        private float _nextDiagnosticsLogAt;
        private const float PrepareTimeoutSeconds = 40f;
        private const float DecoderReleaseDelaySeconds = 0.5f;
        private const float DiagnosticsLogIntervalSeconds = 60f;

        // Sleep. Quest logcats showed Unity's video pipeline leaking GPU memory across a
        // sleep/wake (an 8K player grew from 1.8 GB to 3.1-4.6 GB and was never freed),
        // after which videos froze the headset or would not start at all. Only a process
        // restart gives that memory back, so after every sleep the app restarts itself
        // (RestartActivity.java) and comes back as if freshly launched. Nothing touches
        // the VideoPlayer while the app is paused: the process is killed anyway.
        private bool _appPaused;
        private bool _restartOnWake;
        private float _resumedAt = -1f;
        private const float RestartDelayAfterWakeSeconds = 0.5f;

        private void Awake()
        {
            Debug.Log("[VideoPlayerController] Awake: initializing...");
            EnsureExternalVideoAccess();
            LogVideoDirectoryState();

            // Older scenes carry a VideoPlayer on this GameObject. It is never used now
            // (players are created per video), so make sure it cannot hold a decoder.
            var scenePlayer = GetComponent<VideoPlayer>();
            if (scenePlayer != null)
            {
                scenePlayer.playOnAwake = false;
                try { scenePlayer.Stop(); } catch { }
                Destroy(scenePlayer);
                Debug.Log("[VideoPlayerController] Removed scene VideoPlayer component (players are created per video).");
            }

            TargetTexture = new RenderTexture(
                PlayerConfig.RenderTextureSize,
                PlayerConfig.RenderTextureSize,
                0,
                RenderTextureFormat.ARGB32
            );
            TargetTexture.Create();
            Debug.Log($"[VideoPlayerController] RenderTexture created: {TargetTexture.width}x{TargetTexture.height}, isCreated={TargetTexture.IsCreated()}");

            ApplyEffectiveVolume();

            Debug.Log($"[VideoPlayerController] Initialized: videoPath={PlayerConfig.VideoPath}, {ProcessDiagnostics.Snapshot()}");
        }

        private VideoPlayer CreateVideoPlayer()
        {
            _videoPlayerHost = new GameObject("VideoPlayerInstance");
            _videoPlayerHost.transform.SetParent(transform, false);

            var player = _videoPlayerHost.AddComponent<VideoPlayer>();
            player.playOnAwake = false;
            player.source = VideoSource.Url;
            player.renderMode = VideoRenderMode.RenderTexture;
            player.targetTexture = TargetTexture;
            player.timeUpdateMode = VideoTimeUpdateMode.UnscaledGameTime;
            player.waitForFirstFrame = true;
            player.skipOnDrop = true;
            player.isLooping = _isLooping;
            player.audioOutputMode = VideoAudioOutputMode.Direct;
            player.controlledAudioTrackCount = 1;
            player.EnableAudioTrack(0, true);

            player.prepareCompleted += OnPrepareCompleted;
            player.loopPointReached += OnLoopPointReached;
            player.errorReceived += OnErrorReceived;

            _videoPlayer = player;
            ApplyEffectiveVolume();
            return player;
        }

        /// <summary>
        /// Stops and destroys the current VideoPlayer (and with it the hardware decoder).
        /// Safe to call in any state; returns true if there was a player to release.
        /// </summary>
        private bool DestroyVideoPlayer(string reason)
        {
            var player = _videoPlayer;
            var host = _videoPlayerHost;
            _videoPlayer = null;
            _videoPlayerHost = null;

            if (player == null && host == null) return false;

            Debug.Log($"[VideoPlayerController] Releasing video player ({reason}, state={CurrentState}, file={CurrentFile})");

            if (player != null)
            {
                player.prepareCompleted -= OnPrepareCompleted;
                player.loopPointReached -= OnLoopPointReached;
                player.errorReceived -= OnErrorReceived;
                try
                {
                    player.Stop();
                    player.targetTexture = null;
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[VideoPlayerController] VideoPlayer.Stop() failed ({reason}): {e.Message}");
                }
            }

            if (host != null)
                Destroy(host);

            return true;
        }


        private bool IsPermissionDeclaredInManifest(string permission)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using (var activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
                using (var packageManager = activity.Call<AndroidJavaObject>("getPackageManager"))
                {
                    string packageName = activity.Call<string>("getPackageName");
                    using (var packageInfo = packageManager.Call<AndroidJavaObject>(
                               "getPackageInfo",
                               packageName,
                               4096)) // PackageManager.GET_PERMISSIONS
                    {
                        string[] requestedPermissions = packageInfo.Get<string[]>("requestedPermissions");
                        if (requestedPermissions == null || requestedPermissions.Length == 0)
                            return false;

                        foreach (string declaredPermission in requestedPermissions)
                        {
                            if (declaredPermission == permission)
                                return true;
                        }

                        return false;
                    }
                }
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"[VideoPlayerController] Unable to inspect manifest permissions. Exception={exception.GetType().Name}, message={exception.Message}");
                return false;
            }
#else
            return true;
#endif
        }

        private void EnsureExternalVideoAccess()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            bool hasReadExternalStorage = Permission.HasUserAuthorizedPermission(Permission.ExternalStorageRead);
            bool hasReadMediaVideo = Permission.HasUserAuthorizedPermission("android.permission.READ_MEDIA_VIDEO");

            Debug.Log($"[VideoPlayerController] Android storage permission state. READ_EXTERNAL_STORAGE={hasReadExternalStorage}, READ_MEDIA_VIDEO={hasReadMediaVideo}");

            if (hasReadExternalStorage || hasReadMediaVideo)
            {
                Debug.Log("[VideoPlayerController] Storage read permission already granted.");
                return;
            }

            var callbacks = new PermissionCallbacks();
            callbacks.PermissionGranted += permission =>
            {
                Debug.Log($"[VideoPlayerController] Permission granted: {permission}");
                LogVideoDirectoryState();
            };
            callbacks.PermissionDenied += permission =>
            {
                Debug.LogWarning($"[VideoPlayerController] Permission denied: {permission}. External videos may be inaccessible.");
            };
            callbacks.PermissionDeniedAndDontAskAgain += permission =>
            {
                Debug.LogError($"[VideoPlayerController] Permission denied with 'Don't ask again': {permission}. External videos will remain inaccessible until enabled in system settings.");
            };

            int sdkInt = 0;
            using (var version = new AndroidJavaClass("android.os.Build$VERSION"))
            {
                sdkInt = version.GetStatic<int>("SDK_INT");
            }

            string permissionToRequest = sdkInt >= 33
                ? "android.permission.READ_MEDIA_VIDEO"
                : Permission.ExternalStorageRead;

            bool isDeclaredInManifest = IsPermissionDeclaredInManifest(permissionToRequest);
            Debug.Log($"[VideoPlayerController] Storage permission manifest check. permission={permissionToRequest}, declared={isDeclaredInManifest}, sdkInt={sdkInt}");

            if (!isDeclaredInManifest)
            {
                Debug.LogError($"[VideoPlayerController] Permission '{permissionToRequest}' is not declared in AndroidManifest. Runtime request will not work correctly until it is declared.");
                return;
            }

            Debug.Log($"[VideoPlayerController] Requesting storage permission: {permissionToRequest}, sdkInt={sdkInt}");
            Permission.RequestUserPermission(permissionToRequest, callbacks);
#else
            Debug.Log("[VideoPlayerController] External storage permission request is Android-only; skipping on this platform.");
#endif
        }

        private void LogVideoDirectoryState()
        {
            string videoDirectory = PlayerConfig.VideoPath;
            Debug.Log($"[VideoPlayerController] Video directory diagnostics start. path={videoDirectory}, platform={Application.platform}, persistentDataPath={Application.persistentDataPath}");

            try
            {
                if (!Directory.Exists(videoDirectory))
                {
                    Debug.LogError($"[VideoPlayerController] Video directory does not exist or is inaccessible: {videoDirectory}");
                    return;
                }

                string[] files = Directory.GetFiles(videoDirectory);
                Debug.Log($"[VideoPlayerController] Video directory is accessible. File count={files.Length}");

                if (files.Length == 0)
                {
                    Debug.LogWarning($"[VideoPlayerController] Video directory is empty: {videoDirectory}");
                    return;
                }

                foreach (string file in files)
                {
                    FileInfo fileInfo = new FileInfo(file);
                    Debug.Log($"[VideoPlayerController] Found file: name={fileInfo.Name}, sizeBytes={fileInfo.Length}, modifiedUtc={fileInfo.LastWriteTimeUtc:O}");
                }
            }
            catch (Exception exception)
            {
                Debug.LogError($"[VideoPlayerController] Failed to inspect video directory '{videoDirectory}'. Exception={exception.GetType().Name}, message={exception.Message}");
            }
        }


        private bool HasExternalVideoReadPermission()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            bool hasReadExternalStorage = Permission.HasUserAuthorizedPermission(Permission.ExternalStorageRead);
            bool hasReadMediaVideo = Permission.HasUserAuthorizedPermission("android.permission.READ_MEDIA_VIDEO");
            return hasReadExternalStorage || hasReadMediaVideo;
#else
            return true;
#endif
        }

        private void Update()
        {
            if (_restartOnWake && !_appPaused && Time.unscaledTime - _resumedAt >= RestartDelayAfterWakeSeconds)
            {
                _restartOnWake = false;
                Debug.Log($"[VideoPlayerController] Woke up from sleep: restarting the app. {ProcessDiagnostics.Snapshot()}");
                if (!RestartApplication())
                {
                    // Could not restart: at least do not keep the video from before sleep.
                    Stop();
                }
                return;
            }

            if (_releaseDecoderNextFrame)
            {
                _releaseDecoderNextFrame = false;
                DestroyVideoPlayer("deferred");
            }

            if (CurrentState == PlayerState.Loading && _loadingStartedAt >= 0f &&
                Time.unscaledTime - _loadingStartedAt > PrepareTimeoutSeconds)
            {
                Debug.LogError($"[VideoPlayerController] Prepare timed out after {PrepareTimeoutSeconds:F0}s for '{CurrentFile}'. Releasing decoder. {ProcessDiagnostics.Snapshot()}");
                _loadingStartedAt = -1f;
                CancelPendingOpen();
                DestroyVideoPlayer("prepare timeout");
                SetState(PlayerState.Error);
            }

            if (Time.unscaledTime >= _nextDiagnosticsLogAt)
            {
                _nextDiagnosticsLogAt = Time.unscaledTime + DiagnosticsLogIntervalSeconds;
                Debug.Log($"[VideoPlayerController] Diagnostics: state={CurrentState}, {ProcessDiagnostics.Snapshot()}");
            }
        }

        private void OnApplicationPause(bool paused)
        {
            if (Application.isEditor) return;

            _appPaused = paused;
            if (paused)
            {
                Debug.Log($"[VideoPlayerController] Application paused (sleep). state={CurrentState}, file={CurrentFile}. Will restart on wake.");
                _restartOnWake = true;
                return;
            }

            _resumedAt = Time.unscaledTime;
            Debug.Log($"[VideoPlayerController] Application resumed. restartPending={_restartOnWake}");
        }

        private static bool RestartApplication()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using (var activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
                using (var process = new AndroidJavaClass("android.os.Process"))
                using (var intent = new AndroidJavaObject("android.content.Intent"))
                {
                    int pid = process.CallStatic<int>("myPid");
                    intent.Call<AndroidJavaObject>("setClassName", activity, "com.vrclass.player.RestartActivity").Dispose();
                    intent.Call<AndroidJavaObject>("putExtra", "pid", pid).Dispose();
                    intent.Call<AndroidJavaObject>("addFlags", 0x10000000).Dispose(); // FLAG_ACTIVITY_NEW_TASK
                    activity.Call("startActivity", intent);
                    Debug.Log($"[VideoPlayerController] RestartActivity started for pid {pid}.");
                    return true;
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[VideoPlayerController] Restart failed: {e.Message}");
            }
#endif
            return false;
        }

        private void OnDestroy()
        {
            CancelPendingOpen();
            DestroyVideoPlayer("destroy");

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

            Debug.Log($"[VideoPlayerController] Open requested: {filename} (state={CurrentState}, {ProcessDiagnostics.Snapshot()})");

            // Always release the previous player before preparing a new one, whatever the
            // current state is (Completed/Error/Ready still hold a MediaCodec instance).
            _releaseDecoderNextFrame = false;
            CancelPendingOpen();
            bool releasedPrevious = DestroyVideoPlayer("open");

            // Support both full paths and filenames relative to VideoPath
            bool isAbsolute = filename.StartsWith("/") ||
                              (filename.Length >= 2 && filename[1] == ':'); // Windows drive letter
            string fullPath = isAbsolute ? filename : PlayerConfig.VideoPath + filename;
            Debug.Log($"[VideoPlayerController] Full path: {fullPath}");

            if (!HasExternalVideoReadPermission())
            {
                Debug.LogWarning("[VideoPlayerController] Read permission for external video storage is not granted. File access may fail.");
            }

            if (!File.Exists(fullPath))
            {
                Debug.LogError($"[VideoPlayerController] File not found: {fullPath}");
                SetState(PlayerState.Error);
                return;
            }

            Debug.Log("[VideoPlayerController] File exists, preparing playback...");
            CurrentFile = filename;
            _loadingStartedAt = Time.unscaledTime;
            SetState(PlayerState.Loading);

            _openRoutine = StartCoroutine(PrepareAfterRelease("file://" + fullPath, releasedPrevious, ++_openGeneration));
        }

        private IEnumerator PrepareAfterRelease(string url, bool releasedPrevious, int generation)
        {
            // Destroy() takes effect at the end of the frame, and the media server frees
            // the old MediaCodec asynchronously after that. Preparing a new decoder in the
            // same frame used to stack decoders until the headset ran out of them.
            yield return null;
            if (releasedPrevious)
                yield return new WaitForSecondsRealtime(DecoderReleaseDelaySeconds);

            if (generation != _openGeneration || CurrentState != PlayerState.Loading)
                yield break;

            _openRoutine = null;
            var player = CreateVideoPlayer();
            player.url = url;
            Debug.Log($"[VideoPlayerController] Preparing {url}");
            player.Prepare();
        }

        private void CancelPendingOpen()
        {
            _openGeneration++;
            if (_openRoutine != null)
            {
                StopCoroutine(_openRoutine);
                _openRoutine = null;
            }
        }

        public void Play()
        {
            if (CurrentState == PlayerState.Ready || CurrentState == PlayerState.Paused || CurrentState == PlayerState.Completed)
            {
                if (_videoPlayer == null || !_videoPlayer.isPrepared)
                {
                    // Decoder was released after completion; go through Prepare again so
                    // the state machine (Loading -> Ready -> Playing) stays consistent.
                    if (!string.IsNullOrEmpty(CurrentFile))
                    {
                        Debug.Log("[VideoPlayerController] Play() on a released player, re-opening current file.");
                        Open(CurrentFile);
                    }
                    else
                    {
                        Debug.LogWarning("[VideoPlayerController] Play() ignored: nothing to play.");
                    }
                    return;
                }

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
            if (CurrentState == PlayerState.Playing && _videoPlayer != null)
            {
                _videoPlayer.Pause();
                SetState(PlayerState.Paused);
            }
        }

        public void Restart()
        {
            if (string.IsNullOrEmpty(CurrentFile) || CurrentState == PlayerState.Loading) return;

            if (_videoPlayer == null || !_videoPlayer.isPrepared)
            {
                Open(CurrentFile);
                return;
            }

            _videoPlayer.time = 0;
            _videoPlayer.Play();
            SetState(PlayerState.Playing);
        }

        public void Stop()
        {
            _releaseDecoderNextFrame = false;
            _loadingStartedAt = -1f;
            CancelPendingOpen();
            DestroyVideoPlayer("stop");

            ClearRenderTexture();
            CurrentFile = string.Empty;
            SetState(PlayerState.Idle);
        }

        public void Seek(float seconds)
        {
            if (_videoPlayer == null)
            {
                Debug.LogWarning($"[VideoPlayerController] Seek ignored: no video player (state={CurrentState})");
                return;
            }

            if (!_videoPlayer.canSetTime)
            {
                Debug.LogWarning($"[VideoPlayerController] Seek ignored: canSetTime=false (state={CurrentState}, file={CurrentFile})");
                return;
            }

            float duration = Duration;
            float target = duration > 0f ? Mathf.Clamp(seconds, 0f, duration) : Mathf.Max(0f, seconds);
            _videoPlayer.time = target;
            Debug.Log($"[VideoPlayerController] Seek to {target:F2}s (requested={seconds:F2}, duration={duration:F2}, state={CurrentState})");
        }

        public void SetVolume(float globalVolume, float personalVolume)
        {
            GlobalVolume = Mathf.Clamp01(globalVolume);
            PersonalVolume = Mathf.Clamp01(personalVolume);
            ApplyEffectiveVolume();
            Debug.Log($"[VideoPlayerController] Volume updated: global={GlobalVolume:F2}, personal={PersonalVolume:F2}, effective={EffectiveVolume:F2}");
        }

        private void ApplyEffectiveVolume()
        {
            float volume = EffectiveVolume;
            if (_videoPlayer != null && _videoPlayer.audioTrackCount > 0)
            {
                _videoPlayer.SetDirectAudioVolume(0, volume);
            }
            AudioListener.volume = volume;
        }

        private void OnPrepareCompleted(VideoPlayer source)
        {
            if (source != _videoPlayer)
            {
                Debug.LogWarning("[VideoPlayerController] Ignoring prepareCompleted from a released player.");
                return;
            }

            Debug.Log($"[VideoPlayerController] Prepare completed for: {CurrentFile}, " +
                      $"width={source.width}, height={source.height}, " +
                      $"frameCount={source.frameCount}, frameRate={source.frameRate:F1}, " +
                      $"canSetTime={source.canSetTime}, audioTrackCount={source.audioTrackCount}");

            ApplyEffectiveVolume();
            _loadingStartedAt = -1f;

            // Resize RenderTexture to match video resolution
            ResizeRenderTexture((int)source.width, (int)source.height);

            SetState(PlayerState.Ready);
            OnVideoLoaded?.Invoke(CurrentFile);

            // Auto-play after preparation
            Debug.Log("[VideoPlayerController] Auto-playing video...");
            source.Play();
            SetState(PlayerState.Playing);
        }

        private void ResizeRenderTexture(int videoWidth, int videoHeight)
        {
            if (videoWidth <= 0 || videoHeight <= 0)
            {
                Debug.LogWarning($"[VideoPlayerController] Invalid video dimensions: {videoWidth}x{videoHeight}, keeping current RenderTexture.");
                return;
            }

            // Clamp to reasonable limits for Quest hardware
            const int maxDimension = 4096;
            int targetWidth = Math.Min(videoWidth, maxDimension);
            int targetHeight = Math.Min(videoHeight, maxDimension);

            if (TargetTexture != null && TargetTexture.width == targetWidth && TargetTexture.height == targetHeight)
            {
                Debug.Log($"[VideoPlayerController] RenderTexture already matches video: {targetWidth}x{targetHeight}");
                return;
            }

            Debug.Log($"[VideoPlayerController] Resizing RenderTexture: {TargetTexture?.width}x{TargetTexture?.height} -> {targetWidth}x{targetHeight}");

            // Release old texture
            if (TargetTexture != null)
            {
                _videoPlayer.targetTexture = null;
                TargetTexture.Release();
                Destroy(TargetTexture);
            }

            // Create new texture matching video resolution
            TargetTexture = new RenderTexture(targetWidth, targetHeight, 0, RenderTextureFormat.ARGB32);
            TargetTexture.Create();

            // Reassign to video player
            _videoPlayer.targetTexture = TargetTexture;

            Debug.Log($"[VideoPlayerController] RenderTexture resized to {targetWidth}x{targetHeight}, isCreated={TargetTexture.IsCreated()}");

            // Notify listeners about the new texture
            OnRenderTextureResized?.Invoke(TargetTexture);
        }

        private void OnLoopPointReached(VideoPlayer source)
        {
            if (source != _videoPlayer) return;

            if (!source.isLooping)
            {
                SetState(PlayerState.Completed);
                OnVideoCompleted?.Invoke();
                // Free the hardware decoder now that the clip is done. Play()/Restart()
                // re-prepare on demand. Deferred one frame: we are inside a VideoPlayer
                // callback and Stop() here would tear down the object that is calling us.
                _releaseDecoderNextFrame = true;
            }
        }

        private void OnErrorReceived(VideoPlayer source, string message)
        {
            if (source != _videoPlayer)
            {
                Debug.LogWarning($"[VideoPlayerController] Ignoring error from a released player: {message}");
                return;
            }

            Debug.LogError($"[VideoPlayerController] VideoPlayer error: {message} ({ProcessDiagnostics.Snapshot()})");
            _loadingStartedAt = -1f;
            SetState(PlayerState.Error);
            _releaseDecoderNextFrame = true;
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
