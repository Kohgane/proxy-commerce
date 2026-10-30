"""Provider transport doubles: never calls a live API or writes production."""
import base64
import sys
import types
import unittest
from unittest.mock import patch

from src.services.rep_clean_candidate import fresh_text_count


class FreshOcrTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.body = {"TextDetections": []}
        self.provider = types.ModuleType("src.services.ocr_tencent")
        self.provider.is_configured = lambda: True
        self.provider.unopened = lambda: False
        self.provider._fits_as_is = lambda raw: True
        self.provider._LANG = types.SimpleNamespace(value="zh")
        self.provider.no_text = lambda exc: getattr(exc, "code", None) == "FailedOperation.ImageNoText"
        self.provider._call = self.call
        self.patcher = patch.dict(sys.modules, {"src.services.ocr_tencent": self.provider})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        # from-package imports may otherwise reuse a previously loaded module.
        import src.services
        self.attr = patch.object(src.services, "ocr_tencent", self.provider, create=True)
        self.attr.start()
        self.addCleanup(self.attr.stop)

    def call(self, value):
        self.assertEqual(self.provider._LANG.value, "auto")
        self.sent.append(base64.b64decode(value))
        return self.body

    def test_exact_bytes_are_sent_without_resizing(self):
        self.assertEqual(fresh_text_count(b"exact candidate PNG"), 0)
        self.assertEqual(self.sent, [b"exact candidate PNG"])
        self.assertEqual(self.provider._LANG.value, "zh")

    def test_missing_response_is_not_zero(self):
        for body in (None, {}, [], {"TextDetections": None}, {"TextDetections": {}},
                     {"TextDetections": [], "Error": {"Code": "Denied"}}):
            self.body = body
            self.assertIsNone(fresh_text_count(b"candidate"))

    def test_unlocated_and_low_confidence_detections_are_not_dropped(self):
        self.body = {"TextDetections": [{"DetectedText": "10.5", "Confidence": 12}, {}]}
        self.assertEqual(fresh_text_count(b"candidate"), 2)

    def test_unconfigured_unopened_and_oversized_do_not_call(self):
        for name, value in (("is_configured", False), ("unopened", True), ("_fits_as_is", False)):
            with patch.object(self.provider, name, lambda *args: value):
                self.assertIsNone(fresh_text_count(b"candidate"))
        self.assertEqual(self.sent, [])

    def test_only_explicit_no_text_error_is_zero(self):
        for code, expected in (("FailedOperation.ImageNoText", 0), ("AuthFailure", None)):
            exc = RuntimeError("private error")
            exc.code = code
            with patch.object(self.provider, "_call", side_effect=exc):
                self.assertEqual(fresh_text_count(b"candidate"), expected)

    def test_timeout_and_bad_input_remain_unmeasured(self):
        with patch.object(self.provider, "_call", side_effect=TimeoutError):
            self.assertIsNone(fresh_text_count(b"candidate"))
        for raw in (None, "url", b"", bytearray(b"x")):
            self.assertIsNone(fresh_text_count(raw))

    def test_initial_candidate_measurement_keeps_ambiguous_detections(self):
        from src.services import image_edit as IE, oneshot_ops as O, rep_auto_clean as R
        self.body = {"TextDetections": [{"DetectedText": "logo", "Confidence": 12}, {}]}
        extra = {"images": ["https://example.test/source.png"]}
        with patch.object(IE, "work_bytes", return_value=(b"source bytes", "")):
            counts = R.measure(extra, [0])
        self.assertEqual(counts, {0: 2})
        self.assertEqual(O.pick_rep(counts), -1)
        self.assertEqual(self.sent, [b"source bytes"])

    def test_initial_candidate_missing_response_is_not_selected(self):
        from src.services import image_edit as IE, oneshot_ops as O
        for body, expected in (({}, None), ({"TextDetections": None}, None),
                               ({"TextDetections": []}, 0)):
            self.body = body
            with patch.object(IE, "work_bytes", return_value=(b"source bytes", "")):
                n, why = O._ocr_box_count("https://example.test/source.png")
            self.assertEqual(n, expected)
            self.assertEqual(bool(why), expected is None)
            self.assertEqual(O.pick_rep({0: n}), 0 if expected == 0 else -1)

    def test_initial_download_failure_does_not_call_provider(self):
        from src.services import image_edit as IE, oneshot_ops as O
        with patch.object(IE, "work_bytes", return_value=(None, "download failed")):
            self.assertEqual(O._ocr_box_count("https://example.test/missing"),
                             (None, "download failed"))
        self.assertEqual(self.sent, [])

    def test_selection_requires_integer_zero_and_valid_index(self):
        from src.services.oneshot_ops import pick_rep
        for invalid in (False, 0.0, "0", None, -1):
            self.assertEqual(pick_rep({0: invalid}), -1)
            self.assertEqual(pick_rep({0: invalid, 1: 0}, prefer=0), 1)
        self.assertEqual(pick_rep({"0": 0, -1: 0, 2: 0}), 2)
        self.assertEqual(pick_rep({False: 0}), -1)


if __name__ == "__main__":
    unittest.main()
