import os
import struct
import tempfile
import unittest
from pathlib import Path

from App.server import video_probe as vp

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES_DIR = REPO_ROOT / "Video Samples"
SAMPLE_180 = SAMPLES_DIR / "1803D 8K60 Sample for Eugen - short_180_LR.mp4"
SAMPLE_360 = SAMPLES_DIR / "Test 360 3D 5.7K clip for Eugen_360_TB.mp4"


# --------------------------------------------------------------------------------------
# Synthetic MP4 builder: enough boxes for the parser, moov placed AFTER mdat like the
# customer's exports. Keeps the tests independent of the (git-ignored) sample files.
# --------------------------------------------------------------------------------------

def box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), box_type) + payload


def full_box(box_type: bytes, payload: bytes, version: int = 0) -> bytes:
    return box(box_type, bytes([version, 0, 0, 0]) + payload)


def hvcc(profile_idc=2, tier=0, level_idc=183, bit_depth=10) -> bytes:
    data = bytearray(23)
    data[0] = 1
    data[1] = (tier << 5) | profile_idc
    data[12] = level_idc
    data[16] = 0xFC | 1           # chroma 4:2:0
    data[17] = 0xF8 | (bit_depth - 8)
    data[18] = 0xF8 | (bit_depth - 8)
    return box(b"hvcC", bytes(data))


def visual_entry(width: int, height: int, children: bytes, fourcc=b"hvc1") -> bytes:
    body = bytearray(78)
    struct.pack_into(">H", body, 6, 1)             # data reference index
    struct.pack_into(">HH", body, 24, width, height)
    struct.pack_into(">II", body, 28, 0x00480000, 0x00480000)
    struct.pack_into(">H", body, 40, 1)            # frame count
    struct.pack_into(">H", body, 74, 24)           # depth
    struct.pack_into(">h", body, 76, -1)
    return box(fourcc, bytes(body) + children)


def audio_entry(channels=2, sample_rate=48000) -> bytes:
    body = bytearray(28)
    struct.pack_into(">H", body, 6, 1)
    struct.pack_into(">HH", body, 16, channels, 16)
    struct.pack_into(">I", body, 24, sample_rate << 16)
    return box(b"mp4a", bytes(body))


def spherical_v1(projection="equirectangular", stereo="left-right") -> bytes:
    xml = (
        '<?xml version="1.0"?><rdf:SphericalVideo xmlns:GSpherical="http://ns.google.com/videos/1.0/spherical/">'
        "<GSpherical:Spherical>true</GSpherical:Spherical>"
        f"<GSpherical:ProjectionType>{projection}</GSpherical:ProjectionType>"
        f"<GSpherical:StereoMode>{stereo}</GSpherical:StereoMode>"
        "</rdf:SphericalVideo>"
    ).encode("utf-8")
    return box(b"uuid", vp.SPHERICAL_V1_UUID + xml)


def video_trak(width, height, timescale, sample_count, delta, sample_bytes, extra_entry_children=b"", extra_trak_children=b"") -> bytes:
    mdhd = full_box(b"mdhd", struct.pack(">IIII", 0, 0, timescale, sample_count * delta) + b"\x55\xc4\x00\x00")
    hdlr = full_box(b"hdlr", b"\x00" * 4 + b"vide" + b"\x00" * 12 + b"\x00")
    stsd = full_box(b"stsd", struct.pack(">I", 1) + visual_entry(width, height, hvcc() + extra_entry_children))
    stts = full_box(b"stts", struct.pack(">III", 1, sample_count, delta))
    stsz = full_box(b"stsz", struct.pack(">II", sample_bytes // sample_count, sample_count))
    stbl = box(b"stbl", stsd + stts + stsz)
    minf = box(b"minf", stbl)
    mdia = box(b"mdia", mdhd + hdlr + minf)
    return box(b"trak", mdia + extra_trak_children)


def audio_trak(channels=2) -> bytes:
    mdhd = full_box(b"mdhd", struct.pack(">IIII", 0, 0, 48000, 48000 * 10) + b"\x55\xc4\x00\x00")
    hdlr = full_box(b"hdlr", b"\x00" * 4 + b"soun" + b"\x00" * 12 + b"\x00")
    stsd = full_box(b"stsd", struct.pack(">I", 1) + audio_entry(channels))
    minf = box(b"minf", box(b"stbl", stsd))
    return box(b"trak", box(b"mdia", mdhd + hdlr + minf))


def tmcd_trak() -> bytes:
    hdlr = full_box(b"hdlr", b"\x00" * 4 + b"tmcd" + b"\x00" * 12 + b"\x00")
    return box(b"trak", box(b"mdia", hdlr))


def build_mp4(path: str, *, width, height, fps_num, fps_den, seconds, stereo_xml="left-right", projection_xml="equirectangular", mdat_bytes=4096):
    timescale = fps_num
    delta = fps_den
    sample_count = int(round(seconds * fps_num / fps_den))
    mvhd = full_box(b"mvhd", struct.pack(">IIII", 0, 0, 1000, int(seconds * 1000)) + b"\x00" * 80)
    tracks = video_trak(width, height, timescale, sample_count, delta, mdat_bytes) + audio_trak() + tmcd_trak()
    moov = box(b"moov", mvhd + tracks + spherical_v1(projection_xml, stereo_xml))
    ftyp = box(b"ftyp", b"isom" + struct.pack(">I", 0x200) + b"isomiso2mp41")
    mdat = box(b"mdat", b"\x00" * mdat_bytes)
    with open(path, "wb") as handle:
        handle.write(ftyp + box(b"free", b"") + mdat + moov)


class SyntheticProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _path(self, name: str) -> str:
        return os.path.join(self.tmp.name, name)

    def test_parses_headers_with_moov_at_end(self):
        path = self._path("clip_180_LR.mp4")
        build_mp4(path, width=8192, height=4096, fps_num=60000, fps_den=1001, seconds=10, mdat_bytes=120_000)
        result = vp.probe(path)

        self.assertEqual((result.width, result.height), (8192, 4096))
        self.assertAlmostEqual(result.fps, 59.94, places=2)
        self.assertEqual(result.codec, "hevc")
        self.assertEqual(result.profile, "Main10")
        self.assertEqual(result.tier, "main")
        self.assertEqual(result.level, "6.1")
        self.assertEqual(result.bitDepth, 10)
        self.assertEqual(result.chromaFormat, "4:2:0")
        self.assertEqual(result.audioCodec, "aac")
        self.assertEqual(result.audioChannels, 2)
        self.assertEqual(result.audioSampleRate, 48000)
        self.assertEqual(result.trackTypes, ["vide", "soun", "tmcd"])
        self.assertEqual(result.metadataProjection, "equirectangular")
        self.assertEqual(result.metadataStereo, "left-right")
        self.assertEqual(result.metadataSource, "spherical-v1")
        self.assertFalse(result.faststart)
        self.assertAlmostEqual(result.durationSec, 10.0, places=1)
        self.assertGreater(result.bitrateMbps, 0)

    def test_detects_customer_180_case_from_filename_and_warns_about_metadata(self):
        path = self._path("sample - short_180_LR.mp4")
        build_mp4(path, width=8192, height=4096, fps_num=60000, fps_den=1001, seconds=5)
        result = vp.probe_and_detect(path)

        self.assertEqual(result.detectedType, "180_sbs")
        self.assertEqual(result.detectionSource, "filename")
        self.assertTrue(any("metadata" in warning.lower() and "180" in warning for warning in result.warnings))

    def test_detects_360_tb_from_filename_with_consistent_metadata(self):
        path = self._path("clip_360_TB.mp4")
        build_mp4(path, width=5760, height=5760, fps_num=15360, fps_den=512, seconds=5, stereo_xml="top-bottom")
        result = vp.probe_and_detect(path)

        self.assertEqual(result.detectedType, "360_tb")
        self.assertEqual(result.detectionSource, "filename")
        self.assertAlmostEqual(result.fps, 30.0, places=2)
        # Metadata agrees: no disagreement warning about projection/stereo.
        self.assertFalse(any("metadata says" in warning.lower() for warning in result.warnings))

    def test_manual_override_wins_but_is_cross_checked(self):
        path = self._path("clip_360_TB.mp4")
        build_mp4(path, width=5760, height=5760, fps_num=15360, fps_den=512, seconds=5, stereo_xml="top-bottom")
        result = vp.probe_and_detect(path, manual="180_sbs")

        self.assertEqual(result.detectedType, "180_sbs")
        self.assertEqual(result.detectionSource, "manual")
        self.assertTrue(any("filename suggests 360_tb" in warning.lower() for warning in result.warnings))
        # The UI can still offer what auto-detection would have picked.
        self.assertEqual(result.autoDetectedType, "360_tb")
        self.assertEqual(result.autoDetectionSource, "filename")

    def test_aspect_plus_metadata_when_filename_has_no_suffix(self):
        path = self._path("lesson.mp4")
        build_mp4(path, width=8192, height=4096, fps_num=60000, fps_den=1001, seconds=5, stereo_xml="left-right")
        result = vp.probe_and_detect(path)

        # SBS from metadata -> per-eye 4096x4096 = 1:1 -> 180, metadata says 360 -> warn, trust aspect.
        self.assertEqual(result.detectedType, "180_sbs")
        self.assertEqual(result.detectionSource, "aspect+metadata")
        self.assertTrue(any("trusting the aspect" in warning.lower() for warning in result.warnings))

    def test_not_an_mp4_raises(self):
        path = self._path("garbage.mp4")
        with open(path, "wb") as handle:
            handle.write(b"not a video at all" * 10)
        with self.assertRaises(vp.ProbeError):
            vp.probe(path)

    def test_missing_file_raises(self):
        with self.assertRaises(vp.ProbeError):
            vp.probe(self._path("nope.mp4"))


class DetectFormatWithoutProbeTests(unittest.TestCase):
    def test_default_when_nothing_is_known(self):
        detected, source, warnings = vp.detect_format("lesson01.mp4", None)
        self.assertEqual((detected, source), ("360", "default"))
        self.assertTrue(warnings)

    def test_filename_only(self):
        detected, source, warnings = vp.detect_format("tour_180_LR.mp4", None)
        self.assertEqual((detected, source), ("180_sbs", "filename"))
        self.assertEqual(warnings, [])

    def test_manual_without_probe(self):
        detected, source, _ = vp.detect_format("whatever.mp4", None, manual="360_OU")
        self.assertEqual((detected, source), ("360_tb", "manual"))

    def test_aspect_only_2_to_1_assumes_mono_with_warning(self):
        detected, source, warnings = vp.detect_format("x.mp4", vp.VideoProbeResult(width=3840, height=1920))
        self.assertEqual((detected, source), ("360", "aspect"))
        self.assertTrue(any("assuming mono" in warning.lower() for warning in warnings))

    def test_aspect_1_to_1_without_stereo_hint_is_ambiguous(self):
        detected, source, warnings = vp.detect_format("x.mp4", vp.VideoProbeResult(width=4096, height=4096))
        self.assertEqual((detected, source), ("360", "default"))
        self.assertTrue(any("ambiguous" in warning.lower() for warning in warnings))

    def test_flat_16_9(self):
        detected, source, _ = vp.detect_format("x.mp4", vp.VideoProbeResult(width=1920, height=1080))
        self.assertEqual((detected, source), ("2d", "aspect"))

    def test_metadata_only_when_aspect_is_odd(self):
        probe = vp.VideoProbeResult(width=3000, height=2000, metadataProjection="equirectangular", metadataStereo="top-bottom")
        detected, source, warnings = vp.detect_format("x.mp4", probe)
        self.assertEqual((detected, source), ("360_tb", "metadata"))
        self.assertTrue(any("low confidence" in warning.lower() for warning in warnings))

    def test_spherical_v2_cropped_equirect_means_180(self):
        probe = vp.VideoProbeResult(
            width=3000, height=2000,
            metadataProjection="equirectangular",
            metadataStereo="left-right",
            projectionBounds={"left": 0.25, "right": 0.25, "top": 0.0, "bottom": 0.0},
        )
        detected, source, _ = vp.detect_format("x.mp4", probe)
        self.assertEqual((detected, source), ("180_sbs", "metadata"))


class TechnicalWarningTests(unittest.TestCase):
    def test_flags_high_tier_10bit_and_size(self):
        probe = vp.VideoProbeResult(width=5760, height=5760, codec="hevc", level="6.1", tier="high", bitDepth=10, trackTypes=["vide", "soun", "tmcd"])
        warnings = vp.technical_warnings(probe)
        joined = " ".join(warnings).lower()
        self.assertIn("high tier", joined)
        self.assertIn("10-bit", joined)
        self.assertIn("above 4096x4096", joined)
        self.assertIn("timecode", joined)

    def test_clean_1080p_has_no_warnings(self):
        probe = vp.VideoProbeResult(width=1920, height=1080, codec="h264", level="4.1", bitDepth=8, bitrateMbps=12, audioChannels=2)
        self.assertEqual(vp.technical_warnings(probe), [])


@unittest.skipUnless(SAMPLE_180.exists() and SAMPLE_360.exists(), "customer sample files not present (git-ignored)")
class RealSampleTests(unittest.TestCase):
    """Expected values fixed from docs/specs/stereo-3d-180-360.md §1."""

    def test_vr180_sample(self):
        result = vp.probe_and_detect(str(SAMPLE_180))
        self.assertEqual((result.width, result.height), (8192, 4096))
        self.assertAlmostEqual(result.fps, 59.94, places=2)
        self.assertEqual(result.codec, "hevc")
        self.assertEqual(result.profile, "Main10")
        self.assertEqual(result.tier, "main")
        self.assertEqual(result.level, "6.1")
        self.assertEqual(result.bitDepth, 10)
        self.assertEqual((result.colorPrimaries, result.colorTransfer, result.colorMatrix), (1, 4, 1))
        self.assertEqual(result.pixelAspect, "1:1")
        self.assertEqual(result.audioChannels, 2)
        self.assertEqual(result.audioSampleRate, 48000)
        self.assertEqual(result.trackTypes, ["vide", "soun", "tmcd"])
        self.assertEqual(result.metadataProjection, "equirectangular")
        self.assertEqual(result.metadataStereo, "left-right")
        self.assertFalse(result.faststart)
        self.assertGreater(result.bitrateMbps, 90)
        self.assertLess(result.bitrateMbps, 105)
        self.assertEqual(result.detectedType, "180_sbs")
        self.assertEqual(result.detectionSource, "filename")
        self.assertTrue(any("metadata" in warning.lower() for warning in result.warnings))

    def test_360_tb_sample(self):
        result = vp.probe_and_detect(str(SAMPLE_360))
        self.assertEqual((result.width, result.height), (5760, 5760))
        self.assertAlmostEqual(result.fps, 30.0, places=2)
        self.assertEqual(result.profile, "Main10")
        self.assertEqual(result.tier, "high")
        self.assertEqual(result.level, "6.1")
        self.assertEqual(result.bitDepth, 10)
        self.assertEqual(result.metadataStereo, "top-bottom")
        self.assertGreater(result.bitrateMbps, 95)
        self.assertLess(result.bitrateMbps, 110)
        self.assertEqual(result.detectedType, "360_tb")
        self.assertEqual(result.detectionSource, "filename")


if __name__ == "__main__":
    unittest.main()
