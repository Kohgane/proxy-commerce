# H-rep2 crop prototype — NOT production acceptance

Status: draft, not wired into rep_auto_clean. No operation was queued and no image
was uploaded to a marketplace or Cloudinary. This is a local raster experiment.

## Before and after

Input: existing repository fixture `docs/screens/patrol148/before-d5af2185-p2.jpg`
at main `362f407391f470c525729da1f5bdbd57bdc74efb` (1440 × 1440).
This is the previously captured displayed image, not a newly fetched source photo.

![Before](../patrol148/before-d5af2185-p2.jpg)
![Crop prototype, JPEG preview](after-crop-d5af2185-preview.jpg)

Manually reviewed rectangles on this fixture (NOT Tencent OCR output):

- Text regions: [170,95,1260,365], [1150,1360,1390,1420].
- Protected lamp: [570,520,770,850].
- Crop: [0,369,1440,1356]; retained image: 1440 × 987.
- Canvas: 1440 × 1440, white padding top=226; source-to-output offset=[0,-143].
- Test compares every retained decoded pixel, including the protected lamp,
  against the lossless PNG render: equal. The JPEG here is a preview only.
- Lossless PNG SHA256: f334e716a9bb8f956187d2465f67e491bb5cc6877aceee3c55bff5a57b8891c6.
- Book-spine text remains. Fresh Tencent OCR was NOT run; zero-box acceptance is
  NOT claimed. Product protection annotations are manual and fixture-specific.

SPORTLINK fixture `before-a3a35e92-p4.jpg` has lettering over the merchandise
and on the watch face. Edge-only cropping is rejected in the new test. It must
not be labelled a safe crop merely because promotional lines are near an edge.

## Implemented and checked

`rep_clean_geometry` provides crop planning, a lossless worker-only crop renderer,
and a symmetric variance ratio check. Rejects missing product regions, invalid
coordinates, central text, protected-region overlap, small retained images,
unoriented EXIF, animation and unsupported color modes. Imports no image
libraries at module load. Requires new OCR coordinates after cropping.

16 standalone unittest cases passed (0 skipped), including the repository lamp
photo and exact pixel checks. Command:
`python -m unittest discover -s tests -p test_rep_clean_geometry.py -v`.

## Still required before merge

- Wire the renderer through render_worker, without importing cv2 into the app worker.
- Establish trustworthy product-protection regions tied to the exact selected
  image version; do not treat OCR-empty space as proof of product absence.
- Add inpaint candidate rendering and actual local variance sampling. The scalar
  variance check alone is not a measured smear detector.
- Preserve quota accounting, candidate fallback, existing outbound version,
  original images, non-Coupang payloads and edit-coordinate isolation.
- Fresh OCR must measure the rendered output, with failure preserving hold.
- Add integration tests and compare actual candidate outcomes before/after.
- Full suite and all five required CI gates, plus repository review checklist.
- Do not automatically regenerate existing production edits or refresh listings.

## Pixel quality follow-up (2026-10-30)

Added `measure_inpaint_quality`: same-frame RGB inputs, per-channel variance of each edited rectangle plus a 2–12px context rim, exact protection-pixel preservation, and no changes outside the declared edit bounds. Unknown protection, product overlap, changed coordinates or zero variance reject the candidate. Measuring only the unchanged exterior ring cannot detect a flattened rectangle, so this measurement includes the edited interior. This remains a numerical gate, not proof of OCR completion or semantic product safety.

Targeted unittest now **22 passed, 0 skipped**. Six new cases use controlled raster arrays (not live inpaint evidence). No automatic pipeline wiring, product detector, or Tencent call was added. `image_edit.plan` supplies OCR/prop boxes and a version, but no product-protection regions. Production integration and the original merge checklist remain incomplete.
