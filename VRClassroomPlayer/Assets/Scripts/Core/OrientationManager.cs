using System;
using UnityEngine;

namespace VRClassroom
{
    public class OrientationManager : MonoBehaviour
    {
        public event Action OnRecentered;

        [SerializeField] private Transform vrCamera;
        [SerializeField] private ViewModeManager viewModeManager;
        [SerializeField] private float recenterDebounceSeconds = 1f;

        private float _lastRecenterTime = -1f;
        private bool _isRecentering;

        private void Awake()
        {
            if (vrCamera == null)
            {
                vrCamera = Camera.main != null ? Camera.main.transform : null;
                if (vrCamera != null)
                    Debug.Log($"[OrientationManager] VR camera auto-resolved to: {vrCamera.name}");
                else
                    Debug.LogWarning("[OrientationManager] Could not find VR camera.");
            }
        }

        public void Recenter()
        {
            if (_isRecentering)
            {
                Debug.Log("[OrientationManager] Recenter already in progress, ignoring duplicate request.");
                return;
            }

            if (Time.time - _lastRecenterTime < recenterDebounceSeconds)
            {
                Debug.Log("[OrientationManager] Recenter debounced, ignoring.");
                return;
            }

            _isRecentering = true;
            _lastRecenterTime = Time.time;

            try
            {
                // Rotate content (sphere/plane) so the "front" aligns with viewer's current gaze.
                // We capture the camera's Y rotation and apply it to the content parent.
                RecenterContent();

#if UNITY_ANDROID && !UNITY_EDITOR
                try
                {
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
                    Debug.LogError($"[OrientationManager] XR recenter failed: {e.Message}");
                }
#else
                Debug.Log("[OrientationManager] XR recenter not available in Editor; content rotation applied.");
#endif

                OnRecentered?.Invoke();
            }
            finally
            {
                _isRecentering = false;
            }
        }

        private void RecenterContent()
        {
            if (vrCamera == null)
            {
                Debug.LogWarning("[OrientationManager] Cannot recenter content: VR camera reference is null.");
                return;
            }

            if (viewModeManager == null)
            {
                Debug.LogWarning("[OrientationManager] Cannot recenter content: ViewModeManager reference is null.");
                return;
            }

            // Get camera's current Y-axis (yaw) rotation in world space.
            // This is the direction the viewer is looking at horizontally.
            float cameraYaw = vrCamera.eulerAngles.y;

            Debug.Log($"[OrientationManager] Recentering content to camera yaw: {cameraYaw:F1}°");

            // Apply yaw rotation to the ViewModeManager transform.
            // The sphere (Sphere360) is parented to ViewModeManager's transform (world space).
            // Rotating it so the "front" of the sphere content faces the viewer.
            viewModeManager.transform.rotation = Quaternion.Euler(0f, cameraYaw, 0f);

            Debug.Log($"[OrientationManager] ViewModeManager rotation set to (0, {cameraYaw:F1}, 0)");
        }
    }
}
