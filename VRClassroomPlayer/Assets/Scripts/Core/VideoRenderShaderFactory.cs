using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// Builds video materials for flat 2D and inside-sphere 360 rendering.
    /// Prefers custom VRClassroom shaders, falls back to built-in shaders.
    /// Supports full override via ViewModeConfig.
    /// </summary>
    public static class VideoRenderShaderFactory
    {
        private static readonly string[] SphereShaderCandidates =
        {
            "VRClassroom/VideoSphere",
            "Unlit/Texture",
            "Universal Render Pipeline/Unlit",
            "Standard"
        };

        private static readonly string[] FlatShaderCandidates =
        {
            "VRClassroom/VideoFlat",
            "Unlit/Texture",
            "Universal Render Pipeline/Unlit",
            "Standard"
        };

        /// <summary>
        /// Create a material from a ViewModeConfig. Returns a fully configured material
        /// with tiling, offset, tint, and brightness applied.
        /// </summary>
        public static Material CreateFromConfig(ViewModeConfig config)
        {
            if (config == null)
            {
                Debug.LogError("[VideoRenderShaderFactory] CreateFromConfig called with null config.");
                return null;
            }

            // If a full material override is provided, clone it so we don't modify the asset
            if (config.materialOverride != null)
            {
                var mat = new Material(config.materialOverride)
                {
                    name = config.materialOverride.name + " (Clone)"
                };
                Debug.Log($"[VideoRenderShaderFactory] Using material override: {config.materialOverride.name} for {config.viewMode}");
                return mat;
            }

            // Resolve shader: config override > custom VRClassroom shader > built-in fallback
            bool isSphere = config.viewMode == ViewMode.Sphere360;
            Shader shader = config.shaderOverride != null
                ? config.shaderOverride
                : ResolveShader(null, isSphere ? SphereShaderCandidates : FlatShaderCandidates);

            if (shader == null)
            {
                Debug.LogError($"[VideoRenderShaderFactory] No shader found for {config.viewMode}.");
                return null;
            }

            var material = new Material(shader)
            {
                name = $"Video{config.viewMode}Material"
            };

            // Apply config properties
            ConfigureForVideo(material, isSphere);
            ApplyConfigProperties(material, config);

            Debug.Log($"[VideoRenderShaderFactory] Created material for {config.viewMode} with shader '{shader.name}'");
            return material;
        }

        public static Material CreateFlatMaterial(Shader overrideShader = null)
        {
            var shader = ResolveShader(overrideShader, FlatShaderCandidates);
            if (shader == null) return null;

            var material = new Material(shader)
            {
                name = "VideoFlatMaterial"
            };

            ConfigureForVideo(material, cullFrontFaces: false);
            return material;
        }

        public static Material CreateSphereMaterial(Shader overrideShader = null)
        {
            var shader = ResolveShader(overrideShader, SphereShaderCandidates);
            if (shader == null) return null;

            var material = new Material(shader)
            {
                name = "VideoSphereMaterial"
            };

            ConfigureForVideo(material, cullFrontFaces: true);
            return material;
        }

        private static Shader ResolveShader(Shader overrideShader, string[] candidates)
        {
            if (overrideShader != null)
                return overrideShader;

            for (int i = 0; i < candidates.Length; i++)
            {
                var shader = Shader.Find(candidates[i]);
                if (shader != null)
                    return shader;
            }

            return null;
        }

        private static void ConfigureForVideo(Material material, bool cullFrontFaces)
        {
            if (material == null) return;

            material.color = Color.white;

            if (material.HasProperty("_MainTex"))
            {
                material.SetTextureScale("_MainTex", Vector2.one);
                material.SetTextureOffset("_MainTex", Vector2.zero);
            }

            if (material.HasProperty("_BaseMap"))
            {
                material.SetTextureScale("_BaseMap", Vector2.one);
                material.SetTextureOffset("_BaseMap", Vector2.zero);
            }

            // Unity cull values: 0 Off, 1 Front, 2 Back.
            if (material.HasProperty("_Cull"))
                material.SetInt("_Cull", cullFrontFaces ? 1 : 2);

            if (material.HasProperty("_ZWrite"))
                material.SetInt("_ZWrite", 0);

            if (material.HasProperty("_Surface"))
                material.SetFloat("_Surface", 0f); // URP: force opaque

            if (material.HasProperty("_EmissionColor"))
            {
                material.SetColor("_EmissionColor", Color.white);
                material.EnableKeyword("_EMISSION");
            }
        }

        private static void ApplyConfigProperties(Material material, ViewModeConfig config)
        {
            if (material == null || config == null) return;

            if (material.HasProperty("_Color"))
                material.SetColor("_Color", config.tint);

            if (material.HasProperty("_Brightness"))
                material.SetFloat("_Brightness", config.brightness);

            if (material.HasProperty("_MainTex"))
            {
                material.SetTextureScale("_MainTex", config.textureTiling);
                material.SetTextureOffset("_MainTex", config.textureOffset);
            }

            if (material.HasProperty("_BaseMap"))
            {
                material.SetTextureScale("_BaseMap", config.textureTiling);
                material.SetTextureOffset("_BaseMap", config.textureOffset);
            }
        }
    }
}
