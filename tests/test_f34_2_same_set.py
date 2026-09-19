"""F34-2 계약 — 진단이 세는 집합 = 등록이 보내는 집합.

## 오너 실측 (2026-09-19 카나리 1차)

진단 화면: **「남은 장 0」**. 같은 항목을 등록: **「상세 1번째 — 우리 서버 주소」**로 막힘.
둘 다 맞는 말을 하면서 서로를 반박했다.

## 오너 가설과 실제 (「후보다 — 코드로 확정하라」)

| | |
|---|---|
| 오너 가설 | 갤러리만 세고 **상세는 집합 밖** |
| 코드 실측 | **아니다.** 진단(`effective_plan`)·백필(`pending_cdn`)·등록(`effective_images`)은 |
| | 셋 다 `gallery`·`detail`을 **같이** 돈다 |

진짜로 갈린 것은 **kind가 아니라 표**였다.

| 보는 곳 | 읽는 표 |
|---|---|
| 진단 「남은 장」·백필 | `image_ko_blobs` — **`cdn_url`의 정본** |
| 등록에 나갈 배열 | 초안 `extra_json`의 `images_ko[].url` — **사본** |

백필은 올린 뒤 `_point_entry_at_cdn`으로 사본을 맞췄는데, **그 반환값을 버렸다.**
못 고쳐도 「올림」으로 셌다. 그러면 blob엔 `cdn_url`이 있어 **대기 0**이고,
초안은 우리 주소라 **등록은 막힌다.** 정확히 오너가 본 두 문장이다.

> ★★ **사본을 맞추려 들지 말고 정본을 읽는다.**

## 손대지 않는 것

등록 게이트의 **fail-closed**(우리 주소는 안 내보낸다)는 그대로다. 오너 지시이기도 하고,
그게 카나리를 살린 규율이다. 바뀌는 건 **이미 외부에 있는 장을 못 찾던 것**뿐이다.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

CDN = "https://res.cloudinary.com/x/image/upload/v1/ko.jpg"
OURS = "/seller/collect/image-ko/it-1/0?kind=detail"


def _extra(kind="detail", url=OURS):
    ko = "images_ko" if kind == "gallery" else "detail_images_ko"
    src = "images" if kind == "gallery" else "detail_images"
    return {src: ["https://sup.example/a.jpg"],
            ko: [{"idx": 0, "url": url, "status": "done", "use": True}]}


# ---------------------------------------------------------------------------
# ① 정본을 읽는다 — 초안이 낡아도 등록은 CDN 주소로 나간다
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["gallery", "detail"])
def test_registration_uses_the_cdn_url_when_the_draft_is_stale(kind):
    """★★ **F34-2의 판정 지점** — blob에 CDN 주소가 있으면 그게 나간다."""
    from src.services import image_translate_store as S
    with patch("src.db.image_ko_blobs_pg.status_for_item",
               return_value={(kind, 0): {"bytes": 1234, "cdn_url": CDN}}):
        out = S.effective_images(_extra(kind), kind=kind, item_id="it-1")
    assert out == [CDN], out


@pytest.mark.parametrize("kind", ["gallery", "detail"])
def test_the_screen_plan_agrees_with_registration(kind):
    """화면(썸네일 탭)이 **등록에 나갈 그 주소**를 보여 준다 — 갈리면 또 같은 병이다."""
    from src.services import image_translate_store as S
    with patch("src.db.image_ko_blobs_pg.status_for_item",
               return_value={(kind, 0): {"bytes": 1234, "cdn_url": CDN}}):
        plan = S.effective_plan(_extra(kind), kind=kind, item_id="it-1")
        eff = S.effective_images(_extra(kind), kind=kind, item_id="it-1")
    assert plan[0]["url"] == eff[0] == CDN
    assert plan[0]["gone"] is False, "CDN에 멀쩡히 있는 장을 사라졌다고 한다"


def test_without_a_cdn_copy_it_still_blocks():
    """★ 게이트는 그대로다 — CDN 사본이 없으면 우리 주소는 여전히 우리 주소다."""
    from src.services import image_reachability as R
    from src.services import image_translate_store as S
    with patch("src.db.image_ko_blobs_pg.status_for_item",
               return_value={("detail", 0): {"bytes": 1234, "cdn_url": ""}}):
        out = S.effective_images(_extra("detail"), kind="detail", item_id="it-1")
    assert out == [OURS], "우리 주소를 조용히 원본으로 바꾸거나 통과시키면 안 된다"
    assert R.check_all(out)["ok"] is False, "fail-closed 게이트가 풀렸다"


def test_a_missing_blob_still_falls_back_to_the_original():
    """바이트도 CDN도 없으면 원본으로 — F27의 판정이 살아 있다(무회귀)."""
    from src.services import image_translate_store as S
    with patch("src.db.image_ko_blobs_pg.status_for_item",
               return_value={("detail", 0): {"bytes": 0, "cdn_url": ""}}):
        out = S.effective_images(_extra("detail"), kind="detail", item_id="it-1")
    assert out == ["https://sup.example/a.jpg"]


def test_an_external_url_in_the_draft_is_untouched():
    """초안이 이미 외부 주소면 그대로 쓴다 — 정본 조회가 멀쩡한 값을 덮지 않는다."""
    from src.services import image_translate_store as S
    other = "https://cdn.example/already.jpg"
    with patch("src.db.image_ko_blobs_pg.status_for_item",
               return_value={("detail", 0): {"bytes": 1, "cdn_url": CDN}}):
        out = S.effective_images(_extra("detail", url=other), kind="detail", item_id="it-1")
    assert out == [other]


def test_not_asking_means_not_judging():
    """`item_id` 없이 부르면 적힌 대로 간다 — 못 물어본 것으로 판단하지 않는다(F27 규율)."""
    from src.services import image_translate_store as S
    assert S.effective_images(_extra("detail"), kind="detail") == [OURS]


# ---------------------------------------------------------------------------
# ② 백필이 반쪽 성공을 조용히 넘기지 않는다
# ---------------------------------------------------------------------------

def test_a_failed_repoint_is_recorded_not_swallowed():
    """★★ 올리고 초안을 못 고쳤으면 **그 사실이 남는다** — 예전엔 반환값을 버렸다."""
    from src.services import image_cdn_backfill as BF
    notes = {}

    def _set_cdn(item_id, idx, url, *, kind="gallery", error=""):
        notes["url"], notes["error"] = url, error
        return True

    with patch.object(BF, "cdn_ready", return_value=True), \
         patch.object(BF, "_upload", return_value=(CDN, "")), \
         patch.object(BF, "_point_entry_at_cdn", return_value=False), \
         patch("src.db.image_ko_blobs_pg.pending_cdn",
               return_value=[{"item_id": "it-1", "idx": 0, "kind": "detail"}]), \
         patch("src.db.image_ko_blobs_pg.get_cdn", return_value=""), \
         patch("src.db.image_ko_blobs_pg.get", return_value=(b"bytes", "image/jpeg")), \
         patch("src.db.image_ko_blobs_pg.set_cdn", side_effect=_set_cdn):
        out = BF.run()

    assert notes["url"] == CDN, "CDN 주소는 그대로 남아야 한다(다시 올리지 않는다)"
    assert "초안" in notes["error"], notes
    row = out["results"][0]
    assert row["repointed"] is False and row["error"], row


def test_a_good_repoint_leaves_no_error():
    from src.services import image_cdn_backfill as BF
    with patch.object(BF, "cdn_ready", return_value=True), \
         patch.object(BF, "_upload", return_value=(CDN, "")), \
         patch.object(BF, "_point_entry_at_cdn", return_value=True), \
         patch("src.db.image_ko_blobs_pg.pending_cdn",
               return_value=[{"item_id": "it-1", "idx": 0, "kind": "detail"}]), \
         patch("src.db.image_ko_blobs_pg.get_cdn", return_value=""), \
         patch("src.db.image_ko_blobs_pg.get", return_value=(b"bytes", "image/jpeg")), \
         patch("src.db.image_ko_blobs_pg.set_cdn", return_value=True):
        out = BF.run()
    assert out["uploaded"] == 1 and out["results"][0]["error"] == ""


def test_the_backfill_carries_detail_pages():
    """★ 오너 가설의 검산 — 백필은 **상세도 집어 든다**(kind를 그대로 들고 간다)."""
    from src.services import image_cdn_backfill as BF
    seen = []
    with patch.object(BF, "cdn_ready", return_value=True), \
         patch.object(BF, "_upload", return_value=(CDN, "")), \
         patch.object(BF, "_point_entry_at_cdn", side_effect=lambda i, x, k, u: seen.append(k) or True), \
         patch("src.db.image_ko_blobs_pg.pending_cdn",
               return_value=[{"item_id": "it-1", "idx": 0, "kind": "gallery"},
                             {"item_id": "it-1", "idx": 0, "kind": "detail"}]), \
         patch("src.db.image_ko_blobs_pg.get_cdn", return_value=""), \
         patch("src.db.image_ko_blobs_pg.get", return_value=(b"b", "image/jpeg")), \
         patch("src.db.image_ko_blobs_pg.set_cdn", return_value=True):
        BF.run()
    assert seen == ["gallery", "detail"], seen


# ---------------------------------------------------------------------------
# ③ 진단 표가 상세를 같은 칸으로 보여 주고, 갈린 장을 말한다
# ---------------------------------------------------------------------------

def test_the_diagnostics_walks_both_kinds():
    """진단이 두 kind를 같은 표로 돈다 — 주석이 아니라 코드로 잰다."""
    import ast
    import inspect
    from src.seller_console import views

    tree = ast.parse(inspect.getsource(views.image_storage_diag))
    kinds = [n for n in ast.walk(tree) if isinstance(n, ast.Tuple)
             and {getattr(e, "value", None) for e in n.elts} == {"gallery", "detail"}]
    assert kinds, "진단이 상세를 같이 돌지 않는다"


def test_the_diagnostics_marks_the_drifted_page():
    """★ 「CDN엔 있는데 초안은 우리 주소」를 **화면이 말한다**(추측으로 풀지 않게)."""
    import inspect
    from pathlib import Path
    from src.seller_console import views

    assert '"drifted"' in inspect.getsource(views.image_storage_diag)
    tpl = (Path(__file__).resolve().parents[1]
           / "src/seller_console/templates/image_storage_diag.html").read_text(encoding="utf-8")
    assert "p.drifted" in tpl and "초안 미갱신" in tpl


def test_the_registration_gate_is_still_fail_closed():
    """★ 오너 지시: **게이트는 손대지 않는다.** 409로 막는 자리가 그대로 있다."""
    import inspect
    from src.seller_console import views
    src = inspect.getsource(views.collect_upload)
    assert '"step": "도달성 확인"' in src and "409" in src
    assert "unreachable" in src
