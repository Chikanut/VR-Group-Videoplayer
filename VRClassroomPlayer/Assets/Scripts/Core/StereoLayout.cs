namespace VRClassroom
{
    /// <summary>
    /// How the two eye images are packed into one video frame.
    /// Values are also the integer sent to the shader (_StereoLayout).
    /// </summary>
    public enum StereoLayout
    {
        /// <summary>Single image shown to both eyes.</summary>
        Mono = 0,

        /// <summary>Side-by-side: left eye is the left half of the frame (Quest "_LR").</summary>
        SideBySide = 1,

        /// <summary>Top-bottom / over-under: left eye is the top half of the frame (Quest "_TB").</summary>
        TopBottom = 2
    }
}
