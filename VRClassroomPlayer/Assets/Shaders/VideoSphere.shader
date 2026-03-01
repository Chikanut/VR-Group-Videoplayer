Shader "VRClassroom/VideoSphere"
{
    Properties
    {
        _MainTex ("Video Texture", 2D) = "black" {}
        _Color ("Tint", Color) = (1, 1, 1, 1)
        _Brightness ("Brightness", Range(0, 2)) = 1.0
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Opaque"
            "Queue" = "Geometry"
        }

        // Cull front faces so we see the inside of the sphere
        Cull Front
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

            v2f vert(appdata v)
            {
                v2f o;

                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_OUTPUT(v2f, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);

                o.pos = UnityObjectToClipPos(v.vertex);
                // Mirror U so the video isn't flipped inside the sphere
                o.uv = float2(1.0 - v.uv.x, v.uv.y);
                o.uv = TRANSFORM_TEX(o.uv, _MainTex);
                return o;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);

                fixed4 col = tex2D(_MainTex, i.uv) * _Color;
                col.rgb *= _Brightness;
                return col;
            }
            ENDCG
        }
    }

    Fallback "Unlit/Texture"
}
