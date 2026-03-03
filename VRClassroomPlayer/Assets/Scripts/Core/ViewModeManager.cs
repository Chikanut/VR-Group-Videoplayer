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
        [SerializeField] GameObject logoObject;
        [SerializeField] private Shader videoShaderOverride;

        [Header("View Mode Configs (optional — override material, mesh, transform per mode)")]
        [SerializeField] private ViewModeConfig[] viewModeConfigs;

        private readonly Dictionary<ViewMode, GameObject> _displayObjects = new Dictionary<ViewMode, GameObject>();
        private readonly Dictionary<ViewMode, Material> _materials = new Dictionary<ViewMode, Material>();
        private readonly Dictionary<ViewMode, ViewModeConfig> _configLookup = new Dictionary<ViewMode, ViewModeConfig>();
        private readonly Dictionary<ViewMode, VideoAdvancedSettings> _runtimeOverrides = new Dictionary<ViewMode, VideoAdvancedSettings>();

        private void Awake()
        {
            if (vrCamera == null)
            {
                vrCamera = Camera.main != null ? Camera.main.transform : transform;
                Debug.Log($"[ViewModeManager] VR camera auto-resolved to: {vrCamera.name}");
            }

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
            CreateDisplay(ViewMode.None);

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

        public void ApplyAdvancedSettingsOverride(ViewMode mode, VideoAdvancedSettings advancedSettings)
        {
            if (advancedSettings != null)
            {
                _runtimeOverrides[mode] = advancedSettings;
            }
            else
            {
                _runtimeOverrides.Remove(mode);
            }

            ApplyResolvedSettings(mode);
        }

        private void CreateDisplay(ViewMode mode)
        {
            _configLookup.TryGetValue(mode, out ViewModeConfig config);

            GameObject obj;
            if (config != null && config.meshOverride != null)
            {
                obj = new GameObject($"Video_{mode}");
                var mf = obj.AddComponent<MeshFilter>();
                mf.mesh = config.meshOverride;
                obj.AddComponent<MeshRenderer>();
                Debug.Log($"[ViewModeManager] Using mesh override for {mode}: {config.meshOverride.name}");
            }
            else if (mode == ViewMode.None)
            {
                obj = logoObject;
                Debug.Log($"[ViewModeManager] Created empty GameObject for {mode} mode.");
            }
            else
            {
                var primitiveType = mode == ViewMode.Sphere360
                    ? PrimitiveType.Sphere
                    : PrimitiveType.Quad;
                obj = GameObject.CreatePrimitive(primitiveType);
                obj.name = mode == ViewMode.Sphere360 ? "VideoSphere360" : "VideoQuad2D";
            }

            var collider = obj.GetComponent<Collider>();
            if (collider != null) Destroy(collider);
            obj.layer = 0;

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
            if (material != null && renderer != null)
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

            ApplyResolvedSettings(mode);
            Debug.Log($"[ViewModeManager] {mode} display created.");
        }

        private void ApplyResolvedSettings(ViewMode mode)
        {
            if (!_displayObjects.TryGetValue(mode, out var obj) || obj == null)
            {
                return;
            }

            _configLookup.TryGetValue(mode, out ViewModeConfig config);
            _runtimeOverrides.TryGetValue(mode, out VideoAdvancedSettings overrideSettings);

            ApplyTransformSettings(mode, obj, config, overrideSettings);
            ApplyMaterialSettings(mode, config, overrideSettings);
        }

        private void ApplyTransformSettings(ViewMode mode, GameObject obj, ViewModeConfig config, VideoAdvancedSettings overrideSettings)
        {
            Vector3 localPosition;
            Vector3 localRotation;
            Vector3 localScale;
            bool parentToCam;

            if (config != null)
            {
                localPosition = config.localPosition;
                localRotation = config.localRotation;
                localScale = config.localScale;
                parentToCam = config.parentToCamera;
            }
            else if (mode == ViewMode.Sphere360)
            {
                localPosition = Vector3.zero;
                localRotation = Vector3.zero;
                localScale = new Vector3(-100f, 100f, 100f);
                parentToCam = false;
            }
            else
            {
                localPosition = new Vector3(0f, 0f, 10f);
                localRotation = Vector3.zero;
                localScale = new Vector3(16f, 9f, 1f);
                parentToCam = true;
            }

            if (overrideSettings != null && overrideSettings.overrideTransformSettings && overrideSettings.transformSettings != null)
            {
                localPosition = overrideSettings.transformSettings.localPosition;
                localRotation = overrideSettings.transformSettings.localRotation;
                localScale = overrideSettings.transformSettings.localScale;
            }

            obj.transform.SetParent(parentToCam ? vrCamera : transform);
            obj.transform.localPosition = localPosition;
            obj.transform.localRotation = Quaternion.Euler(localRotation);
            obj.transform.localScale = localScale;
        }

        private void ApplyMaterialSettings(ViewMode mode, ViewModeConfig config, VideoAdvancedSettings overrideSettings)
        {
            if (!_materials.TryGetValue(mode, out var material) || material == null)
            {
                return;
            }

            Color tint = config != null ? config.tint : Color.white;
            float brightness = config != null ? config.brightness : 1f;
            Vector2 tiling = config != null ? config.textureTiling : Vector2.one;
            Vector2 offset = config != null ? config.textureOffset : Vector2.zero;

            if (overrideSettings != null && overrideSettings.overrideMaterialSettings && overrideSettings.materialSettings != null)
            {
                tint = overrideSettings.materialSettings.tint;
                brightness = overrideSettings.materialSettings.brightness;
                tiling = overrideSettings.materialSettings.textureTiling;
                offset = overrideSettings.materialSettings.textureOffset;
            }

            if (material.HasProperty("_Color"))
                material.SetColor("_Color", tint);

            if (material.HasProperty("_Brightness"))
                material.SetFloat("_Brightness", brightness);

            if (material.HasProperty("_Tilling"))
                material.SetVector("_Tilling", tiling);

            if (material.HasProperty("_Offset"))
                material.SetVector("_Offset", offset);

            if (material.HasProperty("_BaseMap"))
            {
                material.SetTextureScale("_BaseMap", tiling);
                material.SetTextureOffset("_BaseMap", offset);
            }
        }
    }
}
