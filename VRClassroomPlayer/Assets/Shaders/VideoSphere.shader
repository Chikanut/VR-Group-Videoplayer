// Inside-sphere / hemisphere video shader with stereo 3D support.
//
// UV pipeline (fragment):
//   mesh uv -> optional mirror U (Unity sphere primitive needs it when seen from inside)
//           -> tiling/offset -> _MainTex_ST -> vertical crop remap
//           -> per-eye split (SBS: left eye = left half, TB: left eye = top half)
// The split is the LAST step and happens in texture space, so it is independent of how
// the geometry is mirrored. _SwapEyes exchanges the halves for material exported with
// the eyes reversed.
Shader "VRClassroom/VideoSphere"
{
    Properties
    {
        _MainTex ("Video Texture", 2D) = "black" {}
        _Color ("Tint", Color) = (1, 1, 1, 1)
        _Brightness ("Brightness", Range(0, 2)) = 1.0
        _Tilling ("Tiling", Vector) = (1, 1, 0, 0)
        _Offset ("Offset", Vector) = (0, 0, 0, 0)
        _TopCrop ("Top Crop", Range(0, 0.49)) = 0.0
        _BottomCrop ("Bottom Crop", Range(0, 0.49)) = 0.0
        [Toggle] _MirrorU ("Mirror U (inside of Unity sphere)", Int) = 1
        [Enum(Mono,0,SideBySide,1,TopBottom,2)] _StereoLayout ("Stereo Layout", Int) = 0
        [Toggle] _SwapEyes ("Swap Eyes", Int) = 0
        [Enum(UnityEngine.Rendering.CullMode)] _Cull ("Cull", Int) = 1
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Opaque"
            "Queue" = "Geometry"
        }

        // Default: cull front faces so we see the inside of the sphere (1 = Front)
        Cull [_Cull]
        ZWrite Off
        Lighting Off

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog

            #include "UnityCG.cginc"

            struct appdata
            {
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;

                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct v2f
            {
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;

                UNITY_VERTEX_OUTPUT_STEREO
            };

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _Color;
            half _Brightness;
            float4 _Tilling;
            float4 _Offset;
            float _TopCrop;
            float _BottomCrop;
            int _MirrorU;
            int _StereoLayout;
            int _SwapEyes;

            v2f vert(appdata v)
            {
                v2f o;

                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_OUTPUT(v2f, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);

                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = v.uv;
                return o;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);

                float2 uv = i.uv;

                // Mirror U so the video isn't flipped inside the sphere (Unity primitive).
                if (_MirrorU != 0)
                    uv.x = 1.0 - uv.x;

                uv = uv * _Tilling.xy + _Offset.xy;
                uv = TRANSFORM_TEX(uv, _MainTex);

                // Crop: stretch the band [_BottomCrop, 1 - _TopCrop] over the full height.
                uv.y = _BottomCrop + uv.y * (1.0 - _TopCrop - _BottomCrop);

                // Per-eye split, always the last step, in texture space.
                int eye = unity_StereoEyeIndex;
                if (_SwapEyes != 0)
                    eye = 1 - eye;

                if (_StereoLayout == 1)
                {
                    // Side-by-side: left eye samples the left half.
                    uv.x = saturate(uv.x) * 0.5 + eye * 0.5;
                }
                else if (_StereoLayout == 2)
                {
                    // Top-bottom: left eye samples the top half (v = 1 is the top of the texture).
                    uv.y = saturate(uv.y) * 0.5 + (1 - eye) * 0.5;
                }

                fixed4 col = tex2D(_MainTex, uv) * _Color;
                col.rgb *= _Brightness;
                return col;
            }
            ENDCG
        }
    }

    Fallback "Unlit/Texture"
}
