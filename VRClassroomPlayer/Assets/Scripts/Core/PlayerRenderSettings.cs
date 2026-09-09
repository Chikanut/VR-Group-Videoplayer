using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// Runtime-tunable render limits, persisted in PlayerPrefs so field tests can change
    /// them via PUT /render-settings without rebuilding the APK.
    /// </summary>
    public static class PlayerRenderSettings
    {
        private const string Tag = "[PlayerRenderSettings]";
        private const string MaxTextureDimensionKey = "render_max_texture_dimension";

        private static int _maxTextureDimension = -1;

        /// <summary>
        /// Largest RenderTexture side used for video. Defaults to
        /// <see cref="PlayerConfig.MaxRenderTextureDimension"/>; never above SystemInfo.maxTextureSize.
        /// </summary>
        public static int MaxTextureDimension
        {
            get
            {
                if (_maxTextureDimension < 0)
                {
                    _maxTextureDimension = PlayerPrefs.GetInt(MaxTextureDimensionKey, PlayerConfig.MaxRenderTextureDimension);
                }
                int hardwareMax = SystemInfo.maxTextureSize > 0 ? SystemInfo.maxTextureSize : PlayerConfig.MaxRenderTextureDimension;
                return Mathf.Clamp(_maxTextureDimension, 256, hardwareMax);
            }
            set
            {
                int clamped = Mathf.Clamp(value, 256, 16384);
                _maxTextureDimension = clamped;
                PlayerPrefs.SetInt(MaxTextureDimensionKey, clamped);
                PlayerPrefs.Save();
                Debug.Log($"{Tag} MaxTextureDimension set to {clamped} (hardware max {SystemInfo.maxTextureSize}).");
            }
        }

        public static void Reset()
        {
            PlayerPrefs.DeleteKey(MaxTextureDimensionKey);
            PlayerPrefs.Save();
            _maxTextureDimension = -1;
            Debug.Log($"{Tag} Reset to defaults (MaxTextureDimension={PlayerConfig.MaxRenderTextureDimension}).");
        }

        public static string ToJson()
        {
            return "{\"maxTextureDimension\":" + MaxTextureDimension +
                   ",\"defaultMaxTextureDimension\":" + PlayerConfig.MaxRenderTextureDimension +
                   ",\"hardwareMaxTextureSize\":" + SystemInfo.maxTextureSize + "}";
        }
    }
}
