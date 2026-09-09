import unittest

from App.server import video_format as vf


class NormalizeFormatIdTests(unittest.TestCase):
    def test_canonical_ids_pass_through(self):
        for format_id in ("2d", "360", "360_sbs", "360_tb", "180", "180_sbs", "180_tb", "auto"):
            self.assertEqual(vf.normalize_format_id(format_id), format_id)

    def test_legacy_aliases(self):
        self.assertEqual(vf.normalize_format_id("flat"), "2d")
        self.assertEqual(vf.normalize_format_id("sphere"), "360")
        self.assertEqual(vf.normalize_format_id("360_mono"), "360")
        self.assertEqual(vf.normalize_format_id("180_mono"), "180")

    def test_industry_aliases(self):
        self.assertEqual(vf.normalize_format_id("180_LR"), "180_sbs")
        self.assertEqual(vf.normalize_format_id("180_3dh"), "180_sbs")
        self.assertEqual(vf.normalize_format_id("360_OU"), "360_tb")
        self.assertEqual(vf.normalize_format_id("360_3dv"), "360_tb")
        self.assertEqual(vf.normalize_format_id("360_lr"), "360_sbs")
        self.assertEqual(vf.normalize_format_id("360_3dh"), "360_sbs")
        self.assertEqual(vf.normalize_format_id("180_ou"), "180_tb")
        self.assertEqual(vf.normalize_format_id("180_3dv"), "180_tb")

    def test_token_order_and_case_do_not_matter(self):
        self.assertEqual(vf.normalize_format_id("SBS_180"), "180_sbs")
        self.assertEqual(vf.normalize_format_id(" TB-360 "), "360_tb")
        self.assertEqual(vf.normalize_format_id("AUTO"), "auto")

    def test_unknown_values_return_none(self):
        self.assertIsNone(vf.normalize_format_id("bogus"))
        self.assertIsNone(vf.normalize_format_id(""))
        self.assertIsNone(vf.normalize_format_id(None))
        self.assertIsNone(vf.normalize_format_id("sbs"))  # stereo without projection


class SplitAndLegacyTests(unittest.TestCase):
    def test_split(self):
        self.assertEqual(vf.split_format_id("2d"), ("flat", "mono"))
        self.assertEqual(vf.split_format_id("180_sbs"), ("180", "sbs"))
        self.assertEqual(vf.split_format_id("360_tb"), ("360", "tb"))
        # Unknown and auto fall back to the default so callers never crash.
        self.assertEqual(vf.split_format_id("auto"), ("360", "mono"))
        self.assertEqual(vf.split_format_id("???"), ("360", "mono"))

    def test_make_format_id_round_trip(self):
        for format_id, (projection, stereo) in vf.CANONICAL_FORMATS.items():
            self.assertEqual(vf.make_format_id(projection, stereo), format_id)
        self.assertEqual(vf.make_format_id("flat", "sbs"), "2d")  # flat has no stereo variant

    def test_legacy_mode_for_old_players(self):
        self.assertEqual(vf.legacy_mode_for("2d"), "2d")
        self.assertEqual(vf.legacy_mode_for("360"), "360")
        self.assertEqual(vf.legacy_mode_for("360_tb"), "360")
        self.assertEqual(vf.legacy_mode_for("180_sbs"), "360")
        self.assertEqual(vf.legacy_mode_for("180"), "360")

    def test_format_id_from_legacy_mode(self):
        self.assertEqual(vf.format_id_from_legacy_mode("2d"), "2d")
        self.assertEqual(vf.format_id_from_legacy_mode("flat"), "2d")
        self.assertEqual(vf.format_id_from_legacy_mode("360"), "360")
        self.assertEqual(vf.format_id_from_legacy_mode("sphere"), "360")
        self.assertEqual(vf.format_id_from_legacy_mode(None), "360")
        self.assertEqual(vf.format_id_from_legacy_mode("garbage"), "360")

    def test_is_stereo(self):
        self.assertTrue(vf.is_stereo("180_sbs"))
        self.assertTrue(vf.is_stereo("360_tb"))
        self.assertFalse(vf.is_stereo("360"))
        self.assertFalse(vf.is_stereo("2d"))


class FilenameDetectionTests(unittest.TestCase):
    def test_customer_samples(self):
        self.assertEqual(
            vf.detect_format_from_filename("1803D 8K60 Sample for Eugen - short_180_LR.mp4"),
            ("180", "sbs"),
        )
        self.assertEqual(
            vf.detect_format_from_filename("Test 360 3D 5.7K clip for Eugen_360_TB.mp4"),
            ("360", "tb"),
        )

    def test_convention_examples(self):
        self.assertEqual(vf.format_id_from_filename("reef-dive_180_LR.mp4"), "180_sbs")
        self.assertEqual(vf.format_id_from_filename("classroom-tour_360_TB.mp4"), "360_tb")
        self.assertEqual(vf.format_id_from_filename("intro-lecture_2d_MONO.mp4"), "2d")
        self.assertEqual(vf.format_id_from_filename("sunset_360_MONO.mp4"), "360")
        self.assertEqual(vf.format_id_from_filename("history_360.mp4"), "360")
        self.assertEqual(vf.format_id_from_filename("/sdcard/Movies/clip_180_OU.mov"), "180_tb")

    def test_no_suffix(self):
        self.assertEqual(vf.detect_format_from_filename("lesson01.mp4"), (None, None))
        self.assertIsNone(vf.format_id_from_filename("lesson01.mp4"))
        self.assertIsNone(vf.format_id_from_filename(""))

    def test_number_in_the_middle_is_not_a_suffix(self):
        # "360" as part of the title, not at the end.
        self.assertEqual(vf.detect_format_from_filename("Test 360 clip final.mp4"), (None, None))

    def test_stereo_only_suffix_gives_partial_result(self):
        self.assertEqual(vf.detect_format_from_filename("clip_LR.mp4"), (None, "sbs"))
        self.assertIsNone(vf.format_id_from_filename("clip_LR.mp4"))


class DescribeTests(unittest.TestCase):
    def test_list_formats_covers_all_canonical(self):
        ids = [item["formatId"] for item in vf.list_formats()]
        self.assertEqual(set(ids), set(vf.CANONICAL_FORMATS))

    def test_describe(self):
        info = vf.describe_format("180_LR")
        self.assertEqual(info["formatId"], "180_sbs")
        self.assertEqual(info["projection"], "180")
        self.assertEqual(info["stereo"], "sbs")
        self.assertEqual(info["legacyMode"], "360")


if __name__ == "__main__":
    unittest.main()
