using System.Collections.Generic;
using UnityEngine;

namespace VRClassroom
{
    /// <summary>
    /// Procedural hemisphere for VR180 content. Unity has no half-sphere primitive.
    ///
    /// Geometry: longitude -hFov/2..+hFov/2 around +Z (the viewer looks along +Z),
    /// latitude -vFov/2..+vFov/2. Radius 1 (scale the GameObject).
    /// UV: u = 0 at the viewer's left, 1 at the right; v = 0 at the bottom. These are
    /// *direct* texture coordinates, so the material has to render with _MirrorU = 0
    /// (see VideoSphere.shader). Meshes are cached per parameter set.
    /// </summary>
    public static class HemisphereMeshBuilder
    {
        private const string Tag = "[HemisphereMeshBuilder]";
        private static readonly Dictionary<string, Mesh> Cache = new Dictionary<string, Mesh>();

        public static Mesh Build(int segments = 64, float horizontalFovDeg = 180f, float verticalFovDeg = 180f)
        {
            segments = Mathf.Clamp(segments, 8, 256);
            horizontalFovDeg = Mathf.Clamp(horizontalFovDeg, 10f, 360f);
            verticalFovDeg = Mathf.Clamp(verticalFovDeg, 10f, 180f);

            string key = $"{segments}_{horizontalFovDeg:F1}_{verticalFovDeg:F1}";
            if (Cache.TryGetValue(key, out var cached) && cached != null)
                return cached;

            int lonSegments = segments;
            int latSegments = segments;
            int vertexCount = (lonSegments + 1) * (latSegments + 1);

            var vertices = new Vector3[vertexCount];
            var normals = new Vector3[vertexCount];
            var uvs = new Vector2[vertexCount];

            float lonStart = -horizontalFovDeg * 0.5f;
            float latStart = -verticalFovDeg * 0.5f;

            int index = 0;
            for (int y = 0; y <= latSegments; y++)
            {
                float v = (float)y / latSegments;
                float lat = (latStart + v * verticalFovDeg) * Mathf.Deg2Rad;
                float cosLat = Mathf.Cos(lat);
                float sinLat = Mathf.Sin(lat);

                for (int x = 0; x <= lonSegments; x++)
                {
                    float u = (float)x / lonSegments;
                    float lon = (lonStart + u * horizontalFovDeg) * Mathf.Deg2Rad;

                    var position = new Vector3(cosLat * Mathf.Sin(lon), sinLat, cosLat * Mathf.Cos(lon));
                    vertices[index] = position;
                    normals[index] = -position; // inside-facing
                    uvs[index] = new Vector2(u, v);
                    index++;
                }
            }

            var triangles = new int[lonSegments * latSegments * 6];
            int t = 0;
            for (int y = 0; y < latSegments; y++)
            {
                for (int x = 0; x < lonSegments; x++)
                {
                    int i0 = y * (lonSegments + 1) + x;
                    int i1 = i0 + 1;
                    int i2 = i0 + (lonSegments + 1);
                    int i3 = i2 + 1;

                    // Counter-clockwise when seen from the inside, i.e. the same convention as
                    // Unity's sphere primitive (outside = front). Rendered with Cull Front/Off.
                    triangles[t++] = i0;
                    triangles[t++] = i1;
                    triangles[t++] = i2;

                    triangles[t++] = i1;
                    triangles[t++] = i3;
                    triangles[t++] = i2;
                }
            }

            var mesh = new Mesh { name = $"Hemisphere_{key}" };
            if (vertexCount > 65535)
                mesh.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = uvs;
            mesh.triangles = triangles;
            mesh.RecalculateBounds();

            Cache[key] = mesh;
            Debug.Log($"{Tag} Built hemisphere mesh {key}: {vertexCount} vertices, {triangles.Length / 3} triangles.");
            return mesh;
        }
    }
}
