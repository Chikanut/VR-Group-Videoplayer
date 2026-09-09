using System;
using System.IO;

namespace VRClassroom
{
    /// <summary>
    /// On-device fallback detection from the Quest media naming convention:
    ///   &lt;name&gt;_&lt;projection&gt;_&lt;stereo&gt;.&lt;ext&gt;   e.g. reef-dive_180_LR.mp4, tour_360_TB.mov
    /// Only the end of the file name counts; a "360" in the middle of a title is ignored.
    /// Mirrors App/server/video_format.py::detect_format_from_filename so both sides agree.
    /// </summary>
    public static class VideoFormatDetector
    {
        private static readonly char[] Separators = { '_', '-', ' ', '.' };

        public static bool TryDetectFromFilename(string filename, out VideoProjection? projection, out StereoLayout? stereo)
        {
            projection = null;
            stereo = null;
            if (string.IsNullOrWhiteSpace(filename)) return false;

            string stem;
            try
            {
                stem = Path.GetFileNameWithoutExtension(filename.Trim());
            }
            catch (ArgumentException)
            {
                stem = filename.Trim();
            }

            string[] tokens = stem.ToLowerInvariant().Split(Separators, StringSplitOptions.RemoveEmptyEntries);
            if (tokens.Length == 0) return false;

            string last = tokens[tokens.Length - 1];
            if (VideoFormatParser.TryParseStereo(last, out var parsedStereo))
            {
                stereo = parsedStereo;
                if (tokens.Length >= 2 && TryProjectionToken(tokens[tokens.Length - 2], out var parsedProjection))
                    projection = parsedProjection;
            }
            else if (TryProjectionToken(last, out var parsedProjection))
            {
                projection = parsedProjection;
            }

            return projection.HasValue || stereo.HasValue;
        }

        /// <summary>Full format from the filename, or null when the name carries no usable suffix.</summary>
        public static VideoFormat DetectFromFilename(string filename)
        {
            if (!TryDetectFromFilename(filename, out var projection, out var stereo) || !projection.HasValue)
                return null;
            return new VideoFormat(projection.Value, stereo ?? StereoLayout.Mono);
        }

        private static bool TryProjectionToken(string token, out VideoProjection projection)
        {
            // "none" is not a filename token.
            if (VideoFormatParser.TryParseProjection(token, out projection) && projection != VideoProjection.None)
                return true;
            projection = VideoProjection.Sphere360;
            return false;
        }
    }
}
