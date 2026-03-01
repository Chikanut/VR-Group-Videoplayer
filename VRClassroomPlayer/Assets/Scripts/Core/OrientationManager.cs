using System;
using UnityEngine;

namespace VRClassroom
{
    public class OrientationManager : MonoBehaviour
    {
        public event Action OnRecentered;

        private float _lastRecenterTime = -1f;
        private const float DebounceDuration = 1f;

        public void Recenter()
        {
            if (Time.time - _lastRecenterTime < DebounceDuration)
            {
                Debug.Log("[OrientationManager] Recenter debounced, ignoring.");
                return;
            }

            _lastRecenterTime = Time.time;

#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                // Use Unity XR InputSubsystem recenter
                var subsystems = new System.Collections.Generic.List<UnityEngine.XR.XRInputSubsystem>();
                UnityEngine.SubsystemManager.GetSubsystems(subsystems);
                bool recentered = false;

                foreach (var subsystem in subsystems)
                {
                    if (subsystem.running)
                    {
                        subsystem.TryRecenter();
                        recentered = true;
                        break;
                    }
                }

                if (!recentered)
                {
                    Debug.LogWarning("[OrientationManager] No running XR input subsystem found for recenter.");
                }
                else
                {
                    Debug.Log("[OrientationManager] Recentered via XR InputSubsystem.");
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[OrientationManager] Recenter failed: {e.Message}");
            }
#else
            Debug.LogWarning("[OrientationManager] Recenter not available in Editor.");
#endif

            OnRecentered?.Invoke();
        }
    }
}
