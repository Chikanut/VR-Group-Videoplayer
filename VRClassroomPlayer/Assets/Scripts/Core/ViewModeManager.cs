using System;
using System.Collections.Generic;
using UnityEngine;

namespace VRClassroom
{
    public class ViewModeManager : MonoBehaviour
    {
        public event Action<ViewMode> OnModeChanged;

        public ViewMode CurrentMode { get; private set; }

        [SerializeField] private Transform vrCamera;
        [SerializeField] private Shader videoShaderOverride;

        [Header("View Mode Configs (optional — override material, mesh, transform per mode)")]
        [SerializeField] private ViewModeConfig[] viewModeConfigs;

        private readonly Dictionary<ViewMode, GameObject> _displayObjects = new Dictionary<ViewMode, GameObject>();
        private readonly Dictionary<ViewMode, Material> _materials = new Dictionary<ViewMode, Material>();
        private readonly Dictionary<ViewMode, ViewModeConfig> _configLookup = new Dictionary<ViewMode, ViewModeConfig>();

        private void Awake()
        {
            if (vrCamera == null)
            {
                vrCamera = Camera.main != null ? Camera.main.transform : transform;
                Debug.Log($"[ViewModeManager] VR camera auto-resolved to: {vrCamera.name}");
            }

            // Build config lookup
            if (viewModeConfigs != null)
            {
                foreach (var cfg in viewModeConfigs)
                {
                    if (cfg == null) continue;
                    _configLookup[cfg.viewMode] = cfg;
                    Debug.Log($"[ViewModeManager] Config loaded for mode: {cfg.viewMode}");
                }
            }

            Debug.Log("[ViewModeManager] Creating display geometry...");
            CreateDisplay(ViewMode.Sphere360);
            CreateDisplay(ViewMode.Flat2D);

            Debug.Log($"[ViewModeManager] Setting default mode: {PlayerConfig.DefaultViewMode}");
            SetMode(PlayerConfig.DefaultViewMode);
        }

        private void OnDestroy()
        {
            foreach (var kvp in _materials)
            {
                if (kvp.Value != null)
                    Destroy(kvp.Value);
            }
            _materials.Clear();
        }

        public void SetMode(ViewMode mode)
        {
            bool anyActive = false;
            foreach (var kvp in _displayObjects)
            {
                if (kvp.Value != null && kvp.Value.activeSelf)
                {
                    anyActive = true;
                    break;
                }
            }

            if (anyActive && mode == CurrentMode)
            {
                Debug.Log($"[ViewModeManager] Already in mode {mode}, skipping.");
                return;
            }

            Debug.Log($"[ViewModeManager] Switching mode: {CurrentMode} -> {mode}");
            CurrentMode = mode;

            foreach (var kvp in _displayObjects)
            {
                if (kvp.Value != null)
                    kvp.Value.SetActive(kvp.Key == mode);
            }

            string activeStates = "";
            foreach (var kvp in _displayObjects)
                activeStates += $" {kvp.Key}={kvp.Value?.activeSelf}";
            Debug.Log($"[ViewModeManager] Display states:{activeStates}");

            OnModeChanged?.Invoke(mode);
        }

        public void SetRenderTexture(RenderTexture rt)
        {
            Debug.Log($"[ViewModeManager] SetRenderTexture called: {(rt != null ? $"{rt.width}x{rt.height}" : "null")}");

            foreach (var kvp in _materials)
            {
                if (kvp.Value != null)
                {
                    kvp.Value.mainTexture = rt;
                    Debug.Log($"[ViewModeManager] Assigned RenderTexture to {kvp.Key} material.");
                }
                else
                {
                    Debug.LogError($"[ViewModeManager] {kvp.Key} material is null, cannot assign RenderTexture!");
                }
            }
        }

        private void CreateDisplay(ViewMode mode)
        {
            _configLookup.TryGetValue(mode, out ViewModeConfig config);

            // --- Geometry ---
            GameObject obj;
            if (config != null && config.meshOverride != null)
            {
                obj = new GameObject($"Video_{mode}");
                var mf = obj.AddComponent<MeshFilter>();
                mf.mesh = config.meshOverride;
                obj.AddComponent<MeshRenderer>();
                Debug.Log($"[ViewModeManager] Using mesh override for {mode}: {config.meshOverride.name}");
            }
            else
            {
                // Default primitives
                var primitiveType = mode == ViewMode.Sphere360
                    ? PrimitiveType.Sphere
                    : PrimitiveType.Quad;
                obj = GameObject.CreatePrimitive(primitiveType);
                obj.name = mode == ViewMode.Sphere360 ? "VideoSphere360" : "VideoQuad2D";
            }

            // Remove collider — not needed and avoids physics conflicts
            var collider = obj.GetComponent<Collider>();
            if (collider != null) Destroy(collider);
            obj.layer = 0;

            // --- Transform ---
            if (config != null)
            {
                bool parentToCam = config.parentToCamera;
                obj.transform.SetParent(parentToCam ? vrCamera : transform);
                obj.transform.localPosition = config.localPosition;
                obj.transform.localRotation = Quaternion.Euler(config.localRotation);
                obj.transform.localScale = config.localScale;
                Debug.Log($"[ViewModeManager] Config transform for {mode}: pos={config.localPosition}, rot={config.localRotation}, scale={config.localScale}, parentToCam={parentToCam}");
            }
            else
            {
                // Defaults matching original behaviour
                if (mode == ViewMode.Sphere360)
                {
                    obj.transform.SetParent(transform);
                    obj.transform.localPosition = Vector3.zero;
                    obj.transform.localScale = new Vector3(-100f, 100f, 100f);
                }
                else
                {
                    obj.transform.SetParent(vrCamera);
                    obj.transform.localPosition = new Vector3(0f, 0f, 10f);
                    obj.transform.localRotation = Quaternion.identity;
                    obj.transform.localScale = new Vector3(16f, 9f, 1f);
                }
            }

            // --- Material ---
            Material material;
            if (config != null)
            {
                material = VideoRenderShaderFactory.CreateFromConfig(config);
            }
            else
            {
                material = mode == ViewMode.Sphere360
                    ? VideoRenderShaderFactory.CreateSphereMaterial(videoShaderOverride)
                    : VideoRenderShaderFactory.CreateFlatMaterial(videoShaderOverride);
            }

            var renderer = obj.GetComponent<Renderer>();
            if (material != null)
            {
                renderer.material = material;
            }
            else
            {
                Debug.LogError($"[ViewModeManager] No compatible shader found for {mode}. Assign shader in config or inspector.");
            }

            obj.SetActive(false);

            _displayObjects[mode] = obj;
            _materials[mode] = material;

            Debug.Log($"[ViewModeManager] {mode} display created.");
        }
    }
}
