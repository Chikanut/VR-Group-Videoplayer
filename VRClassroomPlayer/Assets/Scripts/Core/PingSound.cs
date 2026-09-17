using System;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// Shared "ping" beep. The clip is generated once and reused; the previous
    /// implementation created a new AudioClip (and sometimes a new AudioSource)
    /// on every ping, which leaked ~90 KB of audio memory per press.
    /// </summary>
    public static class PingSound
    {
        private const int SampleRate = 44100;
        private const float Duration = 0.5f;
        private const float Frequency = 880f;

        private static AudioClip _clip;

        public static void Play(GameObject host)
        {
            if (host == null) return;

            try
            {
                var clip = GetClip();
                var audioSource = host.GetComponent<AudioSource>();
                if (audioSource == null)
                {
                    audioSource = host.AddComponent<AudioSource>();
                    audioSource.playOnAwake = false;
                    audioSource.spatialBlend = 0f;
                }
                audioSource.PlayOneShot(clip);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[PingSound] Ping sound failed: {e.Message}");
            }
        }

        private static AudioClip GetClip()
        {
            if (_clip != null) return _clip;

            int sampleCount = Mathf.CeilToInt(SampleRate * Duration);
            var samples = new float[sampleCount];
            for (int i = 0; i < sampleCount; i++)
            {
                float t = (float)i / SampleRate;
                float envelope = 1f - (t / Duration);
                samples[i] = Mathf.Sin(2f * Mathf.PI * Frequency * t) * envelope * 0.8f;
            }

            _clip = AudioClip.Create("Ping", sampleCount, 1, SampleRate, false);
            _clip.SetData(samples, 0);
            return _clip;
        }
    }
}
