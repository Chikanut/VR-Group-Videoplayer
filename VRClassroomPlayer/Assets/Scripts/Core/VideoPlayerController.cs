using System;
using System.IO;
using UnityEngine;
using UnityEngine.Video;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine.Android;
#endif

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
            EnsureExternalVideoAccess();
            LogVideoDirectoryState();

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
                    RegisterFileInMediaLibrary(file);
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

            // Support both full paths and filenames relative to VideoPath
            string fullPath = filename.StartsWith("/") ? filename : PlayerConfig.VideoPath + filename;
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

            RegisterFileInMediaLibrary(fullPath);

            Debug.Log("[VideoPlayerController] File exists, preparing playback...");
            CurrentFile = filename;
            _videoPlayer.url = "file://" + fullPath;

            SetState(PlayerState.Loading);
            _videoPlayer.Prepare();
        }

        private void RegisterFileInMediaLibrary(string fullPath)
        {
            if (string.IsNullOrEmpty(fullPath) || !File.Exists(fullPath))
                return;

#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using (var activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
                using (var uriClass = new AndroidJavaClass("android.net.Uri"))
                using (var mediaScannerClass = new AndroidJavaClass("android.media.MediaScannerConnection"))
                {
                    using (var javaFile = new AndroidJavaObject("java.io.File", fullPath))
                    using (var fileUri = uriClass.CallStatic<AndroidJavaObject>("fromFile", javaFile))
                    using (var intent = new AndroidJavaObject("android.content.Intent", "android.intent.action.MEDIA_SCANNER_SCAN_FILE"))
                    {
                        intent.Call<AndroidJavaObject>("setData", fileUri);
                        activity.Call("sendBroadcast", intent);
                    }

                    string[] paths = { fullPath };
                    mediaScannerClass.CallStatic("scanFile", activity, paths, null, null);
                }

                Debug.Log($"[VideoPlayerController] Media scan requested for file: {fullPath}");
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"[VideoPlayerController] Media registration failed for '{fullPath}'. Exception={exception.GetType().Name}, message={exception.Message}");
            }
#endif
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
