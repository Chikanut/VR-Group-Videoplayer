using System;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// C# side of Assets/Plugins/Android/PlayerSystem.java: keep-awake, relaunch watchdog,
    /// silent self-update. Main thread only. No-op in the Editor.
    /// </summary>
    public static class PlayerSystem
    {
        public static void SetKeepAwake(bool keepAwake) => Call("setKeepAwake", keepAwake);

        /// <summary>Puts the headset to sleep (virtual proximity FAR). Woken by the watchdog's POST :8081/wake or the power button.</summary>
        public static void Sleep() => Call("sleep");

        public static void StartWatchdog() => Call("startWatchdog");

        /// <summary>Installs a downloaded APK file (Java checks its sha256 first).</summary>
        public static void InstallUpdate(string apkPath, string sha256) => Call("installUpdate", apkPath, sha256);

        /// <summary>Path of the installed APK, to compare its sha256 with an offered update.</summary>
        public static string InstalledApkPath()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using (var activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
                using (var appInfo = activity.Call<AndroidJavaObject>("getApplicationInfo"))
                {
                    return appInfo.Get<string>("sourceDir");
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[PlayerSystem] InstalledApkPath failed: {e.Message}");
            }
#endif
            return null;
        }

        private static void Call(string method, params object[] args)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using (var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using (var activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
                using (var system = new AndroidJavaClass("com.vrclass.player.PlayerSystem"))
                {
                    var all = new object[args.Length + 1];
                    all[0] = activity;
                    args.CopyTo(all, 1);
                    system.CallStatic(method, all);
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[PlayerSystem] {method} failed: {e.Message}");
            }
#else
            Debug.Log($"[PlayerSystem] {method} skipped (not on Android)");
#endif
        }
    }
}
