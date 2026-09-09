"""Check a configured video against what a headset reported about itself.

Two independent sources are combined:

* the video's cached probe (``RequirementVideo.probe`` — resolution, codec, bit depth ...)
* the device's ``decoderCaps`` and ``stereoCapable`` from its ``/status``

Nothing here blocks playback; the result is a list of human-readable warnings that the
panel shows before or while opening the video, so the instructor is not surprised by a
black frame on headset #17 in front of the class.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .video_format import is_stereo, projection_of, PROJECTION_180


def _caps_int(caps: Dict[str, Any], key: str) -> int:
    try:
        return int(caps.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def check_video_on_device(video: Dict[str, Any], device: Any, format_id: Optional[str] = None) -> List[str]:
    """Return warnings for playing `video` (config dict) on `device` (DeviceState-like)."""
    warnings: List[str] = []
    format_id = format_id or video.get("videoType") or "360"
    probe = video.get("probe") if isinstance(video.get("probe"), dict) else {}

    stereo_capable = getattr(device, "stereo_capable", None)
    if stereo_capable is False:
        if is_stereo(format_id):
            warnings.append("Player on this headset predates stereo 3D support: the video will play as mono 360.")
        elif projection_of(format_id) == PROJECTION_180:
            warnings.append("Player on this headset predates 180° support: the video will be stretched over a full sphere.")

    caps = getattr(device, "decoder_caps", None) or {}
    if not isinstance(caps, dict) or not caps or not probe:
        return warnings

    width = int(probe.get("width") or 0)
    height = int(probe.get("height") or 0)
    codec = str(probe.get("codec") or "").lower()
    bit_depth = int(probe.get("bitDepth") or 0)
    fps = float(probe.get("fps") or 0.0)

    prefix = {"hevc": "hevc", "h264": "avc", "av1": "av1", "vp9": "vp9"}.get(codec, codec)
    max_width = _caps_int(caps, f"{prefix}MaxWidth")
    max_height = _caps_int(caps, f"{prefix}MaxHeight")
    if width and max_width and width > max_width:
        warnings.append(f"Video width {width} exceeds the {codec.upper()} decoder limit {max_width} on this headset.")
    if height and max_height and height > max_height:
        warnings.append(f"Video height {height} exceeds the {codec.upper()} decoder limit {max_height} on this headset.")

    if codec == "hevc" and bit_depth > 8 and caps.get("hevcMain10") is False:
        warnings.append("10-bit HEVC (Main10) is not supported by the decoder on this headset.")

    max_fps_8k = _caps_int(caps, "hevcMaxFrameRateAt8K")
    if codec == "hevc" and width >= 7680 and fps and max_fps_8k and fps > max_fps_8k + 0.5:
        warnings.append(f"{fps:g} fps at 8K exceeds the decoder's {max_fps_8k} fps limit on this headset.")

    free_bytes = _caps_int(caps, "storageFreeBytes")
    size_bytes = int(probe.get("sizeBytes") or 0)
    if free_bytes and size_bytes and size_bytes > free_bytes:
        warnings.append(f"File size {size_bytes / 1e9:.1f} GB exceeds free storage {free_bytes / 1e9:.1f} GB on this headset.")

    return warnings
