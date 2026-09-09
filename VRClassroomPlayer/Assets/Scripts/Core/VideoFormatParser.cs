using System;
using System.Text;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// formatId / projection / stereo strings ↔ <see cref="VideoFormat"/>, plus the
    /// backward-compatibility rules for the /open payload.
    ///
    /// Accepted spellings (case-insensitive, separators "_", "-", " ", "."):
    ///   projection: 2d, flat | 180, vr180 | 360, sphere | none
    ///   stereo:     mono | sbs, lr, 3dh | tb, ou, 3dv
    /// </summary>
    public static class VideoFormatParser
    {
        private const string Tag = "[VideoFormatParser]";
        private static readonly char[] Separators = { '_', '-', ' ', '.' };

        public static bool TryParseProjection(string value, out VideoProjection projection)
        {
            switch (Normalize(value))
            {
                case "2d":
                case "flat":
                case "flat2d":
                    projection = VideoProjection.Flat;
                    return true;
                case "180":
                case "vr180":
                case "hemisphere180":
                case "hemisphere":
                    projection = VideoProjection.Hemisphere180;
                    return true;
                case "360":
                case "sphere":
                case "sphere360":
                    projection = VideoProjection.Sphere360;
                    return true;
                case "none":
                    projection = VideoProjection.None;
                    return true;
                default:
                    projection = VideoProjection.Sphere360;
                    return false;
            }
        }

        public static bool TryParseStereo(string value, out StereoLayout stereo)
        {
            switch (Normalize(value))
            {
                case "mono":
                    stereo = StereoLayout.Mono;
                    return true;
                case "sbs":
                case "lr":
                case "3dh":
                case "sidebyside":
                case "leftright":
                    stereo = StereoLayout.SideBySide;
                    return true;
                case "tb":
                case "ou":
                case "3dv":
                case "topbottom":
                case "overunder":
                    stereo = StereoLayout.TopBottom;
                    return true;
                default:
                    stereo = StereoLayout.Mono;
                    return false;
            }
        }

        /// <summary>
        /// Parse a full formatId such as "180_sbs", "360_TB", "sphere", "flat", "180_LR".
        /// Token order does not matter. Returns false when no projection token is present.
        /// </summary>
        public static bool TryParseFormatId(string value, out VideoFormat format)
        {
            format = null;
            if (string.IsNullOrWhiteSpace(value)) return false;

            string[] tokens = value.Trim().ToLowerInvariant().Split(Separators, StringSplitOptions.RemoveEmptyEntries);
            bool hasProjection = false;
            var projection = VideoProjection.Sphere360;
            var stereo = StereoLayout.Mono;

            foreach (string token in tokens)
            {
                if (!hasProjection && TryParseProjection(token, out var parsedProjection))
                {
                    projection = parsedProjection;
                    hasProjection = true;
                }
                else if (TryParseStereo(token, out var parsedStereo))
                {
                    stereo = parsedStereo;
                }
            }

            if (!hasProjection) return false;
            if (projection == VideoProjection.Flat || projection == VideoProjection.None)
                stereo = StereoLayout.Mono;

            format = new VideoFormat(projection, stereo);
            return true;
        }

        public static string ToFormatId(VideoFormat format)
        {
            if (format == null) return "";
            string projection;
            switch (format.projection)
            {
                case VideoProjection.Flat: return "2d";
                case VideoProjection.None: return "none";
                case VideoProjection.Hemisphere180: projection = "180"; break;
                default: projection = "360"; break;
            }

            switch (format.stereo)
            {
                case StereoLayout.SideBySide: return projection + "_sbs";
                case StereoLayout.TopBottom: return projection + "_tb";
                default: return projection;
            }
        }

        public static string ProjectionId(VideoProjection projection)
        {
            switch (projection)
            {
                case VideoProjection.Flat: return "flat";
                case VideoProjection.Hemisphere180: return "180";
                case VideoProjection.Sphere360: return "360";
                default: return "none";
            }
        }

        public static string StereoId(StereoLayout stereo)
        {
            switch (stereo)
            {
                case StereoLayout.SideBySide: return "sbs";
                case StereoLayout.TopBottom: return "tb";
                default: return "mono";
            }
        }

        /// <summary>"360" for any spherical content (incl. 180°), "2d" otherwise. Matches what old servers expect.</summary>
        public static string LegacyModeFor(VideoFormat format)
        {
            return format != null && format.IsSpherical ? "360" : "2d";
        }

        /// <summary>
        /// Resolve the effective format from an /open payload following the compatibility rules:
        ///   1. explicit <paramref name="projection"/> / <paramref name="stereo"/> win;
        ///   2. otherwise <paramref name="formatId"/> ("180_sbs" ...);
        ///   3. otherwise legacy <paramref name="mode"/> ("360"/"2d"), refined by the filename suffix
        ///      when the server is too old to know about stereo (new player + old server);
        ///   4. otherwise the current format, or 360 mono when nothing is playing.
        /// Conflicts between explicit fields and legacy mode are logged, explicit fields win.
        /// </summary>
        public static VideoFormat Resolve(
            string mode,
            string formatId,
            string projection,
            string stereo,
            bool swapEyes,
            float forwardYaw,
            string filename,
            VideoFormat current)
        {
            VideoFormat result = null;
            string source;

            if (TryParseProjection(projection, out var explicitProjection))
            {
                var explicitStereo = StereoLayout.Mono;
                if (!string.IsNullOrEmpty(stereo) && !TryParseStereo(stereo, out explicitStereo))
                {
                    Debug.LogWarning($"{Tag} Unknown stereo layout '{stereo}', using mono.");
                    explicitStereo = StereoLayout.Mono;
                }
                result = new VideoFormat(explicitProjection, explicitStereo);
                source = "projection/stereo";

                if (!string.IsNullOrEmpty(mode) && TryParseFormatId(mode, out var legacyFromMode)
                    && LegacyModeFor(legacyFromMode) != LegacyModeFor(result))
                {
                    Debug.LogWarning($"{Tag} mode='{mode}' contradicts projection='{projection}'; explicit projection wins.");
                }
            }
            else if (TryParseFormatId(formatId, out var fromFormatId))
            {
                result = fromFormatId;
                source = "format";
            }
            else if (TryParseFormatId(mode, out var fromMode))
            {
                result = fromMode;
                source = "mode";

                // Old server: only "360"/"2d" is known. If the file follows the Quest naming
                // convention (_180_LR, _360_TB ...) the player can still show it correctly.
                if (result.projection == VideoProjection.Sphere360
                    && VideoFormatDetector.TryDetectFromFilename(filename, out var nameProjection, out var nameStereo))
                {
                    if (nameProjection.HasValue && nameProjection.Value != VideoProjection.Flat)
                        result.projection = nameProjection.Value;
                    if (nameStereo.HasValue)
                        result.stereo = nameStereo.Value;
                    source = "mode+filename";
                }
            }
            else
            {
                if (!string.IsNullOrEmpty(mode))
                    Debug.LogWarning($"{Tag} Unknown mode '{mode}'.");

                if (current != null && current.projection != VideoProjection.None)
                {
                    result = current.Clone();
                    source = "current";
                }
                else if (VideoFormatDetector.TryDetectFromFilename(filename, out var nameProjection, out var nameStereo) && nameProjection.HasValue)
                {
                    result = new VideoFormat(nameProjection.Value, nameStereo ?? StereoLayout.Mono);
                    source = "filename";
                }
                else
                {
                    result = VideoFormat.Default;
                    source = "default";
                }
            }

            if (result.projection == VideoProjection.Flat || result.projection == VideoProjection.None)
                result.stereo = StereoLayout.Mono;

            result.swapEyes = swapEyes;
            result.forwardYaw = forwardYaw;

            Debug.Log($"{Tag} Resolved format {result} (source={source}, mode={mode ?? "-"}, format={formatId ?? "-"}, projection={projection ?? "-"}, stereo={stereo ?? "-"}, file={filename ?? "-"})");
            return result;
        }

        private static string Normalize(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return "";
            var sb = new StringBuilder(value.Length);
            foreach (char c in value.Trim().ToLowerInvariant())
            {
                if (c == '_' || c == '-' || c == ' ' || c == '.') continue;
                sb.Append(c);
            }
            return sb.ToString();
        }
    }
}
