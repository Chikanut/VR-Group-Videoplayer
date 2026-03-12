using System;
using System.IO;
using System.Linq;
using UnityEngine;

namespace VRClassroom
{
    public static class AndroidMediaScanner
    {
        public static int ScanDirectory(string directory)
        {
            if (string.IsNullOrEmpty(directory) || !Directory.Exists(directory))
            {
                return 0;
            }

            return ScanFiles(Directory.GetFiles(directory));
        }

        public static int ScanFiles(string[] paths)
        {
            string[] normalizedPaths = (paths ?? Array.Empty<string>())
                .Where(path => !string.IsNullOrWhiteSpace(path))
                .Select(path => path.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

            if (normalizedPaths.Length == 0)
            {
                return 0;
            }

#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using (var activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
                using (var mediaScanner = new AndroidJavaClass("android.media.MediaScannerConnection"))
                {
                    mediaScanner.CallStatic("scanFile", activity, normalizedPaths, null, null);
                }

                Debug.Log($"[AndroidMediaScanner] Queued media scan for {normalizedPaths.Length} file(s).");
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[AndroidMediaScanner] Media scan failed: {e.Message}");
                return 0;
            }
#else
            Debug.Log($"[AndroidMediaScanner] Editor/no-op scan for {normalizedPaths.Length} file(s).");
#endif

            return normalizedPaths.Length;
        }
    }
}
