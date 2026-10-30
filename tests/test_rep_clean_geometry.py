"""Geometry tests are not live OCR evidence or an automatic product detector."""
import importlib.util
from io import BytesIO
from pathlib import Path
import unittest

from src.services.rep_clean_geometry import crop_plan, render_edge_crop, variance_check


class CropPlanTests(unittest.TestCase):
    def test_top_and_bottom_bands_keep_product(self):
        p = crop_plan((800, 1000), [(0, 0, 800, 200), (0, 900, 800, 1000)],
                      [(200, 300, 600, 850)])
        self.assertEqual(p["crop"], [0, 204, 800, 896])
        self.assertEqual(p["size"], [800, 800])
        self.assertEqual(p["offset"], [0, -150])

    def test_product_overlap_is_rejected(self):
        self.assertEqual(crop_plan((800, 1000), [(0, 0, 600, 200)],
                                   [(200, 180, 600, 800)])["why"], "crop_overlaps_product")

    def test_unknown_product_is_not_treated_as_empty_background(self):
        for value in (None, [], "unknown"):
            with self.subTest(value=value):
                self.assertFalse(crop_plan((800, 1000), [(0, 0, 600, 200)], value)["ok"])

    def test_central_text_is_not_cropped_even_when_product_does_not_overlap(self):
        self.assertEqual(crop_plan((800, 1000), [(0, 350, 100, 400)],
                                   [(200, 500, 600, 800)])["why"], "text_outside_edge_band")

    def test_margin_cannot_push_band_beyond_thirty_percent(self):
        self.assertFalse(crop_plan((800, 1000), [(0, 0, 600, 300)],
                                  [(200, 400, 600, 800)])["ok"])

    def test_invalid_boxes_cannot_be_clipped_into_success(self):
        for box in ((0, 0, 0, 20), (-1, 0, 100, 20), (0, 0, 801, 20),
                    (0, 0, float("nan"), 20), (0, False, 100, 20)):
            with self.subTest(box=box):
                self.assertFalse(crop_plan((800, 1000), [box], [(200, 300, 600, 800)])["ok"])

    def test_size_limit_and_no_padding_based_upscale(self):
        self.assertEqual(crop_plan((400, 600), [(0, 0, 400, 160)],
                                   [(50, 200, 350, 580)])["why"], "retained_image_too_small")
        self.assertFalse(crop_plan((2001, 2001), [(0, 0, 100, 20)],
                                  [(200, 300, 600, 800)])["ok"])

    def test_all_protected_regions_must_survive(self):
        self.assertFalse(crop_plan((800, 1000), [(0, 0, 600, 200)],
                                  [(200, 300, 600, 800), (600, 100, 700, 150)])["ok"])

    def test_sportlink_watch_text_cannot_be_removed_by_edge_crop(self):
        # Human-reviewed fixture geometry: lettering on the watch face is
        # inside the merchandise, not a removable top/bottom caption.
        p = crop_plan((750, 1000), [(0, 0, 735, 275), (325, 690, 450, 780),
                                   (0, 935, 715, 970)], [(180, 205, 520, 910)])
        self.assertEqual(p["why"], "text_outside_edge_band")

    def test_fractional_coordinates_are_rounded_outwards(self):
        p = crop_plan((800, 1000), [(0.1, 0.2, 400.3, 199.1)], [(200, 300, 600, 800)])
        self.assertEqual(p["crop"][1], 204)


class VarianceTests(unittest.TestCase):
    def test_symmetric_threshold_rejects_flattening_and_noise(self):
        self.assertTrue(variance_check(100, 120)["ok"])
        self.assertFalse(variance_check(100, 60)["ok"])
        self.assertFalse(variance_check(100, 150)["ok"])
        self.assertFalse(variance_check(150, 100)["ok"])

    def test_missing_or_flat_measurements_are_not_success(self):
        for value in (0, -1, None, float("nan"), float("inf"), True):
            with self.subTest(value=value):
                self.assertIsNone(variance_check(value, 10)["ratio"])
                self.assertFalse(variance_check(10, value)["ok"])


@unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow required for raster contracts")
class RasterTests(unittest.TestCase):
    def test_retained_pixels_and_product_are_exact_after_padding(self):
        from PIL import Image
        source = Image.new("RGB", (800, 1000), (10, 20, 30))
        # A protected feature must survive exactly, rather than be inpainted.
        source.paste((123, 234, 45), (200, 300, 600, 800))
        raw = BytesIO()
        source.save(raw, format="PNG")
        result = render_edge_crop(raw.getvalue(), [(0, 0, 800, 200), (0, 900, 800, 1000)],
                                  [(200, 300, 600, 800)])
        self.assertTrue(result["ok"])
        actual = Image.open(BytesIO(result["bytes"]))
        self.assertEqual(actual.crop((0, 54, 800, 746)).tobytes(), source.crop((0, 204, 800, 896)).tobytes())
        self.assertEqual(actual.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(actual.crop((200, 150, 600, 650)).tobytes(), source.crop((200, 300, 600, 800)).tobytes())
        self.assertTrue(result["requires_fresh_ocr"])

    def test_invalid_data_and_orientation_are_rejected(self):
        from PIL import Image
        self.assertFalse(render_edge_crop(b"not an image", [], [])["ok"])
        raw = BytesIO()
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (800, 1000)).save(raw, format="JPEG", exif=exif)
        self.assertEqual(render_edge_crop(raw.getvalue(), [(0, 0, 800, 200)],
                                         [(200, 300, 600, 800)])["why"], "orientation_requires_new_coordinates")

    def test_alpha_is_not_silently_lost(self):
        from PIL import Image
        raw = BytesIO()
        Image.new("RGBA", (800, 1000)).save(raw, format="PNG")
        self.assertEqual(render_edge_crop(raw.getvalue(), [(0, 0, 800, 200)],
                                         [(200, 300, 600, 800)])["why"], "unsupported_color_mode")

    def test_real_lamp_crop_preserves_reviewed_product_region(self):
        from PIL import Image
        path = Path(__file__).resolve().parents[1] / "docs/screens/patrol148/before-d5af2185-p2.jpg"
        if not path.exists():
            self.skipTest("repository photo fixture unavailable")
        # Human-reviewed bounds on this fixture, NOT production OCR/detection.
        result = render_edge_crop(path.read_bytes(), [(170, 95, 1260, 365), (1150, 1360, 1390, 1420)],
                                  [(570, 520, 770, 850)])
        self.assertTrue(result["ok"])
        source = Image.open(path)
        actual = Image.open(BytesIO(result["bytes"]))
        dx, dy = result["offset"]
        self.assertEqual(actual.crop((570 + dx, 520 + dy, 770 + dx, 850 + dy)).tobytes(),
                         source.crop((570, 520, 770, 850)).tobytes())


if __name__ == "__main__":
    unittest.main()
