"""F34-2b 계약 — 등록에 나가는 **모든** 장이 마켓이 가져갈 주소를 갖는다.

## 오너 실측 (2026-09-19 카나리 2차, 캡처 4장)

| 화면 | 말한 것 |
|---|---|
| 진단 표 | 갤러리 5행 · **상세 행 0** · **남은 장 0** |
| 등록 결과 | **상세 1번째 — 우리 서버 주소** 로 막힘 |

둘 다 맞는 말을 하면서 서로를 반박했다. F34-2와 **같은 병의 다른 갈래**다.

## 코드로 확정한 것 (「후보다 — 코드로 확정하라」)

1. **그 장은 번역된 적이 없는 원본이다.** 번역본이 없으니 `images_ko`에 항목이 없고,
   항목이 없으니 `image_ko_blobs`에 행이 없고, 행이 없으니 **백필도 진단도 못 본다.**
   진단은 `effective_plan`에서 `translatable or gone`만 남겼다 — 원본은 둘 다 아니다.
   「남은 장」은 `pending_cdn`(= blob 표에서 `cdn_url`이 빈 행)이라 **분모에 아예 없었다.**

2. **왜 그 원본이 「우리 서버 주소」로 읽혔나.**
   `image_reachability.is_internal()`은 **스킴이나 호스트가 없으면 우리 주소로 친다**
   (`src/services/image_reachability.py`). 그리고 확장은 `data-src`·`srcset` **원문**을
   절대화 없이 보낸다(`content_script.js:239`의 `im.getAttribute("data-src")` —
   브라우저가 절대화해 주는 `im.src`와 다르다). 타오바오·1688·Temu가 흔히 쓰는
   `//img.example.com/a.jpg`가 **스킴 없는 채로** 초안에 박힌다.

   → **메시지는 정확하지 않지만 판정은 옳다.** 마켓은 그 주소를 못 연다.
   **게이트는 손대지 않는다**(오너 지시). 고칠 곳은 「원본도 CDN에 있어야 한다」다.

> ★★★ **저장소를 순회하면 저장소에 없는 장은 영원히 안 보인다.**
> 세어야 하는 분모는 **등록이 보내는 집합**이다.
> (e.tb.cn 규칙: 못 한다는 결론도 **측정 범위**를 함께 적는다.)

라이브 호출 0 · Cloudinary 호출 0 — 전부 목이되, **재는 것은 우리가 내보내는 주소**다.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

SUPPLIER = "//img.example.com/detail-1.jpg"          # 스킴 없는 원본(실측된 모양)
CDN = "https://res.cloudinary.com/x/image/upload/v1/orig.jpg"


def _extra(detail_originals=(SUPPLIER,), gallery_originals=("https://ok.example/g1.jpg",)):
    return {"images": list(gallery_originals), "detail_images": list(detail_originals)}


# ---------------------------------------------------------------------------
# ① 등록에 나가는 집합을 순회한다 — blob 유무와 무관하게
# ---------------------------------------------------------------------------

def test_an_untranslated_original_still_appears_in_the_set():
    """★★ **F34-2b의 판정 지점** — 번역된 적 없는 상세 원본도 **행으로 나온다**."""
    from src.services import image_translate_store as S
    pages = S.outbound_pages(_extra())
    detail = [p for p in pages if p["kind"] == "detail"]
    assert len(detail) == 1, pages
    assert detail[0]["source"] == "original"
    assert detail[0]["url"] == SUPPLIER


def test_the_set_says_which_pages_the_market_cannot_fetch():
    """★ 스킴 없는 주소는 **마켓이 못 가져간다** — 그 사실이 집합에 실린다."""
    from src.services import image_translate_store as S
    pages = S.outbound_pages(_extra())
    by_kind = {p["kind"]: p for p in pages}
    assert by_kind["detail"]["outward"] is False, "스킴 없는 원본을 통과로 읽는다"
    assert by_kind["gallery"]["outward"] is True


def test_outbound_missing_is_the_backfill_worklist():
    from src.services import image_translate_store as S
    missing = S.outbound_missing(_extra())
    assert [(p["kind"], p["idx"]) for p in missing] == [("detail", 0)]


def test_a_fully_external_item_has_nothing_missing():
    """다 열리는 항목은 **아무것도 안 시킨다** — 멱등·비용."""
    from src.services import image_translate_store as S
    ex = _extra(detail_originals=("https://ok.example/d1.jpg",))
    assert S.outbound_missing(ex) == []


# ---------------------------------------------------------------------------
# ② 원본 CDN 사본이 있으면 그게 나간다
# ---------------------------------------------------------------------------

def test_the_origin_cdn_copy_goes_out_instead():
    """★★ 원본 배열은 그대로 두고(**공급사 주소는 재번역·감시가 쓴다**) 옆에 적은 주소가 나간다."""
    from src.services import image_translate_store as S
    ex = S.set_origin_cdn(_extra(), "detail", 0, CDN)
    assert ex["detail_images"] == [SUPPLIER], "공급사 원본을 덮었다"
    assert S.effective_images(ex, kind="detail") == [CDN]
    assert S.outbound_missing(ex) == []


def test_a_translation_still_wins_over_the_origin_copy():
    """번역본이 있으면 번역본이다 — 이 판이 D2의 규칙을 뒤집지 않는다."""
    from src.services import image_translate_store as S
    ex = S.set_origin_cdn(_extra(), "detail", 0, CDN)
    ex["detail_images_ko"] = [{"idx": 0, "url": "https://cdn.example/ko.jpg",
                               "status": "done", "use": True}]
    assert S.effective_images(ex, kind="detail") == ["https://cdn.example/ko.jpg"]


def test_a_vanished_translation_falls_back_to_the_origin_copy():
    """번역본이 사라진 장은 원본으로 — 그 원본도 **CDN 사본**이 있으면 그걸 쓴다(F27 연장)."""
    from src.services import image_translate_store as S
    ex = S.set_origin_cdn(_extra(), "detail", 0, CDN)
    ex["detail_images_ko"] = [{"idx": 0, "url": "/seller/collect/image-ko/i/0",
                               "status": "done", "use": True}]
    with patch("src.db.image_ko_blobs_pg.status_for_item",
               return_value={("detail", 0): {"bytes": 0, "cdn_url": ""}}):
        out = S.effective_images(ex, kind="detail", item_id="i")
    assert out == [CDN]


def test_the_screen_plan_and_registration_agree():
    """화면과 등록이 **같은 주소**를 말한다 — 갈리면 또 F34-2다."""
    from src.services import image_translate_store as S
    ex = S.set_origin_cdn(_extra(), "detail", 0, CDN)
    plan = S.effective_plan(ex, kind="detail")
    assert plan[0]["url"] == S.effective_images(ex, kind="detail")[0] == CDN
    assert plan[0]["origin_cdn"] == CDN


# ---------------------------------------------------------------------------
# ③ 주소 펴기 — 지어내지 않는다
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expect", [
    ("//img.example.com/a.jpg", "https://img.example.com/a.jpg"),
    ("https://img.example.com/a.jpg", "https://img.example.com/a.jpg"),
    ("http://img.example.com/a.jpg", "http://img.example.com/a.jpg"),
    ("/img/a.jpg", ""),                       # 어느 호스트인지 모른다 → 지어내지 않는다
    ("a.jpg", ""),
    ("", ""),
])
def test_only_scheme_relative_urls_are_expanded(raw, expect):
    """★ `//`만 편다. 사이트 상대 경로는 **호스트를 지어내지 않는다**."""
    from src.services.image_cdn_backfill import normalize_outward
    assert normalize_outward(raw) == expect


def test_an_unexpandable_original_reports_why():
    """못 펴면 **왜 못 폈는지** 말한다 — 조용히 건너뛰면 또 안 보인다.

    ※ F34-2d: 문장이 바뀌었다. 상대 경로는 이제 **그 상품의 소스 페이지**로 푼다 —
      못 푸는 건 그 기준조차 없을 때뿐이다. 계약은 **의도**(사유를 말한다)를 재고,
      상대 경로 해석 자체는 `test_f34_2cd_…`가 정본이다.
    """
    from src.services.image_cdn_backfill import fetch_original
    raw, err = fetch_original("/img/a.jpg")
    assert raw == b"" and "소스 페이지 주소도 없습니다" in err, err


def test_a_supplier_error_is_reported_verbatim():
    from src.services.image_cdn_backfill import fetch_original

    class _R:
        status_code = 403
        content = b""

    with patch("requests.get", return_value=_R()):
        raw, err = fetch_original(SUPPLIER)
    assert raw == b"" and "403" in err


# ---------------------------------------------------------------------------
# ④ 백필이 원본을 올린다
# ---------------------------------------------------------------------------

def _item(extra):
    return {"id": "it-1", "title": "수행방패", "extra_json": json.dumps(extra)}


def test_the_backfill_uploads_an_untranslated_original():
    """★★ 「지금 올리기」가 **상세 원본**을 Cloudinary에 올리고 초안에 주소를 적는다."""
    from src.services import image_cdn_backfill as BF
    saved = {}

    def _update(item_id, **fields):
        saved.update(json.loads(fields["extra_json"]))
        return True

    with patch.object(BF, "cdn_ready", return_value=True), \
         patch.object(BF, "fetch_original", return_value=(b"jpegbytes", "")), \
         patch.object(BF, "_upload", return_value=(CDN, "")), \
         patch("src.seller_console.collect_history_store.update", side_effect=_update):
        out = BF.run_originals([_item(_extra())])

    assert out["uploaded"] == 1 and out["failed"] == 0, out
    assert saved["detail_images_cdn"] == {"0": CDN}
    assert saved["detail_images"] == [SUPPLIER], "공급사 원본을 덮었다"


def test_the_backfill_leaves_reachable_pages_alone():
    """이미 열리는 장은 **안 올린다** — 장당 비용이다."""
    from src.services import image_cdn_backfill as BF
    with patch.object(BF, "cdn_ready", return_value=True), \
         patch.object(BF, "fetch_original") as fetch:
        out = BF.run_originals([_item(_extra(detail_originals=("https://ok.example/d.jpg",)))])
    assert out["uploaded"] == 0 and fetch.call_count == 0


def test_a_fetch_failure_is_counted_and_explained():
    """★ 공급사에서 못 받아 오면 **실패로 센다** — 조용히 0건으로 넘기지 않는다."""
    from src.services import image_cdn_backfill as BF
    with patch.object(BF, "cdn_ready", return_value=True), \
         patch.object(BF, "fetch_original", return_value=(b"", "공급사 응답 HTTP 403")):
        out = BF.run_originals([_item(_extra())])
    assert out["failed"] == 1 and out["uploaded"] == 0
    assert "403" in out["results"][0]["error"]


def test_a_write_failure_after_upload_is_not_a_clean_success():
    """★ 올렸는데 초안에 못 적었으면 **반쪽 성공**이다 — F34-2가 가르친 것."""
    from src.services import image_cdn_backfill as BF
    with patch.object(BF, "cdn_ready", return_value=True), \
         patch.object(BF, "fetch_original", return_value=(b"b", "")), \
         patch.object(BF, "_upload", return_value=(CDN, "")), \
         patch("src.seller_console.collect_history_store.update", return_value=False):
        out = BF.run_originals([_item(_extra())])
    assert out["failed"] >= 1
    assert any("적지 못했" in r["error"] for r in out["results"]), out["results"]


def test_no_cdn_means_it_says_so_rather_than_reporting_zero():
    from src.services import image_cdn_backfill as BF
    with patch.object(BF, "cdn_ready", return_value=False):
        out = BF.run_originals([_item(_extra())])
    assert out["ok"] is False and "CLOUDINARY" in out["reason"]


# ---------------------------------------------------------------------------
# ⑤ 화면 — 분모와 표기
# ---------------------------------------------------------------------------

def test_the_count_uses_the_outbound_set_not_the_blob_table():
    """★★ 「남은 장」의 **분모**가 등록에 나가는 집합이다(오너 실측의 0이 여기서 났다)."""
    import inspect
    from src.seller_console import views
    src = inspect.getsource(views.image_storage_diag)
    assert 'pending=sum(r["blocked"] for r in rows)' in src
    assert "pending_blobs=" in src, "번역본 대기 수치를 잃어버렸다"


def test_the_diagnostics_iterates_the_outbound_set():
    import inspect
    from src.seller_console import views
    src = inspect.getsource(views.image_storage_diag)
    assert "store.outbound_pages(" in src
    assert 'if not p["translatable"] and not p.get("gone")' not in src, "번역본만 남기던 필터가 남아 있다"


def test_the_table_marks_pages_absent_from_the_store():
    """★ 「없음」과 **「저장소에 없음」**은 다른 사건이다 — 화면이 구분한다."""
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1]
           / "src/seller_console/templates/image_storage_diag.html").read_text(encoding="utf-8")
    assert "저장소에 없음" in tpl and "p.in_store" in tpl
    assert "마켓이 못 가져감" in tpl and "p.outward" in tpl
    assert "등록에 나가는 전 장 기준" in tpl, "측정 범위를 화면에 안 적었다"


def test_the_backfill_route_runs_originals_too():
    import inspect
    from src.seller_console import views
    src = inspect.getsource(views.image_storage_backfill_now)
    assert "run_originals" in src
    assert '"uploaded"' in src, "합계가 한쪽만 센다"


def test_the_gate_is_still_fail_closed():
    """★ 오너 지시: **게이트는 그대로.** 사본이 없으면 여전히 막는다."""
    import inspect
    from src.seller_console import views
    from src.services import image_reachability as R
    from src.services import image_translate_store as S

    out = S.effective_images(_extra(), kind="detail")
    assert out == [SUPPLIER]
    assert R.check_all(out)["ok"] is False
    src = inspect.getsource(views.collect_upload)
    assert '"step": "도달성 확인"' in src and "409" in src
