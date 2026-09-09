using System;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// Complete description of how a video has to be displayed: projection geometry,
    /// stereo packing and the small corrections that go with them.
    /// Serializable so it can travel through JsonUtility and be inspected in the editor.
    /// </summary>
    [Serializable]
    public class VideoFormat
    {
        public VideoProjection projection = VideoProjection.Sphere360;
        public StereoLayout stereo = StereoLayout.Mono;

        /// <summary>Material was exported with the eyes exchanged: swap left/right at render time.</summary>
        public bool swapEyes;

        /// <summary>
        /// Longitude of the video (degrees, positive = to the right of the frame centre) that has
        /// to face the viewer after recenter. 0 keeps the frame centre in front.
        /// </summary>
        public float forwardYaw;

        /// <summary>Vertical field of view of the content. 180 for 1:1 VR180, 90 for 180x90 material.</summary>
        public float verticalFovDeg = 180f;

        public VideoFormat()
        {
        }

        public VideoFormat(VideoProjection projection, StereoLayout stereo = StereoLayout.Mono, bool swapEyes = false, float forwardYaw = 0f)
        {
            this.projection = projection;
            this.stereo = stereo;
            this.swapEyes = swapEyes;
            this.forwardYaw = forwardYaw;
        }

        public static VideoFormat None => new VideoFormat(VideoProjection.None);
        public static VideoFormat Default => new VideoFormat(VideoProjection.Sphere360);

        public bool IsStereo => stereo != StereoLayout.Mono && projection != VideoProjection.None;
        public bool IsSpherical => projection == VideoProjection.Sphere360 || projection == VideoProjection.Hemisphere180;

        /// <summary>Canonical id shared with the server: 2d, 360, 360_sbs, 360_tb, 180, 180_sbs, 180_tb.</summary>
        public string FormatId => VideoFormatParser.ToFormatId(this);

        /// <summary>The "mode" value pre-stereo servers/players understand ("360" or "2d").</summary>
        public string LegacyMode => VideoFormatParser.LegacyModeFor(this);

        public VideoFormat Clone()
        {
            return new VideoFormat(projection, stereo, swapEyes, forwardYaw) { verticalFovDeg = verticalFovDeg };
        }

        public bool Equals(VideoFormat other)
        {
            if (other == null) return false;
            return projection == other.projection
                   && stereo == other.stereo
                   && swapEyes == other.swapEyes
                   && Mathf.Approximately(forwardYaw, other.forwardYaw)
                   && Mathf.Approximately(verticalFovDeg, other.verticalFovDeg);
        }

        public override bool Equals(object obj) => Equals(obj as VideoFormat);

        public override int GetHashCode()
        {
            unchecked
            {
                int hash = (int)projection;
                hash = hash * 31 + (int)stereo;
                hash = hash * 31 + (swapEyes ? 1 : 0);
                hash = hash * 31 + forwardYaw.GetHashCode();
                return hash;
            }
        }

        public override string ToString()
        {
            string text = FormatId;
            if (swapEyes) text += " swapEyes";
            if (!Mathf.Approximately(forwardYaw, 0f)) text += $" yaw={forwardYaw:F0}";
            return text;
        }

        // ─── Legacy ViewMode bridge ─────────────────────────────────────────────

        public static VideoProjection ProjectionOf(ViewMode mode)
        {
            switch (mode)
            {
                case ViewMode.Flat2D: return VideoProjection.Flat;
                case ViewMode.Sphere360: return VideoProjection.Sphere360;
                case ViewMode.Hemisphere180: return VideoProjection.Hemisphere180;
                default: return VideoProjection.None;
            }
        }

        public static ViewMode ToViewMode(VideoProjection projection)
        {
            switch (projection)
            {
                case VideoProjection.Flat: return ViewMode.Flat2D;
                case VideoProjection.Sphere360: return ViewMode.Sphere360;
                case VideoProjection.Hemisphere180: return ViewMode.Hemisphere180;
                default: return ViewMode.None;
            }
        }

        public static VideoFormat FromViewMode(ViewMode mode)
        {
            return new VideoFormat(ProjectionOf(mode));
        }

        public ViewMode ToViewMode() => ToViewMode(projection);

        /// <summary>Short label for HUD / logs, e.g. "180° 3D SBS".</summary>
        public string DisplayLabel
        {
            get
            {
                string geometry;
                switch (projection)
                {
                    case VideoProjection.Flat: return "2D";
                    case VideoProjection.Hemisphere180: geometry = "180°"; break;
                    case VideoProjection.Sphere360: geometry = "360°"; break;
                    default: return "";
                }

                switch (stereo)
                {
                    case StereoLayout.SideBySide: return geometry + " 3D SBS";
                    case StereoLayout.TopBottom: return geometry + " 3D TB";
                    default: return geometry;
                }
            }
        }
    }
}
