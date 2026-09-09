namespace VRClassroom
{
    /// <summary>
    /// Geometry the video is mapped onto. Orthogonal to <see cref="StereoLayout"/>.
    /// Replaces the flat <see cref="ViewMode"/> enum internally; ViewMode stays as a legacy alias.
    /// </summary>
    public enum VideoProjection
    {
        /// <summary>Flat quad in front of the viewer (classic 2D video).</summary>
        Flat,

        /// <summary>Hemisphere 180°x180°, equirectangular per eye (VR180).</summary>
        Hemisphere180,

        /// <summary>Full sphere 360°x180°, equirectangular per eye.</summary>
        Sphere360,

        /// <summary>Nothing playing: logo / idle screen.</summary>
        None
    }
}
