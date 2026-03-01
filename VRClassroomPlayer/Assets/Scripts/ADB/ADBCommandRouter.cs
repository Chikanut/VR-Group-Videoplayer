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
            switch (action.ToUpperInvariant())
            {
                case "OPEN":
                    HandleOpen(extras);
                    break;
                case "PLAY":
                    if (!_videoPlayerMissing) videoPlayer.Play();
                    break;
                case "PAUSE":
                    if (!_videoPlayerMissing) videoPlayer.Pause();
                    break;
                case "STOP":
                    if (!_videoPlayerMissing) videoPlayer.Stop();
                    break;
                case "RESTART":
                    if (!_videoPlayerMissing) videoPlayer.Restart();
                    break;
                case "RECENTER":
                    if (!_orientationManagerMissing) orientationManager.Recenter();
                    break;
                case "SET_MODE":
                    HandleSetMode(extras);
                    break;
                case "GET_STATUS":
                    if (!_statusReporterMissing) statusReporter.ReportNow();
                    break;
                case "SET_LOOP":
                    HandleSetLoop(extras);
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
                    viewModeManager.SetMode(ParseMode(mode));
            }

            videoPlayer.Open(file);
        }

        private void HandleSetMode(Dictionary<string, string> extras)
        {
            if (_viewModeManagerMissing) return;

            if (extras.TryGetValue("mode", out string mode) && !string.IsNullOrEmpty(mode))
            {
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
                videoPlayer.IsLooping = loop.ToLowerInvariant() == "true";
            }
            else
            {
                Debug.LogWarning("[ADBCommandRouter] SET_LOOP command missing 'loop' extra.");
            }
        }

        public static ViewMode ParseMode(string mode)
        {
            if (string.IsNullOrEmpty(mode))
                return PlayerConfig.DefaultViewMode;

            switch (mode.ToLowerInvariant())
            {
                case "360":
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
