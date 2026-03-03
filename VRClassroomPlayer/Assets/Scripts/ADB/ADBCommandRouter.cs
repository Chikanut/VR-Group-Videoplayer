using System.Collections.Generic;
using UnityEngine;

namespace VRClassroom
{
    public class ADBCommandRouter : MonoBehaviour
    {
        [SerializeField] private VideoPlayerController videoPlayer;
        [SerializeField] private ViewModeManager viewModeManager;
        [SerializeField] private OrientationManager orientationManager;
        [SerializeField] private StatusReporter statusReporter;
        [SerializeField] private ADBReceiverBridge adbReceiver;
        [SerializeField] private DebugLogPanel debugLogPanel;

        private bool _videoPlayerMissing;
        private bool _viewModeManagerMissing;
        private bool _orientationManagerMissing;
        private bool _statusReporterMissing;

        private void Start()
        {
            if (videoPlayer == null)
            {
                Debug.LogError("[ADBCommandRouter] VideoPlayerController reference is not assigned.");
                _videoPlayerMissing = true;
            }
            if (viewModeManager == null)
            {
                Debug.LogError("[ADBCommandRouter] ViewModeManager reference is not assigned.");
                _viewModeManagerMissing = true;
            }
            if (orientationManager == null)
            {
                Debug.LogError("[ADBCommandRouter] OrientationManager reference is not assigned.");
                _orientationManagerMissing = true;
            }
            if (statusReporter == null)
            {
                Debug.LogError("[ADBCommandRouter] StatusReporter reference is not assigned.");
                _statusReporterMissing = true;
            }

            if (adbReceiver != null)
            {
                adbReceiver.OnCommandReceived += HandleCommand;
            }
            else
            {
                Debug.LogError("[ADBCommandRouter] ADBReceiverBridge reference is not assigned.");
            }
        }

        private void OnDestroy()
        {
            if (adbReceiver != null)
                adbReceiver.OnCommandReceived -= HandleCommand;
        }

        public void HandleCommand(string action, Dictionary<string, string> extras)
        {
            Debug.Log($"[ADBCommandRouter] Handling action: {action}");

            switch (action.ToUpperInvariant())
            {
                case "OPEN":
                    HandleOpen(extras);
                    break;
                case "PLAY":
                    if (!_videoPlayerMissing)
                    {
                        Debug.Log("[ADBCommandRouter] Dispatching: Play()");
                        videoPlayer.Play();
                    }
                    break;
                case "PAUSE":
                    if (!_videoPlayerMissing)
                    {
                        Debug.Log("[ADBCommandRouter] Dispatching: Pause()");
                        videoPlayer.Pause();
                    }
                    break;
                case "STOP":
                    if (!_videoPlayerMissing)
                    {
                        Debug.Log("[ADBCommandRouter] Dispatching: Stop()");
                        videoPlayer?.Stop();
                        viewModeManager?.SetMode(ViewMode.None);
                    }
                    break;
                case "RESTART":
                    if (!_videoPlayerMissing)
                    {
                        Debug.Log("[ADBCommandRouter] Dispatching: Restart()");
                        videoPlayer.Restart();
                    }
                    break;
                case "RECENTER":
                    if (!_orientationManagerMissing)
                    {
                        Debug.Log("[ADBCommandRouter] Dispatching: Recenter()");
                        orientationManager.Recenter();
                    }
                    break;
                case "SET_MODE":
                    HandleSetMode(extras);
                    break;
                case "GET_STATUS":
                    if (!_statusReporterMissing)
                    {
                        Debug.Log("[ADBCommandRouter] Dispatching: ReportNow()");
                        statusReporter.ReportNow();
                    }
                    break;
                case "SET_LOOP":
                    HandleSetLoop(extras);
                    break;
                case "SET_VOLUME":
                    HandleSetVolume(extras);
                    break;
                case "TOGGLE_DEBUG":
                    if (debugLogPanel != null)
                    {
                        Debug.Log("[ADBCommandRouter] Dispatching: ToggleDebug()");
                        debugLogPanel.Toggle();
                    }
                    break;
                default:
                    Debug.LogWarning($"[ADBCommandRouter] Unknown action: {action}");
                    break;
            }
        }

        private void HandleOpen(Dictionary<string, string> extras)
        {
            if (_videoPlayerMissing) return;

            if (!extras.TryGetValue("file", out string file) || string.IsNullOrEmpty(file))
            {
                Debug.LogWarning("[ADBCommandRouter] OPEN command missing required 'file' extra.");
                return;
            }

            // Handle optional mode
            if (extras.TryGetValue("mode", out string mode) && !string.IsNullOrEmpty(mode))
            {
                if (!_viewModeManagerMissing)
                {
                    Debug.Log($"[ADBCommandRouter] Setting mode: {mode}");
                    viewModeManager.SetMode(ParseMode(mode));
                }
            }

            Debug.Log($"[ADBCommandRouter] Opening file: {file}");
            videoPlayer.Open(file);
        }

        private void HandleSetMode(Dictionary<string, string> extras)
        {
            if (_viewModeManagerMissing) return;

            if (extras.TryGetValue("mode", out string mode) && !string.IsNullOrEmpty(mode))
            {
                Debug.Log($"[ADBCommandRouter] Setting mode: {mode}");
                viewModeManager.SetMode(ParseMode(mode));
            }
            else
            {
                Debug.LogWarning("[ADBCommandRouter] SET_MODE command missing 'mode' extra.");
            }
        }

        private void HandleSetLoop(Dictionary<string, string> extras)
        {
            if (_videoPlayerMissing) return;

            if (extras.TryGetValue("loop", out string loop))
            {
                bool loopValue = loop.ToLowerInvariant() == "true";
                Debug.Log($"[ADBCommandRouter] Setting loop: {loopValue}");
                videoPlayer.IsLooping = loopValue;
            }
            else
            {
                Debug.LogWarning("[ADBCommandRouter] SET_LOOP command missing 'loop' extra.");
            }
        }


        private void HandleSetVolume(Dictionary<string, string> extras)
        {
            if (_videoPlayerMissing) return;

            float global = 1f;
            float personal = 1f;

            if (extras.TryGetValue("globalVolume", out string globalRaw))
                float.TryParse(globalRaw, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out global);

            if (extras.TryGetValue("personalVolume", out string personalRaw))
                float.TryParse(personalRaw, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out personal);

            videoPlayer.SetVolume(global, personal);
        }

        public static ViewMode ParseMode(string mode)
        {
            if (string.IsNullOrEmpty(mode))
                return PlayerConfig.DefaultViewMode;

            switch (mode.ToLowerInvariant())
            {
                case "360":
                case "360_mono":
                case "sphere":
                    return ViewMode.Sphere360;
                case "2d":
                case "flat":
                    return ViewMode.Flat2D;
                default:
                    Debug.LogWarning($"[ADBCommandRouter] Unknown mode '{mode}', defaulting to Flat2D.");
                    return ViewMode.Flat2D;
            }
        }
    }
}
