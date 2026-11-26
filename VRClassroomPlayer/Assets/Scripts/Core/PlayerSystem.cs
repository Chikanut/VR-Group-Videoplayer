using System;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// C# side of Assets/Plugins/Android/PlayerSystem.java. Keep-awake, self-update and the
    /// settings profile moved to the headset agent (Agent.java). Main thread only. No-op in the Editor.
    /// </summary>
    public static class PlayerSystem
    {
        /// <summary>Puts the headset to sleep (virtual proximity FAR). Used by the legacy HTTP /sleep route.</summary>
        public static void Sleep() => Call("sleep");

        /// <summary>Starts the watchdog service, which hosts the agent.</summary>
        public static void StartWatchdog() => Call("startWatchdog");

        /// <summary>Call on pause: if the headset is going to sleep, the player closes itself and the watchdog reopens it on wake.</summary>
        public static void CloseIfAsleep() => Call("closeIfAsleep");

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
