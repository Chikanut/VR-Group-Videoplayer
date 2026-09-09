using System;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// Body of POST /open and of the WebSocket "open" command.
    /// All new fields are optional: an old server sends only file/mode/loop/placementMode.
    /// JsonUtility ignores unknown keys and leaves missing ones at their defaults.
    /// </summary>
    [Serializable]
    public class VideoOpenRequest
    {
        public string file;

        /// <summary>Legacy "360" / "2d". Still sent by every server for old players.</summary>
        public string mode;

        /// <summary>Canonical formatId ("180_sbs", "360_tb", ...). Optional.</summary>
        public string format;

        /// <summary>"flat" | "180" | "360". Wins over mode/format when present.</summary>
        public string projection;

        /// <summary>"mono" | "sbs" | "tb".</summary>
        public string stereo;

        public bool swapEyes;
        public float forwardYaw;
        public bool loop;
        public string placementMode;
        public bool autoRecenterOnOpen = true;
        public VideoAdvancedSettings advancedSettings;
    }

    /// <summary>
    /// Shared implementation of the "open" command for LanServer (HTTP) and ServerConnection (WS),
    /// so both paths resolve the format and apply overrides identically. Main thread only.
    /// </summary>
    public static class VideoOpenExecutor
    {
        private const string Tag = "[VideoOpenExecutor]";

        public static VideoFormat Execute(
            VideoOpenRequest request,
            ViewModeManager viewModeManager,
            VideoPlayerController videoPlayer,
            OrientationManager orientationManager)
        {
            if (request == null)
            {
                Debug.LogWarning($"{Tag} Null request ignored.");
                return null;
            }

            if (string.IsNullOrEmpty(request.file))
            {
                Debug.LogWarning($"{Tag} OPEN ignored: 'file' is missing or empty");
                return null;
            }

            VideoFormat current = viewModeManager != null ? viewModeManager.CurrentFormat : null;
            VideoFormat format = VideoFormatParser.Resolve(
                request.mode,
                request.format,
                request.projection,
                request.stereo,
                request.swapEyes,
                request.forwardYaw,
                request.file,
                current);

            Debug.Log($"{Tag} open file={request.file} format={format} loop={request.loop} placementMode={request.placementMode ?? "(default)"} autoRecenter={request.autoRecenterOnOpen}");

            if (viewModeManager != null)
            {
                viewModeManager.SetFormat(format);
                viewModeManager.ApplyAdvancedSettingsOverride(format.projection, request.advancedSettings);
                viewModeManager.ApplyPlacementOverride(format.projection, request.placementMode);
            }

            if (orientationManager != null)
            {
                orientationManager.SetForwardYaw(format.forwardYaw);
            }

            if (videoPlayer != null)
            {
                videoPlayer.IsLooping = request.loop;
            }

            // 180° content has nothing behind the viewer: they *must* start facing the content.
            bool forceRecenter = format.projection == VideoProjection.Hemisphere180 && !request.autoRecenterOnOpen;
            if (forceRecenter)
                Debug.Log($"{Tag} autoRecenterOnOpen=false ignored for 180° content; recentering anyway.");

            if (request.autoRecenterOnOpen || forceRecenter)
            {
                orientationManager?.Recenter();
            }

            videoPlayer?.Open(request.file);
            return format;
        }
    }
}
