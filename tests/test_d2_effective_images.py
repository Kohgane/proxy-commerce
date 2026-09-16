"""D2 계약 — 번역본이 실제로 상품 이미지가 된다.

## 실측 (오너 2026-09-16)

수행방패 5장 번역 완료(0.8~1.5s/장). 그런데 그 번역본은 **서랍 「이미지 번역」 탭에만** 있었다.
썸네일 탭도, 등록 흐름도 원본만 봤다 — **돈을 써서 만든 것이 아무 데도 안 나갔다.**

## 그래서 재는 것

  ① **저장소** — 로컬 파일 금지(배포에 사라진다) · DB · CDN, 셋뿐.
  ② **effective** — 토글이 반영된 배열이 나온다. 원본은 그대로 남는다.
  ③ **등록 파이프가 그걸 읽는다** — 서랍이 한국어인데 마켓이 중국어면 D2가 한 일이 없다.

라이브 호출 0 — 공급사도 소싱처도 부르지 않는다(장당 과금).
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_ko_blobs_pg as blobs
    blobs.reset_for_tests()
    yield
    blobs.reset_for_tests()


def _extra(**kw):
    base = {
        "images": ["https://o/0.jpg", "https://o/1.jpg", "https://o/2.jpg"],
        # D2b: 등록에 나가는 주소는 **외부에서 열리는 것**이어야 한다(CDN).
        #   우리 서버 주소(`/seller/…`)는 로그인 게이트 뒤라 마켓이 못 가져간다.
        "images_ko": [
            {"idx": 0, "status": "done", "url": "https://res.cloudinary.com/x/0.jpg",
             "use": True, "warn": [], "dense": False},
            {"idx": 1, "status": "failed", "error_message": "실패"},
            {"idx": 2, "status": "done", "url": "https://res.cloudinary.com/x/2.jpg",
             "use": False, "warn": ["최고"], "dense": True},
        ],
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# ① 저장소 — 로컬 파일은 없다
# ---------------------------------------------------------------------------

def test_local_file_storage_is_gone():
    """★ 배포에 사라지는 자리를 「저장했다」고 부르지 않는다.

    D1은 `data/images_ko/<item>/<idx>.jpg`에 뒀다. Render는 배포마다 그 디스크를 버린다 —
    볼트 [[Render tmp 휘발]]에 이미 적힌 지뢰를 「임시」라는 이유로 다시 밟았다.
    **장당 과금으로 만든 결과물이 사라지면 그 돈을 다시 쓴다.**
    """
    src = (ROOT / "src/services/image_translate_store.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith(("#", ">", "·")))
    assert "IMAGES_KO_DIR" not in code
    assert "write_bytes" not in code, "다시 로컬 파일에 쓰고 있다"
    assert '"file"' not in code, "`stored_by=\"file\"` 갈래가 남아 있다"


def test_storage_backends_are_exactly_three():
    """갈래는 cdn · db · ""(못 뒀다) 셋뿐이다."""
    from src.services import image_translate_store as store
    with patch("src.media.image_pipeline._cloudinary_configured", return_value=True), \
         patch("src.media.image_pipeline._CDN_UPLOAD_ENABLED", True):
        assert store.storage_backend() == "cdn"
    with patch("src.media.image_pipeline._cloudinary_configured", return_value=False), \
         patch("src.db.pg.pg_enabled", return_value=True):
        assert store.storage_backend() == "db"
    with patch("src.media.image_pipeline._cloudinary_configured", return_value=False), \
         patch("src.db.pg.pg_enabled", return_value=False):
        assert store.storage_backend() == ""


def test_bytes_round_trip_through_the_blob_store():
    import base64
    from src.services import image_translate_store as store
    raw = b"\xff\xd8\xff-hello"
    with patch.object(store, "_store_via_cdn", return_value=("", "")):   # F31: (url, error)
        placed = store.store_translated("i1", 0, base64.b64encode(raw).decode(),
                                        seller_id="u1")
    assert placed["stored_by"] == "db"
    assert placed["url"] == "/seller/collect/image-ko/i1/0"
    assert store.read_translated("i1", 0) == raw


def test_detail_images_have_their_own_slot():
    """D2-4: 상세 이미지도 같은 구조다 — 갤러리 0번과 상세 0번이 서로를 덮으면 안 된다."""
    import base64
    from src.services import image_translate_store as store
    with patch.object(store, "_store_via_cdn", return_value=("", "")):   # F31: (url, error)
        store.store_translated("i1", 0, base64.b64encode(b"gal").decode())
        store.store_translated("i1", 0, base64.b64encode(b"det").decode(), kind="detail")
    assert store.read_translated("i1", 0) == b"gal"
    assert store.read_translated("i1", 0, kind="detail") == b"det"


def test_banner_only_when_it_is_true():
    """「저장소 미연결」은 **사실일 때만** 뜬다 — 늘 띄우면 아무도 안 읽는다."""
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "{% if not imgko_storage %}" in tpl
    assert "저장소 미연결" in tpl


def test_stage12_is_applied_at_boot():
    src = (ROOT / "src/db/pg.py").read_text(encoding="utf-8")
    assert "schema_stage12.sql" in src
    sql = (ROOT / "src/db/schema_stage12.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS image_ko_blobs" in sql
    assert "bytea" in sql


# ---------------------------------------------------------------------------
# ② effective — 토글이 반영되고, 원본은 남는다
# ---------------------------------------------------------------------------

def test_effective_uses_translation_only_where_it_is_on_and_done():
    from src.services.image_translate_store import effective_images
    eff = effective_images(_extra())
    assert eff == [
        "https://res.cloudinary.com/x/0.jpg",   # done + use
        "https://o/1.jpg",                 # failed → 원본
        "https://o/2.jpg",                 # done인데 use=False → 원본
    ]


def test_effective_keeps_order_and_count():
    """번역 안 된 장을 빼면 **상품에 구멍이 난다** — 장수와 순서는 원본 그대로다."""
    from src.services.image_translate_store import effective_images
    ex = _extra()
    assert len(effective_images(ex)) == len(ex["images"])


def test_originals_are_never_touched():
    """★★ 원본 `images`는 영구 보존이다 — 번역이 마음에 안 들 때 되돌릴 데가 있어야 한다."""
    from src.services.image_translate_store import effective_images, set_use_flags
    ex = _extra()
    before = list(ex["images"])
    effective_images(ex)
    ex["images_ko"] = set_use_flags(ex, {0: False, 2: True})
    effective_images(ex)
    assert ex["images"] == before


def test_use_cannot_be_turned_on_without_a_translation():
    """번역본이 없는 장은 켜지지 않는다 — 켜진 척하면 「켰는데 왜 원본이지」를 겪는다."""
    from src.services.image_translate_store import set_use_flags
    rows = set_use_flags(_extra(), {1: True})
    assert rows[1].get("use") is False


def test_live_originals_win_over_saved_ones():
    """사람이 서랍에서 방금 고친 목록이 등록에 나간다(저장된 옛 목록이 아니라)."""
    from src.services.image_translate_store import effective_images
    eff = effective_images(_extra(), originals=["https://new/0.jpg", "https://new/1.jpg"])
    assert eff == ["https://res.cloudinary.com/x/0.jpg", "https://new/1.jpg"]


def test_plan_tells_the_screen_what_goes_out():
    from src.services.image_translate_store import effective_plan
    plan = effective_plan(_extra())
    assert [p["source"] for p in plan] == ["translated", "original", "original"]
    assert plan[0]["translatable"] is True and plan[1]["translatable"] is False
    assert plan[2]["translatable"] is True and plan[2]["use"] is False
    assert plan[2]["warn"] == ["최고"] and plan[2]["dense"] is True


def test_summary_flags_only_pages_that_actually_go_out():
    """켜지지 않은 장의 금칙어로 사람을 세우지 않는다 — 그건 나가지 않는다."""
    from src.services.image_translate_store import effective_summary
    s = effective_summary(_extra())
    assert s["translated"] == 1 and s["original"] == 2
    assert s["warn_idx"] == [], "안 나가는 장 때문에 확인을 요구했다"

    ex = _extra()
    ex["images_ko"][2]["use"] = True
    s2 = effective_summary(ex)
    assert [w["idx"] for w in s2["warn_idx"]] == [2]
    assert [d["idx"] for d in s2["dense_idx"]] == [2]


def test_dense_is_measured_not_guessed():
    """「레이아웃 확인」은 공급사가 돌려준 **줄 수** 그대로다 — 임의 점수가 아니다."""
    from src.services import image_translate_store as store
    with patch.object(store, "_store_via_cdn", return_value=("", "")):   # F31: (url, error)
        e = store.build_entry(0, {"ok": True, "image_b64": "aW1n", "vendor": "t",
                                  "lines": [{}] * store.DENSE_TEXT_LINES}, item_id="i1")
    assert e["dense"] is True
    with patch.object(store, "_store_via_cdn", return_value=("", "")):   # F31: (url, error)
        e2 = store.build_entry(1, {"ok": True, "image_b64": "aW1n", "vendor": "t",
                                   "lines": [{}]}, item_id="i1")
    assert e2["dense"] is False


def test_a_fresh_translation_defaults_to_being_used():
    """번역한 장은 기본으로 쓴다 — 그러려고 번역했다(사람이 끌 수 있다)."""
    from src.services import image_translate_store as store
    with patch.object(store, "_store_via_cdn", return_value=("", "")):   # F31: (url, error)
        e = store.build_entry(0, {"ok": True, "image_b64": "aW1n", "vendor": "t"},
                              item_id="i1")
    assert e["use"] is True
    failed = store.build_entry(1, {"ok": False, "error_class": "X"}, item_id="i1")
    assert failed.get("use") is not True


# ---------------------------------------------------------------------------
# ③ 등록 파이프가 effective를 읽는다
# ---------------------------------------------------------------------------

def test_review_sheet_reads_effective():
    """검수표·카나리도 **등록에 나갈 배열**을 본다."""
    from src.pipeline.register_pipe import build_source_review_row
    draft = dict(_extra(), title="수행방패", price="100", currency="KRW")
    row = build_source_review_row(draft, url="https://item.taobao.com/item.htm?id=1")
    assert row["thumbnail"] == "https://res.cloudinary.com/x/0.jpg"
    assert row["image_count"] == 3


def test_review_sheet_is_unchanged_without_translations():
    """`images_ko`가 없으면 원본 그대로다 — 무회귀."""
    from src.pipeline.register_pipe import build_source_review_row
    row = build_source_review_row({"images": ["https://o/0.jpg"], "title": "가방"},
                                  url="https://item.taobao.com/item.htm?id=1")
    assert row["thumbnail"] == "https://o/0.jpg"


def _client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
    return c


def test_upload_route_swaps_in_the_translations():
    """★ 마켓에 나가는 배열이 **번역본**이다. 여기가 D2의 판정 지점이다.

    디스패처를 목으로 잡아 **실제로 무엇이 실려 나갔는지** 본다 —
    「예외가 안 났다」가 아니라 「번역본이 갔다」를 재야 한다.
    """
    import src.seller_console.views as V
    sent = {}
    row = {"id": "i1", "extra_json": json.dumps(_extra())}
    c = _client()

    class _Result:
        def to_dict(self):
            return {"results": []}

    class _Dispatcher:
        def dispatch(self, product_data, markets):
            sent["product"] = dict(product_data)
            return _Result()          # 라우트가 `result.to_dict()`를 부른다(실제 모양 그대로)

    # D2b 게이트는 **통과시킨다** — 여기서 재는 것은 「무엇이 실려 나갔나」이고,
    #   게이트 자체는 `test_d2b_cdn_and_reachability.py`가 잰다(계약 하나에 두 가지를 재지 않는다).
    with patch.object(V, "_get_owned_item", lambda i: dict(row)), \
         patch.object(V, "_get_upload_dispatcher", lambda: _Dispatcher()), \
         patch("src.services.image_reachability.check_all",
               return_value={"ok": True, "checked": 3, "bad": [], "unknown": []}):
        r = c.post("/seller/collect/upload", json={
            "item_id": "i1", "markets": ["coupang"],
            "product": {"title": "수행방패", "price": "100", "currency": "KRW",
                        "images": _extra()["images"]},
        })
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    assert sent, "디스패처가 불리지 않았다 — 계약이 아무것도 재지 못했다"
    assert sent["product"]["images"] == [
        "https://res.cloudinary.com/x/0.jpg",   # 번역본
        "https://o/1.jpg",                 # 실패 → 원본
        "https://o/2.jpg",                 # 꺼 둠 → 원본
    ]
    assert sent["product"]["thumbnail"] == "https://res.cloudinary.com/x/0.jpg"


def test_upload_asks_once_when_a_used_page_has_banned_words():
    """D2-3: 금칙어가 걸린 번역본을 쓰면 **한 번 물어본다**(막지는 않는다)."""
    import src.seller_console.views as V
    ex = _extra()
    ex["images_ko"][2]["use"] = True          # 금칙어 걸린 장을 쓰기로
    row = {"id": "i1", "extra_json": json.dumps(ex)}
    c = _client()
    with patch.object(V, "_get_owned_item", lambda i: dict(row)), \
         patch("src.services.image_reachability.check_all",
               return_value={"ok": True, "checked": 3, "bad": [], "unknown": []}):
        r = c.post("/seller/collect/upload", json={
            "item_id": "i1", "markets": ["coupang"],
            "product": {"title": "수행방패", "price": "100", "images": ex["images"]},
        })
    assert r.status_code == 409
    d = r.get_json()
    assert d["needs_confirm"] is True
    assert [w["idx"] for w in d["warn_pages"]] == [2]


def test_toggle_route_saves_and_returns_the_plan():
    import src.seller_console.views as V
    saved = {}
    row = {"id": "i1", "extra_json": json.dumps(_extra())}
    c = _client()
    with patch.object(V, "_get_owned_item", lambda i: dict(row)), \
         patch("src.seller_console.collect_history_store.update",
               side_effect=lambda i, **kw: saved.update(kw) or True):
        r = c.post("/seller/collect/i1/image-use", json={"flags": {"0": False, "2": True}})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert [p["source"] for p in d["plan"]] == ["original", "original", "translated"]
    ex = json.loads(saved["extra_json"])
    assert ex["images"] == _extra()["images"], "토글이 원본을 건드렸다"


def test_the_effective_array_is_built_in_exactly_one_place():
    """화면과 파이프가 각자 계산하면 「서랍은 한국어, 마켓은 중국어」가 된다."""
    import subprocess
    out = subprocess.run(
        ["grep", "-rn", "def effective_images", "src/"],
        capture_output=True, text=True, cwd=ROOT).stdout.strip().splitlines()
    assert len(out) == 1, f"배열을 만드는 자리가 여럿이다: {out}"
    assert "image_translate_store.py" in out[0]


def test_drawer_shows_which_source_each_page_uses():
    """썸네일 탭 = 등록에 나갈 목록. 각 장에 원본/번역 표식이 붙는다."""
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "kgpRenderUseBadges" in tpl
    seg = tpl.split("function kgpRenderUseBadges", 1)[1][:900]
    assert "'번역본'" in seg and "'원본'" in seg
    assert "kgp-src-badge" in seg


def test_zoom_opens_in_place_not_a_new_tab():
    """크게 보기는 **같은 화면 위**다 — 새 창·라우트 이동 0(콘솔 규율)."""
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    seg = tpl.split("function kgpImgkoZoom", 1)[1][:700]
    assert "window.open" not in seg and "target=" not in seg
    assert "kgp-img-zoom" in seg
    css = (ROOT / "src/static/app.css").read_text(encoding="utf-8")
    assert ".kgp-img-zoom" in css and "var(--" in css.split(".kgp-img-zoom", 1)[1][:400]


def test_no_live_calls_in_this_contract_file():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert "requests" not in mods and "urllib" not in mods
