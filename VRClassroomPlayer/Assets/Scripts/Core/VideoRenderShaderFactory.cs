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
                ApplyConfigProperties(mat, config);
                return mat;
            }

            // Resolve shader: config override > custom VRClassroom shader > built-in fallback
            bool isSphere = config.Projection == VideoProjection.Sphere360 || config.Projection == VideoProjection.Hemisphere180;
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
            if (config.Projection == VideoProjection.Hemisphere180)
                ConfigureForHemisphere(material);
            ApplyConfigProperties(material, config);

            Debug.Log($"[VideoRenderShaderFactory] Created material for {config.viewMode} with shader '{shader.name}'");
            return material;
        }

        /// <summary>
        /// Material for the procedural VR180 hemisphere: same inside-sphere shader, but the mesh
        /// carries direct UVs so U is not mirrored, and culling is off (the outside is never seen).
        /// </summary>
        public static Material CreateHemisphereMaterial(Shader overrideShader = null)
        {
            var shader = ResolveShader(overrideShader, SphereShaderCandidates);
            if (shader == null) return null;

            var material = new Material(shader)
            {
                name = "VideoHemisphere180Material"
            };

            ConfigureForVideo(material, cullFrontFaces: true);
            ConfigureForHemisphere(material);
            return material;
        }

        /// <summary>
        /// Opaque black material seen from inside a sphere; drawn before the video geometry so
        /// the video always wins where both overlap (ZWrite is off on video materials).
        /// </summary>
        public static Material CreateBlackInsideMaterial(Shader overrideShader = null)
        {
            var shader = ResolveShader(overrideShader, SphereShaderCandidates);
            if (shader == null) return null;

            var material = new Material(shader)
            {
                name = "VideoBackdropBlack"
            };

            ConfigureForVideo(material, cullFrontFaces: true);
            if (material.HasProperty("_Color"))
                material.SetColor("_Color", Color.black);
            if (material.HasProperty("_Brightness"))
                material.SetFloat("_Brightness", 0f);
            material.mainTexture = Texture2D.blackTexture;
            material.renderQueue = 1990; // before Geometry (2000)
            return material;
        }

        /// <summary>
        /// Stereo-capable replacement for a material that has no _StereoLayout property
        /// (e.g. a Shader Graph material assigned through ViewModeConfig). Uses
        /// config.stereoMaterialOverride when set, otherwise the VRClassroom shaders.
        /// </summary>
        public static Material CreateStereoCapableMaterial(VideoProjection projection, ViewModeConfig config, Shader overrideShader = null)
        {
            Material material;
            if (config != null && config.stereoMaterialOverride != null)
            {
                material = new Material(config.stereoMaterialOverride)
                {
                    name = config.stereoMaterialOverride.name + " (Stereo Clone)"
                };
            }
            else
            {
                switch (projection)
                {
                    case VideoProjection.Sphere360:
                        material = CreateSphereMaterial(overrideShader);
                        break;
                    case VideoProjection.Hemisphere180:
                        material = CreateHemisphereMaterial(overrideShader);
                        break;
                    case VideoProjection.Flat:
                        material = CreateFlatMaterial(overrideShader);
                        break;
                    default:
                        return null;
                }

                if (material != null && projection == VideoProjection.Sphere360 && config != null && material.HasProperty("_MirrorU"))
                    material.SetInt("_MirrorU", config.fallbackMirrorU ? 1 : 0);
            }

            if (material == null) return null;

            if (!material.HasProperty("_StereoLayout"))
            {
                Debug.LogWarning($"[VideoRenderShaderFactory] Stereo material '{material.name}' for {projection} has no _StereoLayout property. Is VRClassroom/VideoSphere included in the build?");
            }

            if (config != null)
                ApplyConfigProperties(material, config);

            material.name += " [stereo]";
            Debug.Log($"[VideoRenderShaderFactory] Created stereo-capable material '{material.name}' for {projection} with shader '{material.shader.name}'");
            return material;
        }

        private static void ConfigureForHemisphere(Material material)
        {
            if (material == null) return;
            if (material.HasProperty("_MirrorU"))
                material.SetInt("_MirrorU", 0);
            if (material.HasProperty("_Cull"))
                material.SetInt("_Cull", 0); // Off: robust against winding, outside is never visible
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

            if (material.HasProperty("_Tilling"))
                material.SetVector("_Tilling", Vector2.one);

            if (material.HasProperty("_Offset"))
                material.SetVector("_Offset", Vector2.zero);

            if (material.HasProperty("_Color"))
                material.SetColor("_Color", Color.white);

            if (material.HasProperty("_Brightness"))
                material.SetFloat("_Brightness", 1f);

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

            if (material.HasProperty("_Tilling"))
                material.SetVector("_Tilling", config.textureTiling);

            if (material.HasProperty("_Offset"))
                material.SetVector("_Offset", config.textureOffset);

            if (material.HasProperty("_BaseMap"))
            {
                material.SetTextureScale("_BaseMap", config.textureTiling);
                material.SetTextureOffset("_BaseMap", config.textureOffset);
            }
        }
    }
}
