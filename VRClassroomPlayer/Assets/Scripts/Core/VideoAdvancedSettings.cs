using System;
using UnityEngine;

namespace VRClassroom
{
    [Serializable]
    public class VideoAdvancedSettings
    {
        public bool overrideTransformSettings;
        public bool overrideMaterialSettings;
        public VideoTransformSettings transformSettings = new VideoTransformSettings();
        public VideoMaterialSettings materialSettings = new VideoMaterialSettings();
    }

    [Serializable]
    public class VideoTransformSettings
    {
        public Vector3 localPosition = Vector3.zero;
        public Vector3 localRotation = Vector3.zero;
        public Vector3 localScale = Vector3.one;
    }

    [Serializable]
    public class VideoMaterialSettings
    {
        public Color tint = Color.white;
        public float brightness = 1f;
        public Vector2 textureTiling = Vector2.one;
        public Vector2 textureOffset = Vector2.zero;
    }
}
