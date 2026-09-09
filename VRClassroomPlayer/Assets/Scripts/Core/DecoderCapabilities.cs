using System;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// What the headset can actually decode, queried once from Android MediaCodecList
    /// and reported to the server in /status ("decoderCaps") so the control panel can
    /// warn about 8K / 10-bit files before class. Hardware decoders only (software
    /// "OMX.google.*" / "c2.android.*" are ignored: they cannot do 8K in real time).
    /// Free storage is refreshed every 30 s because it changes as videos are pushed.
    /// </summary>
    public static class DecoderCapabilities
    {
        private const string Tag = "[DecoderCapabilities]";
        private const float StorageRefreshSeconds = 30f;

        public static bool Queried { get; private set; }
        public static bool Available { get; private set; }

        public static int HevcMaxWidth { get; private set; }
        public static int HevcMaxHeight { get; private set; }
        public static bool HevcMain10 { get; private set; }
        public static string HevcMaxLevel { get; private set; } = "";
        public static int HevcMaxFrameRateAt8K { get; private set; }
        public static bool HevcSupports8192x4096 { get; private set; }
        public static bool HevcSupports5760x5760 { get; private set; }
        public static string HevcDecoderName { get; private set; } = "";

        public static int AvcMaxWidth { get; private set; }
        public static int AvcMaxHeight { get; private set; }
        public static string AvcDecoderName { get; private set; } = "";

        public static int MaxTextureSize => SystemInfo.maxTextureSize;
        public static long StorageFreeBytes { get; private set; } = -1;
        public static long StorageTotalBytes { get; private set; } = -1;

        private static float _lastStorageRefresh = -1000f;

        /// <summary>Query once (cheap to call repeatedly).</summary>
        public static void EnsureQueried()
        {
            if (Queried) return;
            Queried = true;

#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                QueryAndroid();
                Available = true;
                Debug.Log($"{Tag} HEVC: max {HevcMaxWidth}x{HevcMaxHeight}, Main10={HevcMain10}, level={HevcMaxLevel}, " +
                          $"8192x4096={HevcSupports8192x4096}, 5760x5760={HevcSupports5760x5760}, fps@8K={HevcMaxFrameRateAt8K}, decoder={HevcDecoderName}; " +
                          $"AVC: max {AvcMaxWidth}x{AvcMaxHeight} ({AvcDecoderName}); maxTextureSize={MaxTextureSize}");
            }
            catch (Exception e)
            {
                Available = false;
                Debug.LogWarning($"{Tag} MediaCodecList query failed: {e.GetType().Name}: {e.Message}");
            }
#else
            Available = false;
            Debug.Log($"{Tag} Decoder query is Android-only; maxTextureSize={MaxTextureSize}");
#endif
            RefreshStorage(force: true);
        }

        public static void RefreshStorage(bool force = false)
        {
            if (!force && Time.realtimeSinceStartup - _lastStorageRefresh < StorageRefreshSeconds) return;
            _lastStorageRefresh = Time.realtimeSinceStartup;

#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var statFs = new AndroidJavaObject("android.os.StatFs", PlayerConfig.VideoPath.TrimEnd('/')))
                {
                    StorageFreeBytes = statFs.Call<long>("getAvailableBytes");
                    StorageTotalBytes = statFs.Call<long>("getTotalBytes");
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"{Tag} StatFs failed: {e.Message}");
            }
#else
            try
            {
                var drive = new System.IO.DriveInfo(System.IO.Path.GetPathRoot(Application.persistentDataPath));
                StorageFreeBytes = drive.AvailableFreeSpace;
                StorageTotalBytes = drive.TotalSize;
            }
            catch
            {
                // ignore: not critical in the editor
            }
#endif
        }

        /// <summary>JSON object for /status. Always valid JSON, even when nothing could be queried.</summary>
        public static string ToJson()
        {
            EnsureQueried();
            RefreshStorage();

            var sb = new StringBuilder(384);
            sb.Append('{');
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"available\":{0},", Available ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"hevcMaxWidth\":{0},", HevcMaxWidth);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"hevcMaxHeight\":{0},", HevcMaxHeight);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"hevcMain10\":{0},", HevcMain10 ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"hevcMaxLevel\":\"{0}\",", StatusReporter.EscapeJson(HevcMaxLevel));
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"hevcMaxFrameRateAt8K\":{0},", HevcMaxFrameRateAt8K);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"hevcSupports8192x4096\":{0},", HevcSupports8192x4096 ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"hevcSupports5760x5760\":{0},", HevcSupports5760x5760 ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"hevcDecoder\":\"{0}\",", StatusReporter.EscapeJson(HevcDecoderName));
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"avcMaxWidth\":{0},", AvcMaxWidth);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"avcMaxHeight\":{0},", AvcMaxHeight);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"maxTextureSize\":{0},", MaxTextureSize);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"maxRenderTextureDimension\":{0},", PlayerRenderSettings.MaxTextureDimension);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"systemMemoryMb\":{0},", SystemInfo.systemMemorySize);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"graphicsMemoryMb\":{0},", SystemInfo.graphicsMemorySize);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"storageFreeBytes\":{0},", StorageFreeBytes);
            sb.AppendFormat(CultureInfo.InvariantCulture, "\"storageTotalBytes\":{0}", StorageTotalBytes);
            sb.Append('}');
            return sb.ToString();
        }

#if UNITY_ANDROID && !UNITY_EDITOR
        private const int RegularCodecs = 1; // MediaCodecList.REGULAR_CODECS
        private const int HevcProfileMain10 = 2; // MediaCodecInfo.CodecProfileLevel.HEVCProfileMain10

        private static void QueryAndroid()
        {
            using (var codecList = new AndroidJavaObject("android.media.MediaCodecList", RegularCodecs))
            using (var infos = codecList.Call<AndroidJavaObject>("getCodecInfos"))
            {
                if (infos == null) return;
                var raw = infos.GetRawObject();
                int count = AndroidJNI.GetArrayLength(raw);
                for (int i = 0; i < count; i++)
                {
                    var element = AndroidJNI.GetObjectArrayElement(raw, i);
                    if (element == IntPtr.Zero) continue;
                    using (var info = new AndroidJavaObject(element))
                    {
                        InspectCodec(info);
                    }
                }
            }
        }

        private static void InspectCodec(AndroidJavaObject info)
        {
            if (info.Call<bool>("isEncoder")) return;
            string name = info.Call<string>("getName") ?? "";
            string lowerName = name.ToLowerInvariant();
            if (lowerName.StartsWith("omx.google.") || lowerName.StartsWith("c2.android.") || lowerName.Contains(".sw."))
                return; // software decoder

            string[] types = info.Call<string[]>("getSupportedTypes");
            if (types == null) return;

            foreach (string type in types)
            {
                bool isHevc = string.Equals(type, "video/hevc", StringComparison.OrdinalIgnoreCase);
                bool isAvc = string.Equals(type, "video/avc", StringComparison.OrdinalIgnoreCase);
                if (!isHevc && !isAvc) continue;

                using (var caps = info.Call<AndroidJavaObject>("getCapabilitiesForType", type))
                using (var videoCaps = caps.Call<AndroidJavaObject>("getVideoCapabilities"))
                {
                    int maxWidth = RangeUpperInt(videoCaps, "getSupportedWidths");
                    int maxHeight = RangeUpperInt(videoCaps, "getSupportedHeights");

                    if (isAvc)
                    {
                        if (maxWidth * maxHeight > AvcMaxWidth * AvcMaxHeight)
                        {
                            AvcMaxWidth = maxWidth;
                            AvcMaxHeight = maxHeight;
                            AvcDecoderName = name;
                        }
                        continue;
                    }

                    if (maxWidth * maxHeight < HevcMaxWidth * HevcMaxHeight) continue;

                    HevcMaxWidth = maxWidth;
                    HevcMaxHeight = maxHeight;
                    HevcDecoderName = name;
                    HevcSupports8192x4096 = SafeIsSizeSupported(videoCaps, 8192, 4096);
                    HevcSupports5760x5760 = SafeIsSizeSupported(videoCaps, 5760, 5760);
                    HevcMaxFrameRateAt8K = HevcSupports8192x4096 ? SafeMaxFrameRate(videoCaps, 8192, 4096) : 0;

                    HevcMain10 = false;
                    int maxLevelFlag = 0;
                    using (var profileLevels = caps.Get<AndroidJavaObject>("profileLevels"))
                    {
                        if (profileLevels != null)
                        {
                            var raw = profileLevels.GetRawObject();
                            int count = AndroidJNI.GetArrayLength(raw);
                            for (int i = 0; i < count; i++)
                            {
                                var element = AndroidJNI.GetObjectArrayElement(raw, i);
                                if (element == IntPtr.Zero) continue;
                                using (var profileLevel = new AndroidJavaObject(element))
                                {
                                    int profile = profileLevel.Get<int>("profile");
                                    int level = profileLevel.Get<int>("level");
                                    if (profile == HevcProfileMain10) HevcMain10 = true;
                                    if (level > maxLevelFlag) maxLevelFlag = level;
                                }
                            }
                        }
                    }
                    HevcMaxLevel = HevcLevelName(maxLevelFlag);
                }
            }
        }

        private static int RangeUpperInt(AndroidJavaObject videoCaps, string method)
        {
            try
            {
                using (var range = videoCaps.Call<AndroidJavaObject>(method))
                using (var upper = range.Call<AndroidJavaObject>("getUpper"))
                {
                    return upper.Call<int>("intValue");
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"{Tag} {method} failed: {e.Message}");
                return 0;
            }
        }

        private static bool SafeIsSizeSupported(AndroidJavaObject videoCaps, int width, int height)
        {
            try
            {
                return videoCaps.Call<bool>("isSizeSupported", width, height);
            }
            catch (Exception)
            {
                return false;
            }
        }

        private static int SafeMaxFrameRate(AndroidJavaObject videoCaps, int width, int height)
        {
            try
            {
                using (var range = videoCaps.Call<AndroidJavaObject>("getSupportedFrameRatesFor", width, height))
                using (var upper = range.Call<AndroidJavaObject>("getUpper"))
                {
                    return (int)Math.Floor(upper.Call<double>("doubleValue"));
                }
            }
            catch (Exception)
            {
                return 0;
            }
        }

        /// <summary>MediaCodecInfo.CodecProfileLevel.HEVC*TierLevel* flag -> "6.1" style string.</summary>
        private static string HevcLevelName(int flag)
        {
            if (flag <= 0) return "";
            // Flags are 1 << n with n even = main tier, n odd = high tier, in level order.
            int bit = 0;
            while ((1 << bit) < flag && bit < 30) bit++;
            if ((1 << bit) != flag) return flag.ToString(CultureInfo.InvariantCulture);
            string[] levels = { "1", "2", "2.1", "3", "3.1", "4", "4.1", "5", "5.1", "5.2", "6", "6.1", "6.2" };
            int levelIndex = bit / 2;
            string tier = (bit % 2 == 1) ? " high" : "";
            return levelIndex < levels.Length ? levels[levelIndex] + tier : flag.ToString(CultureInfo.InvariantCulture);
        }
#endif
    }
}
