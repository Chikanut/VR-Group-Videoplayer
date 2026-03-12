using UnityEngine;

namespace VRClassroom
{
    public static class ViewModeParser
    {
        public static ViewMode Parse(string mode)
        {
            if (string.IsNullOrEmpty(mode))
            {
                return PlayerConfig.DefaultViewMode;
            }

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
                    Debug.LogWarning($"[ViewModeParser] Unknown mode '{mode}', defaulting to Flat2D.");
                    return ViewMode.Flat2D;
            }
        }
    }
}
