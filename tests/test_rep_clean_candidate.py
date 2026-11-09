import copy
import hashlib
import unittest

from src.services.rep_clean_candidate import crop_candidate


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.raw = b"source raster contract double"
        self.protection = {"reviewed_complete": True, "version": "translated",
                           "sha256": hashlib.sha256(self.raw).hexdigest(),
                           "regions": [[20, 30, 60, 80]]}
        self.calls = []

    def worker(self, fn, raw, texts, protected, **kwargs):
        self.calls.append((fn.__name__, raw, texts, protected, kwargs))
        return {"ok": True, "bytes": b"rendered PNG contract double"}

    def call(self, ocr=lambda _: 0, **kw):
        return crop_candidate(self.raw, [[0, 0, 80, 20]], self.protection,
                              version="translated", ocr=ocr, worker=kw.get("worker", self.worker))

    def test_candidate_is_rendered_then_freshly_measured_without_mutating_evidence(self):
        saved = copy.deepcopy(self.protection)
        observed = []
        out = self.call(ocr=lambda raw: observed.append(raw) or 0)
        self.assertTrue(out["ok"])
        self.assertEqual(self.calls[0][0], "render_edge_crop")
        self.assertEqual(self.calls[0][-1]["_timeout"], 30.0)
        self.assertEqual(observed, [out["bytes"]])
        self.assertEqual(self.protection, saved)
        self.assertFalse(out["reuse_source_boxes"])

    def test_stale_bytes_or_version_never_reach_worker(self):
        for field in ("sha256", "version"):
            old = self.protection[field]
            self.protection[field] = "stale"
            self.assertEqual(self.call()["why"], "product_protection_stale")
            self.protection[field] = old
        self.assertEqual(self.calls, [])

    def test_missing_protection_or_ocr_never_reaches_worker(self):
        self.assertEqual(self.call(ocr=None)["why"], "ocr_unavailable")
        self.protection["reviewed_complete"] = False
        self.assertEqual(self.call()["why"], "product_protection_unverified")
        self.assertEqual(self.calls, [])

    def test_ocr_failures_do_not_leak_an_accepted_candidate(self):
        for count in (None, False, 0.0, "0", -1, 3):
            with self.subTest(count=count):
                out = self.call(ocr=lambda _, n=count: n)
                self.assertFalse(out["ok"])
                self.assertNotIn("bytes", out)
        def broken(_):
            raise RuntimeError("private provider response")
        self.assertEqual(self.call(ocr=broken), {"ok": False, "why": "fresh_ocr_failed"})

    def test_worker_rejection_prevents_ocr(self):
        def never(_):
            self.fail("OCR must not run for a rejected render")
        out = self.call(ocr=never, worker=lambda *a, **kw: {"ok": False, "why": "crop_overlaps_product"})
        self.assertEqual(out["why"], "crop_overlaps_product")

    def test_worker_exception_is_a_hold(self):
        def broken(*a, **kw):
            raise TimeoutError()
        self.assertEqual(self.call(worker=broken)["why"], "crop_worker_failed")


if __name__ == "__main__":
    unittest.main()
