using System;

namespace VRClassroom
{
    /// <summary>
    /// Waiting-room look sent by the agent (server Settings → "Headset environment").
    /// custom=false is the built-in look: logo model + skybox.
    /// Position/rotation are metres/degrees from the viewer's start point (X right, Y up, Z forward).
    /// </summary>
    [Serializable]
    public class EnvironmentSettings
    {
        public bool custom;
        public string background = "#1a1a1a";
        public float[] logoPosition;
        public float logoSize = 4f;
        public float[] logoRotation;
    }
}
