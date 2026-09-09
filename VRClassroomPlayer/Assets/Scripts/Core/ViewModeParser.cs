using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// Legacy "mode" string parser. Delegates to <see cref="VideoFormatParser"/>; stereo
    /// information in the string (e.g. "180_sbs") is dropped here — use
    /// <see cref="VideoFormatParser.TryParseFormatId"/> when the full format is needed.
    /// </summary>
    public static class ViewModeParser
    {
        public static ViewMode Parse(string mode)
        {
            if (string.IsNullOrEmpty(mode))
            {
                return PlayerConfig.DefaultViewMode;
            }

            if (VideoFormatParser.TryParseFormatId(mode, out var format))
            {
                return format.ToViewMode();
            }

            Debug.LogWarning($"[ViewModeParser] Unknown mode '{mode}', defaulting to Flat2D.");
            return ViewMode.Flat2D;
        }
    }
}
