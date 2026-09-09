"""Header-only MP4 / MOV probe and video format auto-detection.

Pure Python, no ffprobe: the control panel runs on teachers' laptops where nothing but
Python is guaranteed. Only box headers and the ``moov`` atom are read, so probing a
multi-gigabyte file costs a handful of seeks even when ``moov`` sits at the end of the
file (as it does in the customer's DaVinci Resolve exports).

What is extracted:

* container brand, size, ``mdat`` size
* video track: fourcc, width/height, fps, duration, profile / tier / level, bit depth,
  chroma format, colour description (``colr``), pixel aspect (``pasp``)
* audio track: codec, channels, sample rate
* other tracks (``tmcd`` timecode ...)
* spherical metadata: Google Spherical v1 (``uuid`` + XML) and v2 (``st3d`` / ``sv3d``)

``detect_format()`` then applies the priority order from the spec (manual > filename >
aspect + metadata > metadata > default) and reports the source and warnings.
"""
from __future__ import annotations

import logging
import os
import re
import struct
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .video_format import (
    DEFAULT_FORMAT,
    FORMAT_AUTO,
    PROJECTION_180,
    PROJECTION_360,
    PROJECTION_FLAT,
    STEREO_MONO,
    STEREO_SBS,
    STEREO_TB,
    detect_format_from_filename,
    make_format_id,
    normalize_format_id,
    split_format_id,
)

logger = logging.getLogger("vrclassroom.video_probe")

SPHERICAL_V1_UUID = bytes.fromhex("ffcc8263f8554a938814587a02521fdd")

# Container boxes whose payload is a plain list of child boxes.
_CONTAINER_BOXES = {
    b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta", b"edts", b"sv3d", b"proj", b"dinf",
    b"mvex", b"tref", b"gmhd",
}
# Full boxes (4 bytes version/flags) that contain children after a fixed prefix.
_VISUAL_SAMPLE_ENTRIES = {b"hvc1", b"hev1", b"avc1", b"avc3", b"av01", b"vp09", b"mp4v", b"dvh1", b"dvhe"}
_AUDIO_SAMPLE_ENTRIES = {b"mp4a", b"ac-3", b"ec-3", b"opus", b"flac", b"alac", b"sowt", b"twos", b"lpcm"}

# Guard against corrupted headers: moov larger than this is not read into memory.
MAX_MOOV_BYTES = 64 * 1024 * 1024

_CODEC_NAMES = {
    b"hvc1": "hevc",
    b"hev1": "hevc",
    b"dvh1": "hevc",
    b"dvhe": "hevc",
    b"avc1": "h264",
    b"avc3": "h264",
    b"av01": "av1",
    b"vp09": "vp9",
    b"mp4v": "mpeg4",
}

_HEVC_PROFILES = {1: "Main", 2: "Main10", 3: "MainStillPicture", 4: "RExt"}
_H264_PROFILES = {66: "Baseline", 77: "Main", 88: "Extended", 100: "High", 110: "High10", 122: "High422", 244: "High444"}

_AUDIO_CODEC_NAMES = {
    b"mp4a": "aac",
    b"ac-3": "ac3",
    b"ec-3": "eac3",
    b"opus": "opus",
    b"flac": "flac",
    b"alac": "alac",
    b"sowt": "pcm",
    b"twos": "pcm",
    b"lpcm": "pcm",
}


class ProbeError(Exception):
    """The file could not be parsed as ISO BMFF."""


@dataclass
class VideoProbeResult:
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""
    bitDepth: int = 0
    chromaFormat: str = ""
    profile: str = ""
    tier: str = ""
    level: str = ""
    bitrateMbps: float = 0.0
    durationSec: float = 0.0
    sizeBytes: int = 0
    container: str = ""
    faststart: bool = False
    colorPrimaries: int = 0
    colorTransfer: int = 0
    colorMatrix: int = 0
    pixelAspect: str = ""
    audioCodec: str = ""
    audioChannels: int = 0
    audioSampleRate: int = 0
    trackTypes: List[str] = field(default_factory=list)
    metadataProjection: str = ""   # verbatim from uuid XML / sv3d, NOT trusted
    metadataStereo: str = ""       # "left-right" | "top-bottom" | "mono" | ""
    metadataSource: str = ""       # "spherical-v1" | "spherical-v2" | ""
    projectionBounds: Dict[str, float] = field(default_factory=dict)  # equi box, 0..1
    detectedType: str = ""
    detectionSource: str = ""
    # What auto-detection alone would give (filename/aspect/metadata), even when a manual
    # format was passed. Lets the UI offer "use detected format" for manual videos.
    autoDetectedType: str = ""
    autoDetectionSource: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------------------
# Low level box reading
# --------------------------------------------------------------------------------------

def _iter_boxes(data: bytes, start: int = 0, end: Optional[int] = None):
    """Yield (type, payload_start, payload_end) for consecutive boxes in `data`."""
    if end is None:
        end = len(data)
    offset = start
    while offset + 8 <= end:
        size, box_type = struct.unpack_from(">I4s", data, offset)
        header = 8
        if size == 1:
            if offset + 16 > end:
                return
            size = struct.unpack_from(">Q", data, offset + 8)[0]
            header = 16
        elif size == 0:
            size = end - offset
        if size < header:
            return
        payload_start = offset + header
        payload_end = min(offset + size, end)
        yield box_type, payload_start, payload_end
        offset += size


def _read_top_level(path: str) -> Tuple[Dict[str, Any], Optional[bytes]]:
    """Walk the top-level boxes of the file with seeks only. Returns (info, moov_bytes)."""
    info: Dict[str, Any] = {"brand": "", "mdat_size": 0, "moov_offset": -1, "mdat_offset": -1}
    moov: Optional[bytes] = None

    file_size = os.path.getsize(path)
    with open(path, "rb") as handle:
        offset = 0
        while offset + 8 <= file_size:
            handle.seek(offset)
            header = handle.read(16)
            if len(header) < 8:
                break
            size, box_type = struct.unpack_from(">I4s", header, 0)
            header_len = 8
            if size == 1:
                if len(header) < 16:
                    break
                size = struct.unpack_from(">Q", header, 8)[0]
                header_len = 16
            elif size == 0:
                size = file_size - offset
            if size < header_len:
                raise ProbeError(f"corrupted box header at offset {offset}")

            payload_size = size - header_len
            if box_type == b"ftyp":
                handle.seek(offset + header_len)
                payload = handle.read(min(payload_size, 64))
                if len(payload) >= 4:
                    info["brand"] = payload[:4].decode("latin-1").strip()
            elif box_type == b"mdat":
                info["mdat_size"] += payload_size
                if info["mdat_offset"] < 0:
                    info["mdat_offset"] = offset
            elif box_type == b"moov":
                if payload_size > MAX_MOOV_BYTES:
                    raise ProbeError(f"moov box too large ({payload_size} bytes)")
                handle.seek(offset + header_len)
                moov = handle.read(payload_size)
                info["moov_offset"] = offset

            offset += size

    return info, moov


def _fixed_16_16(value: int) -> float:
    return value / 65536.0


def _parse_mdhd(data: bytes, start: int, end: int) -> Tuple[int, int]:
    version = data[start]
    if version == 1:
        timescale = struct.unpack_from(">I", data, start + 20)[0]
        duration = struct.unpack_from(">Q", data, start + 24)[0]
    else:
        timescale = struct.unpack_from(">I", data, start + 12)[0]
        duration = struct.unpack_from(">I", data, start + 16)[0]
    return timescale, duration


def _parse_hdlr(data: bytes, start: int, end: int) -> str:
    # fullbox(4) + pre_defined(4) + handler_type(4)
    if end - start < 12:
        return ""
    return data[start + 8:start + 12].decode("latin-1")


def _parse_stts(data: bytes, start: int, end: int) -> Tuple[int, int]:
    """Return (sample_count, total_delta) so fps = timescale * count / total."""
    if end - start < 8:
        return 0, 0
    entry_count = struct.unpack_from(">I", data, start + 4)[0]
    count_total = 0
    delta_total = 0
    offset = start + 8
    for _ in range(entry_count):
        if offset + 8 > end:
            break
        count, delta = struct.unpack_from(">II", data, offset)
        count_total += count
        delta_total += count * delta
        offset += 8
    return count_total, delta_total


def _parse_stsz(data: bytes, start: int, end: int) -> int:
    """Sum of sample sizes for one track (exact track payload in bytes)."""
    if end - start < 12:
        return 0
    sample_size, sample_count = struct.unpack_from(">II", data, start + 4)
    if sample_size != 0:
        return sample_size * sample_count
    total = 0
    offset = start + 12
    for _ in range(sample_count):
        if offset + 4 > end:
            break
        total += struct.unpack_from(">I", data, offset)[0]
        offset += 4
    return total


def _parse_hvcc(payload: bytes, track: Dict[str, Any]):
    if len(payload) < 19:
        return
    byte1 = payload[1]
    tier = (byte1 >> 5) & 0x1
    profile_idc = byte1 & 0x1F
    level_idc = payload[12]
    chroma_format = payload[16] & 0x3
    bit_depth_luma = (payload[17] & 0x7) + 8
    track["profile"] = _HEVC_PROFILES.get(profile_idc, f"profile{profile_idc}")
    track["tier"] = "high" if tier else "main"
    track["level"] = f"{level_idc / 30:.1f}".rstrip("0").rstrip(".") if level_idc else ""
    track["bitDepth"] = bit_depth_luma
    track["chromaFormat"] = {0: "4:0:0", 1: "4:2:0", 2: "4:2:2", 3: "4:4:4"}.get(chroma_format, "")


def _parse_avcc(payload: bytes, track: Dict[str, Any]):
    if len(payload) < 4:
        return
    profile_idc = payload[1]
    level_idc = payload[3]
    track["profile"] = _H264_PROFILES.get(profile_idc, f"profile{profile_idc}")
    track["level"] = f"{level_idc / 10:.1f}".rstrip("0").rstrip(".") if level_idc else ""
    track["bitDepth"] = 10 if profile_idc == 110 else 8
    track["chromaFormat"] = "4:2:0"
    # High profiles append chroma_format / bit_depth after the parameter sets.
    if profile_idc in (100, 110, 122, 244):
        try:
            offset = 5
            num_sps = payload[offset] & 0x1F
            offset += 1
            for _ in range(num_sps):
                length = struct.unpack_from(">H", payload, offset)[0]
                offset += 2 + length
            num_pps = payload[offset]
            offset += 1
            for _ in range(num_pps):
                length = struct.unpack_from(">H", payload, offset)[0]
                offset += 2 + length
            if offset + 3 <= len(payload):
                chroma = payload[offset] & 0x3
                track["chromaFormat"] = {0: "4:0:0", 1: "4:2:0", 2: "4:2:2", 3: "4:4:4"}.get(chroma, "")
                track["bitDepth"] = (payload[offset + 1] & 0x7) + 8
        except (IndexError, struct.error):
            pass


def _parse_visual_sample_entry(data: bytes, box_type: bytes, start: int, end: int, track: Dict[str, Any]):
    if end - start < 78:
        return
    width, height = struct.unpack_from(">HH", data, start + 24)
    track["fourcc"] = box_type.decode("latin-1")
    track["codec"] = _CODEC_NAMES.get(box_type, box_type.decode("latin-1"))
    track["width"] = width
    track["height"] = height

    for child_type, child_start, child_end in _iter_boxes(data, start + 78, end):
        payload = data[child_start:child_end]
        if child_type == b"hvcC":
            _parse_hvcc(payload, track)
        elif child_type == b"avcC":
            _parse_avcc(payload, track)
        elif child_type == b"colr" and len(payload) >= 10:
            colour_type = payload[:4]
            if colour_type in (b"nclx", b"nclc"):
                primaries, transfer, matrix = struct.unpack_from(">HHH", payload, 4)
                track["colorPrimaries"] = primaries
                track["colorTransfer"] = transfer
                track["colorMatrix"] = matrix
        elif child_type == b"pasp" and len(payload) >= 8:
            h_spacing, v_spacing = struct.unpack_from(">II", payload, 0)
            track["pixelAspect"] = f"{h_spacing}:{v_spacing}"
        elif child_type == b"st3d" and len(payload) >= 5:
            stereo_mode = payload[4]
            track["metadataStereo"] = {0: "mono", 1: "top-bottom", 2: "left-right", 3: "custom"}.get(stereo_mode, "")
            track["metadataSource"] = "spherical-v2"
        elif child_type == b"sv3d":
            _parse_sv3d(data, child_start, child_end, track)


def _parse_sv3d(data: bytes, start: int, end: int, track: Dict[str, Any]):
    track["metadataSource"] = "spherical-v2"
    for box_type, child_start, child_end in _iter_boxes(data, start, end):
        if box_type != b"proj":
            continue
        for proj_type, proj_start, proj_end in _iter_boxes(data, child_start, child_end):
            payload = data[proj_start:proj_end]
            if proj_type == b"equi":
                track["metadataProjection"] = "equirectangular"
                if len(payload) >= 20:
                    top, bottom, left, right = struct.unpack_from(">IIII", payload, 4)
                    scale = float(1 << 32)
                    track["projectionBounds"] = {
                        "top": top / scale,
                        "bottom": bottom / scale,
                        "left": left / scale,
                        "right": right / scale,
                    }
            elif proj_type == b"cbmp":
                track["metadataProjection"] = "cubemap"
            elif proj_type == b"mshp":
                track["metadataProjection"] = "mesh"


def _parse_audio_sample_entry(data: bytes, box_type: bytes, start: int, end: int, track: Dict[str, Any]):
    if end - start < 28:
        return
    version = struct.unpack_from(">H", data, start + 8)[0]
    channels, sample_size = struct.unpack_from(">HH", data, start + 16)
    sample_rate = struct.unpack_from(">I", data, start + 24)[0] >> 16
    track["fourcc"] = box_type.decode("latin-1")
    track["codec"] = _AUDIO_CODEC_NAMES.get(box_type, box_type.decode("latin-1"))
    track["channels"] = channels
    track["sampleSize"] = sample_size
    track["sampleRate"] = sample_rate
    if version == 2 and end - start >= 64:
        # QuickTime v2 sound description: 64-bit float sample rate + 32-bit channel count.
        rate = struct.unpack_from(">d", data, start + 32)[0]
        track["sampleRate"] = int(rate)
        track["channels"] = struct.unpack_from(">I", data, start + 40)[0]


def _parse_stsd(data: bytes, start: int, end: int, track: Dict[str, Any]):
    if end - start < 8:
        return
    for box_type, child_start, child_end in _iter_boxes(data, start + 8, end):
        if box_type in _VISUAL_SAMPLE_ENTRIES:
            _parse_visual_sample_entry(data, box_type, child_start, child_end, track)
        elif box_type in _AUDIO_SAMPLE_ENTRIES:
            _parse_audio_sample_entry(data, box_type, child_start, child_end, track)
        else:
            track.setdefault("fourcc", box_type.decode("latin-1"))
        break  # first sample description only


def _parse_spherical_v1_xml(xml_text: str, meta: Dict[str, Any]):
    def _tag(name: str) -> str:
        match = re.search(rf"<GSpherical:{name}>\s*([^<]*?)\s*</GSpherical:{name}>", xml_text, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    projection = _tag("ProjectionType").lower()
    stereo = _tag("StereoMode").lower()
    if projection:
        meta["metadataProjection"] = projection
    if stereo:
        meta["metadataStereo"] = stereo
    meta["metadataSource"] = "spherical-v1"
    if _tag("Spherical").lower() == "true" and not projection:
        meta["metadataProjection"] = "equirectangular"

    # Cropped equirect fields describe a partial sphere (e.g. VR180 exported correctly).
    try:
        full_w = int(_tag("FullPanoWidthPixels") or 0)
        crop_w = int(_tag("CroppedAreaImageWidthPixels") or 0)
        full_h = int(_tag("FullPanoHeightPixels") or 0)
        crop_h = int(_tag("CroppedAreaImageHeightPixels") or 0)
        left = int(_tag("CroppedAreaLeftPixels") or 0)
        top = int(_tag("CroppedAreaTopPixels") or 0)
    except ValueError:
        return
    if full_w > 0 and crop_w > 0 and (crop_w != full_w or crop_h != full_h):
        meta["projectionBounds"] = {
            "left": left / full_w,
            "right": max(0.0, (full_w - left - crop_w) / full_w),
            "top": top / full_h if full_h else 0.0,
            "bottom": max(0.0, (full_h - top - crop_h) / full_h) if full_h else 0.0,
        }


def _walk_track(data: bytes, start: int, end: int) -> Dict[str, Any]:
    track: Dict[str, Any] = {"handler": "", "timescale": 0, "duration": 0, "sampleCount": 0, "deltaTotal": 0, "bytes": 0}

    def walk(range_start: int, range_end: int):
        for box_type, child_start, child_end in _iter_boxes(data, range_start, range_end):
            if box_type == b"mdhd":
                track["timescale"], track["duration"] = _parse_mdhd(data, child_start, child_end)
            elif box_type == b"hdlr":
                track["handler"] = _parse_hdlr(data, child_start, child_end)
            elif box_type == b"stsd":
                _parse_stsd(data, child_start, child_end, track)
            elif box_type == b"stts":
                track["sampleCount"], track["deltaTotal"] = _parse_stts(data, child_start, child_end)
            elif box_type == b"stsz":
                track["bytes"] = _parse_stsz(data, child_start, child_end)
            elif box_type == b"uuid":
                _parse_uuid(data, child_start, child_end, track)
            elif box_type in _CONTAINER_BOXES:
                walk(child_start, child_end)
            elif box_type == b"meta":
                walk(_meta_children_start(data, child_start, child_end), child_end)

    walk(start, end)
    return track


def _meta_children_start(data: bytes, start: int, end: int) -> int:
    # ISO 'meta' is a full box (4 bytes version/flags); QuickTime 'meta' is a plain container.
    if end - start >= 8 and data[start + 4:start + 8] == b"hdlr":
        return start
    return start + 4


def _parse_uuid(data: bytes, start: int, end: int, meta: Dict[str, Any]):
    if end - start < 16:
        return
    if data[start:start + 16] != SPHERICAL_V1_UUID:
        return
    try:
        xml_text = data[start + 16:end].decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - decode with errors=replace never raises
        return
    _parse_spherical_v1_xml(xml_text, meta)


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------

def probe(path: str) -> VideoProbeResult:
    """Read container headers of `path` and return a VideoProbeResult (format not detected)."""
    result = VideoProbeResult()
    if not path or not os.path.isfile(path):
        raise ProbeError(f"file not found: {path}")

    result.sizeBytes = os.path.getsize(path)
    top, moov = _read_top_level(path)
    result.container = top["brand"] or "unknown"
    if moov is None:
        raise ProbeError("no moov box found (not an MP4/MOV file, or the file is truncated)")
    result.faststart = top["moov_offset"] >= 0 and (top["mdat_offset"] < 0 or top["moov_offset"] < top["mdat_offset"])

    movie_timescale = 0
    movie_duration = 0
    tracks: List[Dict[str, Any]] = []
    movie_meta: Dict[str, Any] = {}

    for box_type, start, end in _iter_boxes(moov):
        if box_type == b"mvhd":
            version = moov[start]
            if version == 1:
                movie_timescale = struct.unpack_from(">I", moov, start + 20)[0]
                movie_duration = struct.unpack_from(">Q", moov, start + 24)[0]
            else:
                movie_timescale = struct.unpack_from(">I", moov, start + 12)[0]
                movie_duration = struct.unpack_from(">I", moov, start + 16)[0]
        elif box_type == b"trak":
            tracks.append(_walk_track(moov, start, end))
        elif box_type == b"uuid":
            _parse_uuid(moov, start, end, movie_meta)
        elif box_type == b"udta":
            _walk_udta(moov, start, end, movie_meta)

    video = next((track for track in tracks if track.get("handler") == "vide" or track.get("width")), None)
    audio = next((track for track in tracks if track.get("handler") == "soun" or track.get("channels")), None)
    result.trackTypes = [track.get("handler") or track.get("fourcc") or "?" for track in tracks]

    if movie_timescale and movie_duration:
        result.durationSec = movie_duration / movie_timescale

    if video is not None:
        result.width = int(video.get("width", 0))
        result.height = int(video.get("height", 0))
        result.codec = str(video.get("codec", ""))
        result.bitDepth = int(video.get("bitDepth", 0))
        result.chromaFormat = str(video.get("chromaFormat", ""))
        result.profile = str(video.get("profile", ""))
        result.tier = str(video.get("tier", ""))
        result.level = str(video.get("level", ""))
        result.colorPrimaries = int(video.get("colorPrimaries", 0))
        result.colorTransfer = int(video.get("colorTransfer", 0))
        result.colorMatrix = int(video.get("colorMatrix", 0))
        result.pixelAspect = str(video.get("pixelAspect", ""))

        timescale = video.get("timescale") or 0
        duration = video.get("duration") or 0
        if timescale and duration:
            result.durationSec = duration / timescale
        sample_count = video.get("sampleCount") or 0
        delta_total = video.get("deltaTotal") or 0
        if timescale and sample_count and delta_total:
            result.fps = round(timescale * sample_count / delta_total, 3)

        video_bytes = video.get("bytes") or 0
        if result.durationSec > 0:
            payload_bytes = video_bytes if video_bytes else top["mdat_size"]
            result.bitrateMbps = round(payload_bytes * 8 / result.durationSec / 1_000_000, 2)

        for key in ("metadataProjection", "metadataStereo", "metadataSource", "projectionBounds"):
            if video.get(key):
                setattr(result, key, video[key])

    for key in ("metadataProjection", "metadataStereo", "metadataSource", "projectionBounds"):
        if movie_meta.get(key) and not getattr(result, key):
            setattr(result, key, movie_meta[key])

    if audio is not None:
        result.audioCodec = str(audio.get("codec", ""))
        result.audioChannels = int(audio.get("channels", 0))
        result.audioSampleRate = int(audio.get("sampleRate", 0))

    return result


def _walk_udta(data: bytes, start: int, end: int, meta: Dict[str, Any]):
    for box_type, child_start, child_end in _iter_boxes(data, start, end):
        if box_type == b"uuid":
            _parse_uuid(data, child_start, child_end, meta)
        elif box_type == b"meta":
            _walk_udta(data, _meta_children_start(data, child_start, child_end), child_end, meta)


# --------------------------------------------------------------------------------------
# Format detection (spec §8)
# --------------------------------------------------------------------------------------

_ASPECT_TOLERANCE = 0.05


def _stereo_from_metadata(metadata_stereo: str) -> Optional[str]:
    value = (metadata_stereo or "").strip().lower()
    if value in ("left-right", "left_right", "leftright", "sbs", "side-by-side"):
        return STEREO_SBS
    if value in ("top-bottom", "top_bottom", "topbottom", "tb", "over-under"):
        return STEREO_TB
    if value == "mono":
        return STEREO_MONO
    return None


def _per_eye_aspect(width: int, height: int, stereo: str) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    if stereo == STEREO_SBS:
        return (width / 2.0) / height
    if stereo == STEREO_TB:
        return width / (height / 2.0)
    return width / height


def _projection_from_aspect(aspect: float) -> Optional[str]:
    if aspect <= 0:
        return None
    if abs(aspect - 2.0) / 2.0 <= _ASPECT_TOLERANCE:
        return PROJECTION_360
    if abs(aspect - 1.0) <= _ASPECT_TOLERANCE:
        return PROJECTION_180
    if abs(aspect - 16.0 / 9.0) / (16.0 / 9.0) <= _ASPECT_TOLERANCE or abs(aspect - 4.0 / 3.0) / (4.0 / 3.0) <= _ASPECT_TOLERANCE:
        return PROJECTION_FLAT
    return None


def _projection_from_metadata(result: VideoProbeResult) -> Optional[str]:
    projection = (result.metadataProjection or "").lower()
    if not projection:
        return None
    bounds = result.projectionBounds or {}
    horizontal_coverage = 1.0 - float(bounds.get("left", 0.0)) - float(bounds.get("right", 0.0))
    if projection == "equirectangular":
        if 0.4 <= horizontal_coverage <= 0.6:
            return PROJECTION_180
        return PROJECTION_360
    if projection in ("rectilinear", "flat", "none"):
        return PROJECTION_FLAT
    return None


def detect_format(filename: str, result: Optional[VideoProbeResult], manual: str = FORMAT_AUTO) -> Tuple[str, str, List[str]]:
    """Return (formatId, detectionSource, warnings) following the spec priority order.

    1. manual value in config (anything but ``auto``)        -> source "manual"
    2. filename suffix (``_180_LR``, ``_360_TB`` ...)         -> source "filename"
    3. per-eye aspect ratio + stereo hint from metadata      -> source "aspect+metadata"
    4. metadata only                                          -> source "metadata"
    5. default 360 mono                                       -> source "default"

    Independent signals are cross-checked and disagreements are reported as warnings.
    """
    warnings: List[str] = []

    manual_id = normalize_format_id(manual)
    if manual_id and manual_id != FORMAT_AUTO:
        _cross_check(manual_id, filename, result, warnings, "manual setting")
        return manual_id, "manual", warnings

    name_projection, name_stereo = detect_format_from_filename(filename)
    meta_stereo = _stereo_from_metadata(result.metadataStereo) if result else None
    meta_projection = _projection_from_metadata(result) if result else None

    if name_projection is not None:
        stereo = name_stereo or STEREO_MONO
        if name_stereo is None and meta_stereo not in (None, STEREO_MONO):
            stereo = meta_stereo
            warnings.append(
                f"Filename gives projection {name_projection} without a stereo suffix; "
                f"stereo layout {stereo} taken from file metadata."
            )
        detected = make_format_id(name_projection, stereo)
        _cross_check(detected, filename, result, warnings, "filename")
        return detected, "filename", warnings

    if result is not None and result.width > 0 and result.height > 0:
        stereo = name_stereo or meta_stereo
        stereo_known = stereo is not None
        aspect = _per_eye_aspect(result.width, result.height, stereo or STEREO_MONO)
        aspect_projection = _projection_from_aspect(aspect)
        if aspect_projection is not None:
            if not stereo_known:
                if aspect_projection == PROJECTION_180:
                    warnings.append(
                        f"Per-eye aspect {aspect:.2f} (1:1) is ambiguous without a stereo hint: "
                        "could be 180 mono or 360 top-bottom. Defaulting to 360 mono; set the format manually."
                    )
                    return DEFAULT_FORMAT, "default", warnings
                warnings.append(
                    "No stereo layout in filename or metadata; assuming mono. "
                    "A 2:1 frame can also be 180 side-by-side."
                )
            detected = make_format_id(aspect_projection, stereo or STEREO_MONO)
            if meta_projection is not None and meta_projection != aspect_projection:
                warnings.append(
                    f"File metadata claims {result.metadataProjection or meta_projection} but the per-eye aspect "
                    f"{aspect:.2f} indicates {aspect_projection}; trusting the aspect ratio."
                )
            source = "aspect+metadata" if (meta_stereo is not None or meta_projection is not None) else "aspect"
            return detected, source, warnings

    if meta_projection is not None or meta_stereo is not None:
        projection = meta_projection or PROJECTION_360
        stereo = meta_stereo or STEREO_MONO
        warnings.append("Format taken from file metadata only (low confidence): check it visually before class.")
        return make_format_id(projection, stereo), "metadata", warnings

    warnings.append("Format could not be determined; defaulting to 360 mono. Set it manually or rename the file (_180_LR, _360_TB ...).")
    return DEFAULT_FORMAT, "default", warnings


def _cross_check(format_id: str, filename: str, result: Optional[VideoProbeResult], warnings: List[str], chosen: str):
    """Compare the chosen format with the other signals and log disagreements."""
    projection, stereo = split_format_id(format_id)

    name_projection, name_stereo = detect_format_from_filename(filename)
    if chosen != "filename" and name_projection is not None:
        name_format = make_format_id(name_projection, name_stereo or STEREO_MONO)
        if name_format != format_id:
            warnings.append(f"Filename suggests {name_format} but {chosen} is {format_id}.")

    if result is None:
        return

    if result.width > 0 and result.height > 0:
        aspect = _per_eye_aspect(result.width, result.height, stereo)
        aspect_projection = _projection_from_aspect(aspect)
        if aspect_projection is not None and aspect_projection != projection:
            warnings.append(
                f"Per-eye aspect {aspect:.2f} for {stereo} layout suggests {aspect_projection}, "
                f"but {chosen} is {projection}."
            )
        elif aspect_projection is None:
            warnings.append(f"Unusual per-eye aspect {aspect:.2f} for {stereo} layout ({result.width}x{result.height}).")

    meta_stereo = _stereo_from_metadata(result.metadataStereo)
    if meta_stereo is not None and meta_stereo != stereo:
        warnings.append(f"File metadata says stereo '{result.metadataStereo}' but {chosen} is {stereo}.")

    meta_projection = _projection_from_metadata(result)
    if meta_projection is not None and meta_projection != projection:
        warnings.append(
            f"File metadata says projection '{result.metadataProjection}' ({meta_projection}) but {chosen} is {projection}. "
            "Metadata from some exporters is wrong for VR180; the filename/aspect is trusted."
        )


def technical_warnings(result: VideoProbeResult) -> List[str]:
    """Warnings about the file itself, independent of the projection/stereo decision."""
    warnings: List[str] = []
    pixels = result.width * result.height
    if result.codec == "hevc" and result.level:
        try:
            level = float(result.level)
        except ValueError:
            level = 0.0
        if level > 6.1:
            warnings.append(f"HEVC level {result.level} exceeds Level 6.1 supported by Quest decoders.")
        if result.tier == "high":
            warnings.append("HEVC high tier: some mobile decoders only support main tier at this level.")
    if result.bitDepth and result.bitDepth > 8:
        warnings.append(f"{result.bitDepth}-bit video: playback requires a Main10-capable decoder.")
    if pixels > 8192 * 4096:
        warnings.append(f"Frame {result.width}x{result.height} exceeds 8192x4096.")
    elif pixels > 4096 * 4096:
        warnings.append(f"Frame {result.width}x{result.height} is above 4096x4096: needs an 8K-capable headset.")
    if result.bitrateMbps > 120:
        warnings.append(f"Bitrate {result.bitrateMbps:.0f} Mbit/s is very high; expect long copy times and possible stutter.")
    if result.audioChannels > 2:
        warnings.append(f"{result.audioChannels} audio channels: only stereo is played back.")
    if any(track == "tmcd" for track in result.trackTypes):
        warnings.append("File contains a timecode track (tmcd); it is ignored by the player.")
    if result.colorTransfer in (16, 18):
        warnings.append("HDR transfer function detected (PQ/HLG); the player expects SDR BT.709.")
    return warnings


def probe_and_detect(path: str, manual: str = FORMAT_AUTO, filename: Optional[str] = None) -> VideoProbeResult:
    """Probe the file and fill detectedType / detectionSource / warnings."""
    result = probe(path)
    name = filename or os.path.basename(path)
    detected, source, warnings = detect_format(name, result, manual)
    result.detectedType = detected
    result.detectionSource = source
    if source == "manual":
        result.autoDetectedType, result.autoDetectionSource, _ = detect_format(name, result, FORMAT_AUTO)
    else:
        result.autoDetectedType, result.autoDetectionSource = detected, source
    result.warnings = warnings + technical_warnings(result)
    return result


def detect_without_probe(filename: str, manual: str = FORMAT_AUTO) -> Tuple[str, str, List[str]]:
    """Detection when only the filename is known (no local file to read)."""
    return detect_format(filename, None, manual)


def format_summary(result: VideoProbeResult) -> str:
    """One-line technical summary for logs."""
    parts = [f"{result.width}x{result.height}"]
    if result.fps:
        parts.append(f"{result.fps:g}fps")
    if result.codec:
        codec = result.codec
        if result.profile:
            codec += f" {result.profile}"
        if result.level:
            codec += f" L{result.level}"
        parts.append(codec)
    if result.bitDepth:
        parts.append(f"{result.bitDepth}-bit")
    if result.bitrateMbps:
        parts.append(f"{result.bitrateMbps:g} Mbit/s")
    if result.detectedType:
        parts.append(f"format={result.detectedType} ({result.detectionSource})")
    return ", ".join(parts)
