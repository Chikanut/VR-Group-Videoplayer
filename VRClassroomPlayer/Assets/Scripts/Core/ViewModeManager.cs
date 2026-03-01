using System;
using UnityEngine;

namespace VRClassroom
{
    public class ViewModeManager : MonoBehaviour
    {
        private static readonly string[] VideoShaderCandidates =
        {
            "Unlit/Texture",
            "Universal Render Pipeline/Unlit",
            "Universal Render Pipeline/Lit",
            "Standard"
        };

        public event Action<ViewMode> OnModeChanged;

        public ViewMode CurrentMode { get; private set; }

        [SerializeField] private Transform vrCamera;
        [SerializeField] private Shader videoShaderOverride;

        private GameObject _sphere360;
        private GameObject _flat2D;
        private Material _sphereMaterial;
        private Material _flatMaterial;

        private void Awake()
        {
            if (vrCamera == null)
            {
                vrCamera = Camera.main != null ? Camera.main.transform : transform;
                Debug.Log($"[ViewModeManager] VR camera auto-resolved to: {vrCamera.name}");
            }

            Debug.Log("[ViewModeManager] Creating display geometry...");
            CreateSphere360();
            CreateFlat2D();

            Debug.Log($"[ViewModeManager] Setting default mode: {PlayerConfig.DefaultViewMode}");
            SetMode(PlayerConfig.DefaultViewMode);
        }

        private void OnDestroy()
        {
            if (_sphereMaterial != null) Destroy(_sphereMaterial);
            if (_flatMaterial != null) Destroy(_flatMaterial);
        }

        public void SetMode(ViewMode mode)
        {
            if (_sphere360 != null && _flat2D != null && mode == CurrentMode
                && (_sphere360.activeSelf || _flat2D.activeSelf))
            {
                Debug.Log($"[ViewModeManager] Already in mode {mode}, skipping.");
                return;
            }

            Debug.Log($"[ViewModeManager] Switching mode: {CurrentMode} -> {mode}");
            CurrentMode = mode;

            if (_sphere360 != null)
                _sphere360.SetActive(mode == ViewMode.Sphere360);

            if (_flat2D != null)
                _flat2D.SetActive(mode == ViewMode.Flat2D);

            Debug.Log($"[ViewModeManager] Sphere360 active={_sphere360?.activeSelf}, Flat2D active={_flat2D?.activeSelf}");

            OnModeChanged?.Invoke(mode);
        }

        public void SetRenderTexture(RenderTexture rt)
        {
            Debug.Log($"[ViewModeManager] SetRenderTexture called: {(rt != null ? $"{rt.width}x{rt.height}" : "null")}");

            if (_sphereMaterial != null)
            {
                _sphereMaterial.mainTexture = rt;
                Debug.Log("[ViewModeManager] Assigned RenderTexture to sphere material.");
            }
            else
            {
                Debug.LogError("[ViewModeManager] _sphereMaterial is null, cannot assign RenderTexture!");
            }

            if (_flatMaterial != null)
            {
                _flatMaterial.mainTexture = rt;
                Debug.Log("[ViewModeManager] Assigned RenderTexture to flat material.");
            }
            else
            {
                Debug.LogError("[ViewModeManager] _flatMaterial is null, cannot assign RenderTexture!");
            }
        }

        private void CreateSphere360()
        {
            _sphere360 = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            _sphere360.name = "VideoSphere360";
            _sphere360.transform.SetParent(transform);
            _sphere360.transform.localPosition = Vector3.zero;
            // Negative X scale inverts normals so video renders on the inside
            _sphere360.transform.localScale = new Vector3(-100f, 100f, 100f);

            // Remove collider — not needed and avoids physics conflicts
            var collider = _sphere360.GetComponent<Collider>();
            if (collider != null) Destroy(collider);

            // Set layer to avoid UI conflicts (use Default layer)
            _sphere360.layer = 0;

            var renderer = _sphere360.GetComponent<Renderer>();
            _sphereMaterial = CreateVideoMaterial(renderer, "sphere");

            if (_sphereMaterial != null)
            {
                renderer.material = _sphereMaterial;
            }

            _sphere360.SetActive(false);
            Debug.Log("[ViewModeManager] Sphere360 geometry created.");
        }

        private void CreateFlat2D()
        {
            _flat2D = GameObject.CreatePrimitive(PrimitiveType.Quad);
            _flat2D.name = "VideoQuad2D";
            // Child of camera so it moves with the user
            _flat2D.transform.SetParent(vrCamera);
            _flat2D.transform.localPosition = new Vector3(0f, 0f, 10f);
            _flat2D.transform.localRotation = Quaternion.identity;
            // 16:9 aspect ratio
            _flat2D.transform.localScale = new Vector3(16f, 9f, 1f);

            // Remove collider
            var collider = _flat2D.GetComponent<Collider>();
            if (collider != null) Destroy(collider);

            var renderer = _flat2D.GetComponent<Renderer>();
            _flatMaterial = CreateVideoMaterial(renderer, "flat quad");

            if (_flatMaterial != null)
            {
                renderer.material = _flatMaterial;
            }

            _flat2D.SetActive(false);
            Debug.Log("[ViewModeManager] Flat2D geometry created.");
        }

        private Material CreateVideoMaterial(Renderer renderer, string targetName)
        {
            if (renderer == null)
            {
                Debug.LogError($"[ViewModeManager] Renderer is missing for {targetName}.");
                return null;
            }

            var shader = FindFirstAvailableShader();
            if (shader != null)
            {
                Debug.Log($"[ViewModeManager] {targetName} shader found: {shader.name}");
                return new Material(shader);
            }

            Debug.LogError($"[ViewModeManager] No compatible shader found for {targetName}. Assign 'videoShaderOverride' in the inspector. Using primitive default material as fallback.");
            return renderer.material;
        }

        private Shader FindFirstAvailableShader()
        {
            if (videoShaderOverride != null)
            {
                return videoShaderOverride;
            }

            for (int i = 0; i < VideoShaderCandidates.Length; i++)
            {
                var shader = Shader.Find(VideoShaderCandidates[i]);
                if (shader != null)
                {
                    return shader;
                }
            }

            return null;
        }
    }
}
