using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// Configuration for a single view mode (e.g. Sphere360, Flat2D).
    /// Create instances via Assets > Create > VRClassroom > View Mode Config.
    /// Override material, mesh, transform, and texture settings per mode.
    /// </summary>
    [CreateAssetMenu(fileName = "NewViewModeConfig", menuName = "VRClassroom/View Mode Config")]
    public class ViewModeConfig : ScriptableObject
    {
        [Header("Identity")]
        [Tooltip("Which view mode this config applies to.")]
        public ViewMode viewMode = ViewMode.Sphere360;

        [Header("Mesh Override")]
        [Tooltip("Custom mesh to use instead of the default primitive. Leave null to use the built-in primitive (Sphere or Quad).")]
        public Mesh meshOverride;

        [Header("Material Override")]
        [Tooltip("Complete material override. If set, shader/color/brightness below are ignored.")]
        public Material materialOverride;

        [Tooltip("Shader override. If materialOverride is null, a material is created with this shader. Leave null to use VRClassroom/VideoSphere or VRClassroom/VideoFlat.")]
        public Shader shaderOverride;

        [Header("Material Properties")]
        [Tooltip("Tint color applied to the video texture.")]
        public Color tint = Color.white;

        [Tooltip("Brightness multiplier for the video.")]
        [Range(0f, 2f)]
        public float brightness = 1f;

        [Tooltip("Texture tiling (scale).")]
        public Vector2 textureTiling = Vector2.one;

        [Tooltip("Texture offset.")]
        public Vector2 textureOffset = Vector2.zero;

        [Header("Transform")]
        [Tooltip("Local position of the display object.")]
        public Vector3 localPosition = Vector3.zero;

        [Tooltip("Local rotation (euler angles) of the display object.")]
        public Vector3 localRotation = Vector3.zero;

        [Tooltip("Local scale of the display object.")]
        public Vector3 localScale = Vector3.one;

        [Header("Parenting")]
        [Tooltip("If true, this display object follows the VR camera (parented to it). Typically true for Flat2D, false for Sphere360.")]
        public bool parentToCamera;
    }
}
