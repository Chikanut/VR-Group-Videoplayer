namespace VRClassroom
{
    /// <summary>
    /// Legacy display mode. Kept for the old "mode" API field, ViewModeConfig assets and the
    /// PlayerStateManager/HUD, but internally everything runs on <see cref="VideoFormat"/>
    /// (projection + stereo). One-to-one with <see cref="VideoProjection"/>:
    /// Flat2D=Flat, Sphere360=Sphere360, Hemisphere180=Hemisphere180, None=None.
    /// Do not reorder: the integer values are serialized in .asset files.
    /// </summary>
    public enum ViewMode
    {
        Flat2D,
        Sphere360,
        None,
        Hemisphere180
    }
}
