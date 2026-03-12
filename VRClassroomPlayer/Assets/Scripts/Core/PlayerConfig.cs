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
    }
}
