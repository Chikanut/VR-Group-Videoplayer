using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// Builds video materials that are compatible with both built-in and URP shaders
    /// and configures them for flat 2D and inside-sphere 360 rendering.
    /// </summary>
    public static class VideoRenderShaderFactory
    {
        private static readonly string[] UnlitShaderCandidates =
        {
            "Unlit/Texture",
            "Universal Render Pipeline/Unlit",
            "Standard"
        };

        public static Material CreateFlatMaterial(Shader overrideShader = null)
        {
            var shader = ResolveShader(overrideShader);
            if (shader == null)
            {
                return null;
            }

            var material = new Material(shader)
            {
                name = "VideoFlatMaterial"
            };

            ConfigureForVideo(material, cullFrontFaces: false);
            return material;
        }

        public static Material CreateSphereMaterial(Shader overrideShader = null)
        {
            var shader = ResolveShader(overrideShader);
            if (shader == null)
            {
                return null;
            }

            var material = new Material(shader)
            {
                name = "VideoSphereMaterial"
            };

            // We render the sphere from the inside.
            ConfigureForVideo(material, cullFrontFaces: true);
            return material;
        }

        private static Shader ResolveShader(Shader overrideShader)
        {
            if (overrideShader != null)
            {
                return overrideShader;
            }

            for (int i = 0; i < UnlitShaderCandidates.Length; i++)
            {
                var shader = Shader.Find(UnlitShaderCandidates[i]);
                if (shader != null)
                {
                    return shader;
                }
            }

            return null;
        }

        private static void ConfigureForVideo(Material material, bool cullFrontFaces)
        {
            if (material == null)
            {
                return;
            }

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
            {
                material.SetInt("_Cull", cullFrontFaces ? 1 : 2);
            }

            if (material.HasProperty("_ZWrite"))
            {
                material.SetInt("_ZWrite", 0);
            }

            if (material.HasProperty("_Surface"))
            {
                // URP: force opaque for stable video output.
                material.SetFloat("_Surface", 0f);
            }

            if (material.HasProperty("_EmissionColor"))
            {
                material.SetColor("_EmissionColor", Color.white);
                material.EnableKeyword("_EMISSION");
            }
        }
    }
}
