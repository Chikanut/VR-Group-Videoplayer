using System;
using System.Collections.Generic;
using System.IO;
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
        private readonly Dictionary<ViewMode, string> _placementOverrides = new Dictionary<ViewMode, string>();

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
            DestroyCustomLogo();
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

        // ─── Waiting-room environment ──────────────────────────────────────────

        private bool _environmentDefaultsSaved;
        private Material _defaultSkybox;
        private CameraClearFlags _defaultClearFlags;
        private Color _defaultBackground;
        private readonly List<Renderer> _logoRenderers = new List<Renderer>();
        private readonly List<bool> _logoRendererStates = new List<bool>();
        private GameObject _customLogo;
        private Texture2D _customLogoTexture;
        private Vector3 _logoRootPosition;

        /// <summary>
        /// custom=false (or null): the built-in look. Otherwise a solid background colour and, when
        /// logoPath points to a PNG, that picture instead of the logo model. The picture lives under
        /// the logo object, so it shows and hides with the waiting room like the model did.
        /// </summary>
        public void ApplyEnvironment(EnvironmentSettings env, string logoPath)
        {
            Camera cam = vrCamera != null ? vrCamera.GetComponent<Camera>() : null;
            if (cam == null) cam = Camera.main;
            if (!_environmentDefaultsSaved)
            {
                _environmentDefaultsSaved = true;
                _defaultSkybox = RenderSettings.skybox;
                if (cam != null)
                {
                    _defaultClearFlags = cam.clearFlags;
                    _defaultBackground = cam.backgroundColor;
                }
                if (logoObject != null)
                {
                    _logoRootPosition = logoObject.transform.position;
                    foreach (var r in logoObject.GetComponentsInChildren<Renderer>(true))
                    {
                        _logoRenderers.Add(r);
                        _logoRendererStates.Add(r.enabled);
                    }
                }
            }

            DestroyCustomLogo();
            bool custom = env != null && env.custom;

            if (cam != null)
            {
                if (custom && ColorUtility.TryParseHtmlString(env.background, out Color background))
                {
                    cam.clearFlags = CameraClearFlags.SolidColor;
                    cam.backgroundColor = background;
                }
                else
                {
                    cam.clearFlags = _defaultClearFlags;
                    cam.backgroundColor = _defaultBackground;
                }
            }
            RenderSettings.skybox = custom ? null : _defaultSkybox;

            for (int i = 0; i < _logoRenderers.Count; i++)
            {
                if (_logoRenderers[i] != null) _logoRenderers[i].enabled = !custom && _logoRendererStates[i];
            }

            if (custom && !string.IsNullOrEmpty(logoPath) && File.Exists(logoPath) && logoObject != null)
            {
                CreateCustomLogo(env, logoPath);
            }
            Debug.Log($"[ViewModeManager] Environment applied: {(custom ? "custom" : "default")}, picture={(_customLogo != null)}");
        }

        private void CreateCustomLogo(EnvironmentSettings env, string logoPath)
        {
            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, true);
            if (!texture.LoadImage(File.ReadAllBytes(logoPath), true)) // non-readable: frees the CPU copy
            {
                Destroy(texture);
                Debug.LogError($"[ViewModeManager] Environment picture could not be loaded: {logoPath}");
                return;
            }
            texture.wrapMode = TextureWrapMode.Clamp;
            _customLogoTexture = texture;

            float size = env.logoSize > 0.01f ? env.logoSize : 4f;
            var sprite = Sprite.Create(texture, new Rect(0, 0, texture.width, texture.height),
                new Vector2(0.5f, 0.5f), texture.width / size);

            _customLogo = new GameObject("CustomLogo");
            _customLogo.transform.SetParent(logoObject.transform, false);
            var spriteRenderer = _customLogo.AddComponent<SpriteRenderer>();
            spriteRenderer.sprite = sprite;
            // Reuse the scene's own sprite material so the shader is surely in the build.
            foreach (var r in _logoRenderers)
            {
                if (r is SpriteRenderer existing && existing.sharedMaterial != null)
                {
                    spriteRenderer.sharedMaterial = existing.sharedMaterial;
                    break;
                }
            }

            Vector3 position = ToVector(env.logoPosition, _logoRootPosition);
            _customLogo.transform.localPosition = position - _logoRootPosition;
            _customLogo.transform.localEulerAngles = ToVector(env.logoRotation, Vector3.zero);
        }

        private void DestroyCustomLogo()
        {
            if (_customLogo != null)
            {
                var spriteRenderer = _customLogo.GetComponent<SpriteRenderer>();
                if (spriteRenderer != null && spriteRenderer.sprite != null) Destroy(spriteRenderer.sprite);
                Destroy(_customLogo);
                _customLogo = null;
            }
            if (_customLogoTexture != null)
            {
                Destroy(_customLogoTexture);
                _customLogoTexture = null;
            }
        }

        private static Vector3 ToVector(float[] values, Vector3 fallback)
        {
            return values != null && values.Length == 3 ? new Vector3(values[0], values[1], values[2]) : fallback;
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

        public void ApplyPlacementOverride(ViewMode mode, string placementMode)
        {
            if (string.IsNullOrWhiteSpace(placementMode) || placementMode.Equals("default", StringComparison.OrdinalIgnoreCase))
            {
                _placementOverrides.Remove(mode);
            }
            else
            {
                _placementOverrides[mode] = placementMode;
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

            if (_placementOverrides.TryGetValue(mode, out string placementMode))
            {
                if (placementMode.Equals("locked", StringComparison.OrdinalIgnoreCase))
                {
                    parentToCam = true;
                }
                else if (placementMode.Equals("free", StringComparison.OrdinalIgnoreCase))
                {
                    parentToCam = false;
                }
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
            float topCrop = 0f;
            float bottomCrop = 0f;

            if (overrideSettings != null && overrideSettings.overrideMaterialSettings && overrideSettings.materialSettings != null)
            {
                tint = overrideSettings.materialSettings.tint;
                brightness = overrideSettings.materialSettings.brightness;
                tiling = overrideSettings.materialSettings.textureTiling;
                offset = overrideSettings.materialSettings.textureOffset;
                topCrop = overrideSettings.materialSettings.topCrop;
                bottomCrop = overrideSettings.materialSettings.bottomCrop;
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

            if (material.HasProperty("_TopCrop"))
                material.SetFloat("_TopCrop", topCrop);

            if (material.HasProperty("_BottomCrop"))
                material.SetFloat("_BottomCrop", bottomCrop);
        }
    }
}
