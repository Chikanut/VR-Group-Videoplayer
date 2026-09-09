using System;
using System.Collections.Generic;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// Owns the display geometry (flat quad, 360 sphere, 180 hemisphere, idle logo) and the
    /// materials on it. Switches geometry by <see cref="VideoProjection"/> and drives the stereo
    /// shader properties by <see cref="StereoLayout"/>.
    ///
    /// The legacy <see cref="ViewMode"/> API (SetMode/CurrentMode/OnModeChanged) is kept for
    /// existing callers and maps to mono formats.
    /// </summary>
    public class ViewModeManager : MonoBehaviour
    {
        /// <summary>Legacy event: projection changed (as ViewMode).</summary>
        public event Action<ViewMode> OnModeChanged;

        /// <summary>Full format changed (projection, stereo, swapEyes or forwardYaw).</summary>
        public event Action<VideoFormat> OnFormatChanged;

        public VideoFormat CurrentFormat { get; private set; } = VideoFormat.None;
        public ViewMode CurrentMode => CurrentFormat.ToViewMode();

        [SerializeField] private Transform vrCamera;
        [SerializeField] GameObject logoObject;
        [SerializeField] private Shader videoShaderOverride;

        [Header("View Mode Configs (optional — override material, mesh, transform per mode)")]
        [SerializeField] private ViewModeConfig[] viewModeConfigs;

        [Header("VR180 hemisphere")]
        [SerializeField] private int hemisphereSegments = PlayerConfig.HemisphereMeshSegments;
        [SerializeField] private float hemisphereRadius = PlayerConfig.HemisphereRadius;
        [Tooltip("Draw a black sphere behind the viewer so the area outside the 180° content is black instead of the skybox.")]
        [SerializeField] private bool blackBackdropBehindHemisphere = true;

        private static readonly int StereoLayoutId = Shader.PropertyToID("_StereoLayout");
        private static readonly int SwapEyesId = Shader.PropertyToID("_SwapEyes");

        private readonly Dictionary<VideoProjection, GameObject> _displayObjects = new Dictionary<VideoProjection, GameObject>();
        private readonly Dictionary<VideoProjection, Material> _materials = new Dictionary<VideoProjection, Material>();
        private readonly Dictionary<VideoProjection, Material> _stereoFallbackMaterials = new Dictionary<VideoProjection, Material>();
        private readonly Dictionary<VideoProjection, ViewModeConfig> _configLookup = new Dictionary<VideoProjection, ViewModeConfig>();
        private readonly Dictionary<VideoProjection, VideoAdvancedSettings> _runtimeOverrides = new Dictionary<VideoProjection, VideoAdvancedSettings>();
        private readonly Dictionary<VideoProjection, string> _placementOverrides = new Dictionary<VideoProjection, string>();

        private RenderTexture _currentTexture;
        private Material _backdropMaterial;

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
                    _configLookup[cfg.Projection] = cfg;
                    Debug.Log($"[ViewModeManager] Config loaded for mode: {cfg.viewMode} ({cfg.Projection})");
                }
            }

            Debug.Log("[ViewModeManager] Creating display geometry...");
            CreateDisplay(VideoProjection.Sphere360);
            CreateDisplay(VideoProjection.Hemisphere180);
            CreateDisplay(VideoProjection.Flat);
            CreateDisplay(VideoProjection.None);

            Debug.Log($"[ViewModeManager] Setting default mode: {PlayerConfig.DefaultViewMode}");
            SetFormat(VideoFormat.FromViewMode(PlayerConfig.DefaultViewMode));
        }

        private void OnDestroy()
        {
            foreach (var kvp in _materials)
            {
                if (kvp.Value != null)
                    Destroy(kvp.Value);
            }
            _materials.Clear();

            foreach (var kvp in _stereoFallbackMaterials)
            {
                if (kvp.Value != null)
                    Destroy(kvp.Value);
            }
            _stereoFallbackMaterials.Clear();

            if (_backdropMaterial != null)
                Destroy(_backdropMaterial);
        }

        // ─── Public API ─────────────────────────────────────────────────────────

        /// <summary>Legacy entry point: switch geometry, mono stereo.</summary>
        public void SetMode(ViewMode mode)
        {
            SetFormat(VideoFormat.FromViewMode(mode));
        }

        public void SetFormat(VideoFormat format)
        {
            if (format == null)
                format = VideoFormat.None;

            bool anyActive = false;
            foreach (var kvp in _displayObjects)
            {
                if (kvp.Value != null && kvp.Value.activeSelf)
                {
                    anyActive = true;
                    break;
                }
            }

            bool geometryChanged = format.projection != CurrentFormat.projection;
            bool stereoChanged = format.stereo != CurrentFormat.stereo || format.swapEyes != CurrentFormat.swapEyes;

            if (anyActive && !geometryChanged && !stereoChanged && format.Equals(CurrentFormat))
            {
                Debug.Log($"[ViewModeManager] Already in format {format}, skipping.");
                return;
            }

            Debug.Log($"[ViewModeManager] Switching format: {CurrentFormat} -> {format}");
            CurrentFormat = format.Clone();

            foreach (var kvp in _displayObjects)
            {
                if (kvp.Value != null)
                    kvp.Value.SetActive(kvp.Key == format.projection);
            }

            ApplyStereo(format.projection);

            string activeStates = "";
            foreach (var kvp in _displayObjects)
                activeStates += $" {kvp.Key}={kvp.Value?.activeSelf}";
            Debug.Log($"[ViewModeManager] Display states:{activeStates}");

            OnModeChanged?.Invoke(CurrentMode);
            OnFormatChanged?.Invoke(CurrentFormat);
        }

        public void SetRenderTexture(RenderTexture rt)
        {
            Debug.Log($"[ViewModeManager] SetRenderTexture called: {(rt != null ? $"{rt.width}x{rt.height}" : "null")}");
            _currentTexture = rt;

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

            foreach (var kvp in _stereoFallbackMaterials)
            {
                if (kvp.Value != null)
                    kvp.Value.mainTexture = rt;
            }
        }

        public void ApplyAdvancedSettingsOverride(ViewMode mode, VideoAdvancedSettings advancedSettings)
        {
            ApplyAdvancedSettingsOverride(VideoFormat.ProjectionOf(mode), advancedSettings);
        }

        public void ApplyAdvancedSettingsOverride(VideoProjection projection, VideoAdvancedSettings advancedSettings)
        {
            if (advancedSettings != null)
            {
                _runtimeOverrides[projection] = advancedSettings;
            }
            else
            {
                _runtimeOverrides.Remove(projection);
            }

            ApplyResolvedSettings(projection);
        }

        public void ApplyPlacementOverride(ViewMode mode, string placementMode)
        {
            ApplyPlacementOverride(VideoFormat.ProjectionOf(mode), placementMode);
        }

        public void ApplyPlacementOverride(VideoProjection projection, string placementMode)
        {
            if (string.IsNullOrWhiteSpace(placementMode) || placementMode.Equals("default", StringComparison.OrdinalIgnoreCase))
            {
                _placementOverrides.Remove(projection);
            }
            else
            {
                _placementOverrides[projection] = placementMode;
            }

            ApplyResolvedSettings(projection);
        }

        /// <summary>True when the material currently shown for `projection` can split eyes.</summary>
        public bool SupportsStereo(VideoProjection projection)
        {
            var material = GetActiveMaterial(projection);
            return material != null && material.HasProperty(StereoLayoutId);
        }

        // ─── Geometry creation ──────────────────────────────────────────────────

        private void CreateDisplay(VideoProjection projection)
        {
            _configLookup.TryGetValue(projection, out ViewModeConfig config);

            GameObject obj;
            if (config != null && config.meshOverride != null)
            {
                obj = new GameObject($"Video_{projection}");
                var mf = obj.AddComponent<MeshFilter>();
                mf.mesh = config.meshOverride;
                obj.AddComponent<MeshRenderer>();
                Debug.Log($"[ViewModeManager] Using mesh override for {projection}: {config.meshOverride.name}");
            }
            else if (projection == VideoProjection.None)
            {
                obj = logoObject;
                Debug.Log($"[ViewModeManager] Using logo object for {projection} mode.");
            }
            else if (projection == VideoProjection.Hemisphere180)
            {
                obj = new GameObject("VideoHemisphere180");
                var mf = obj.AddComponent<MeshFilter>();
                mf.sharedMesh = HemisphereMeshBuilder.Build(hemisphereSegments, 180f, 180f);
                obj.AddComponent<MeshRenderer>();
            }
            else
            {
                var primitiveType = projection == VideoProjection.Sphere360
                    ? PrimitiveType.Sphere
                    : PrimitiveType.Quad;
                obj = GameObject.CreatePrimitive(primitiveType);
                obj.name = projection == VideoProjection.Sphere360 ? "VideoSphere360" : "VideoQuad2D";
            }

            if (obj == null)
            {
                Debug.LogWarning($"[ViewModeManager] No display object for {projection} (logo object not assigned?).");
                _displayObjects[projection] = null;
                _materials[projection] = null;
                return;
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
                switch (projection)
                {
                    case VideoProjection.Sphere360:
                        material = VideoRenderShaderFactory.CreateSphereMaterial(videoShaderOverride);
                        break;
                    case VideoProjection.Hemisphere180:
                        material = VideoRenderShaderFactory.CreateHemisphereMaterial(videoShaderOverride);
                        break;
                    case VideoProjection.None:
                        material = null; // logo keeps its own material
                        break;
                    default:
                        material = VideoRenderShaderFactory.CreateFlatMaterial(videoShaderOverride);
                        break;
                }
            }

            var renderer = obj.GetComponent<Renderer>();
            if (material != null && renderer != null)
            {
                renderer.sharedMaterial = material;
            }
            else if (projection != VideoProjection.None)
            {
                Debug.LogError($"[ViewModeManager] No compatible shader found for {projection}. Assign shader in config or inspector.");
            }

            if (projection == VideoProjection.Hemisphere180 && blackBackdropBehindHemisphere)
            {
                CreateHemisphereBackdrop(obj);
            }

            obj.SetActive(false);

            _displayObjects[projection] = obj;
            _materials[projection] = material;

            ApplyResolvedSettings(projection);
            Debug.Log($"[ViewModeManager] {projection} display created (stereoCapable={material != null && material.HasProperty(StereoLayoutId)}).");
        }

        private void CreateHemisphereBackdrop(GameObject hemisphere)
        {
            var backdrop = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            backdrop.name = "HemisphereBackdrop";
            var collider = backdrop.GetComponent<Collider>();
            if (collider != null) Destroy(collider);

            backdrop.transform.SetParent(hemisphere.transform, false);
            backdrop.transform.localPosition = Vector3.zero;
            backdrop.transform.localRotation = Quaternion.identity;
            // Sphere primitive has diameter 1: scale 3 -> radius 1.5x the hemisphere radius.
            backdrop.transform.localScale = Vector3.one * 3f;

            _backdropMaterial = VideoRenderShaderFactory.CreateBlackInsideMaterial(videoShaderOverride);
            var renderer = backdrop.GetComponent<Renderer>();
            if (_backdropMaterial != null && renderer != null)
            {
                renderer.sharedMaterial = _backdropMaterial;
            }
            else
            {
                Debug.LogWarning("[ViewModeManager] Could not create backdrop material; area behind 180° content will show the skybox.");
            }
        }

        // ─── Stereo ─────────────────────────────────────────────────────────────

        private Material GetActiveMaterial(VideoProjection projection)
        {
            if (!_displayObjects.TryGetValue(projection, out var obj) || obj == null)
                return null;
            var renderer = obj.GetComponent<Renderer>();
            return renderer != null ? renderer.sharedMaterial : null;
        }

        /// <summary>
        /// Push the stereo layout to the material shown for `projection`. If that material cannot
        /// split eyes (no _StereoLayout property, e.g. a Shader Graph material) and stereo is
        /// requested, swap in a stereo-capable fallback; swap back for mono content.
        /// </summary>
        private void ApplyStereo(VideoProjection projection)
        {
            if (projection == VideoProjection.None) return;
            if (!_displayObjects.TryGetValue(projection, out var obj) || obj == null) return;
            var renderer = obj.GetComponent<Renderer>();
            if (renderer == null) return;

            _materials.TryGetValue(projection, out var baseMaterial);
            Material target = baseMaterial;
            bool wantStereo = CurrentFormat.IsStereo;

            if (wantStereo && (baseMaterial == null || !baseMaterial.HasProperty(StereoLayoutId)))
            {
                target = GetOrCreateStereoFallback(projection);
                if (target == null)
                {
                    Debug.LogWarning($"[ViewModeManager] {projection}: no stereo-capable material available; showing {CurrentFormat.stereo} content as mono.");
                    target = baseMaterial;
                }
                else
                {
                    Debug.LogWarning($"[ViewModeManager] {projection}: base material '{baseMaterial?.name}' has no _StereoLayout; using fallback '{target.name}'. Verify eye order / mirroring on device.");
                }
            }

            if (target != null && renderer.sharedMaterial != target)
            {
                renderer.sharedMaterial = target;
                ApplyMaterialSettings(projection);
            }

            if (target == null) return;

            if (target.HasProperty(StereoLayoutId))
                target.SetInt(StereoLayoutId, (int)CurrentFormat.stereo);
            if (target.HasProperty(SwapEyesId))
                target.SetInt(SwapEyesId, CurrentFormat.swapEyes ? 1 : 0);

            if (_currentTexture != null && target.mainTexture != _currentTexture)
                target.mainTexture = _currentTexture;

            Debug.Log($"[ViewModeManager] {projection}: stereo={CurrentFormat.stereo} swapEyes={CurrentFormat.swapEyes} material='{target.name}'");
        }

        private Material GetOrCreateStereoFallback(VideoProjection projection)
        {
            if (_stereoFallbackMaterials.TryGetValue(projection, out var existing) && existing != null)
                return existing;

            _configLookup.TryGetValue(projection, out var config);
            var material = VideoRenderShaderFactory.CreateStereoCapableMaterial(projection, config, videoShaderOverride);
            if (material == null) return null;

            if (_currentTexture != null)
                material.mainTexture = _currentTexture;

            _stereoFallbackMaterials[projection] = material;
            return material;
        }

        // ─── Settings ───────────────────────────────────────────────────────────

        private void ApplyResolvedSettings(VideoProjection projection)
        {
            if (!_displayObjects.TryGetValue(projection, out var obj) || obj == null)
            {
                return;
            }

            _configLookup.TryGetValue(projection, out ViewModeConfig config);
            _runtimeOverrides.TryGetValue(projection, out VideoAdvancedSettings overrideSettings);

            ApplyTransformSettings(projection, obj, config, overrideSettings);
            ApplyMaterialSettings(projection);
        }

        private void ApplyTransformSettings(VideoProjection projection, GameObject obj, ViewModeConfig config, VideoAdvancedSettings overrideSettings)
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
            else if (projection == VideoProjection.Sphere360)
            {
                localPosition = Vector3.zero;
                localRotation = Vector3.zero;
                localScale = new Vector3(-100f, 100f, 100f);
                parentToCam = false;
            }
            else if (projection == VideoProjection.Hemisphere180)
            {
                localPosition = Vector3.zero;
                localRotation = Vector3.zero;
                localScale = Vector3.one * hemisphereRadius;
                parentToCam = false;
            }
            else
            {
                localPosition = new Vector3(0f, 0f, 10f);
                localRotation = Vector3.zero;
                localScale = new Vector3(16f, 9f, 1f);
                parentToCam = projection == VideoProjection.Flat;
            }

            if (overrideSettings != null && overrideSettings.overrideTransformSettings && overrideSettings.transformSettings != null)
            {
                localPosition = overrideSettings.transformSettings.localPosition;
                localRotation = overrideSettings.transformSettings.localRotation;
                localScale = overrideSettings.transformSettings.localScale;
            }

            if (_placementOverrides.TryGetValue(projection, out string placementMode))
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

        private void ApplyMaterialSettings(VideoProjection projection)
        {
            var material = GetActiveMaterial(projection);
            if (material == null)
            {
                return;
            }

            _configLookup.TryGetValue(projection, out ViewModeConfig config);
            _runtimeOverrides.TryGetValue(projection, out VideoAdvancedSettings overrideSettings);

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
