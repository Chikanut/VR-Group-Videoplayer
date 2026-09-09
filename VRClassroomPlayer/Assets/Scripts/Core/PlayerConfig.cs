namespace VRClassroom
{
    public static class PlayerConfig
    {
        /// <summary>
        /// Path to video files on Quest internal storage (Android forward slashes).
        /// </summary>
        public const string VideoPath = "/sdcard/Movies/";

        /// <summary>
        /// Port for the built-in HTTP server.
        /// </summary>
        public const int HttpPort = 8080;

        /// <summary>
        /// Interval in seconds between periodic status reports.
        /// </summary>
        public const float StatusInterval = 2f;

        /// <summary>
        /// Forces immediate status/registration sync when app regains focus.
        /// </summary>
        public const bool FastResyncOnFocus = true;

        /// <summary>
        /// Default view mode when none is specified.
        /// </summary>
        public const ViewMode DefaultViewMode = ViewMode.None;

        /// <summary>
        /// RenderTexture resolution for video output.
        /// </summary>
        public const int RenderTextureSize = 2048;

        /// <summary>
        /// Largest RenderTexture side for the Unity VideoPlayer backend. 4096 keeps 8K
        /// stereo sources at 2048x4096 per eye; raising it to 8192 needs the Phase 0 device
        /// verification (memory bandwidth). Can be overridden at runtime through
        /// PUT /render-settings (see <see cref="PlayerRenderSettings"/>).
        /// </summary>
        public const int MaxRenderTextureDimension = 4096;

        /// <summary>
        /// Longitude/latitude segments of the procedural VR180 hemisphere. Below 64 straight
        /// lines (walls, door frames) show visible facets.
        /// </summary>
        public const int HemisphereMeshSegments = 64;

        /// <summary>
        /// Radius (world units) of the VR180 hemisphere; matches the 100-unit sphere.
        /// </summary>
        public const float HemisphereRadius = 100f;

        /// <summary>
        /// Rendering backend name reported in /status. "native" is reserved for the
        /// OVROverlay + Android MediaPlayer backend (Phase 3).
        /// </summary>
        public const string VideoBackendName = "unity";
    }
}
