"""F27 계약 — 「URL이 있다」와 「이미지가 온다」는 다르다.

## 실측 (오너 2026-09-16)

번역 탭 5장이 전부 **깨진 이미지 아이콘**(대체 텍스트 「번역본」 노출) + 「외부 미공개」.
썸네일 탭은 **중국어 원본** 5장. 로그인 세션은 정상.

## 실측으로 가른 세 가지

① 라우트는 **정상이다.** 바이트가 DB에 있으면 `200 · image/jpeg · 바이트 일치`.
   **없으면 404** — 그래서 깨진 아이콘이 떴다.
   → 오너의 5장은 **D1 시절 컨테이너 파일**에 있었고, D2가 그 경로를 없애며 **이관하지 않았다.**
     Render는 배포마다 그 파일을 버리므로 이관할 것도 이미 없었다.

② 썸네일 탭은 `_EXTRA.images`(**원본**)를 그렸다. D2에서 뱃지만 붙이고 그림은 안 바꿨다 —
   그래서 「번역본 뱃지가 붙은 중국어 이미지」가 떴다.

③ `images_ko`에 URL이 남아 있어 화면은 「번역됨」이라고 말했다. **적혀 있는 것과 있는 것은 다르다.**

## 그래서 이 계약은 렌더 HTML의 `<img src>`를 **실제로 GET** 한다

「URL이 있다」가 아니라 **「이미지가 온다」**를 잰다. D2 계약은 쓰기만 쟀다 —
읽는 쪽 계약이 없어서, 저장소를 옮기며 데이터를 잃고도 전부 초록이었다.
"""
from __future__ import annotations

import ast
import base64
import json
import os
import re
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


JPG = b"\xff\xd8\xff\xe0-korean-pixels"


def _client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
    return c


def _row(extra):
    return {"id": "i1", "title": "수행방패", "url": "https://item.taobao.com/item.htm?id=1",
            "image_url": "", "price": "100", "currency": "CNY", "status": "ok",
            "extra_json": json.dumps(extra)}


def _extra_with_translation(url="/seller/collect/image-ko/i1/0"):
    return {"images": ["https://o/0.jpg", "https://o/1.jpg"],
            "images_ko": [{"idx": 0, "status": "done", "url": url, "use": True,
                           "stored_by": "db", "warn": [], "dense": False}]}


# ---------------------------------------------------------------------------
# ① 라우트 — 바이트가 있으면 이미지가 온다
# ---------------------------------------------------------------------------

def test_route_serves_the_actual_bytes():
    """로그인 세션 GET → **200 · image/* · 바이트 일치**."""
    import src.seller_console.views as V
    from src.db import image_ko_blobs_pg as blobs
    blobs.put("i1", 0, JPG, seller_id="u1")
    c = _client()
    with patch.object(V, "_get_owned_item", lambda i: _row(_extra_with_translation())):
        r = c.get("/seller/collect/image-ko/i1/0")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("image/")
    assert r.data == JPG


def test_route_404s_when_the_bytes_are_gone():
    """바이트가 없으면 404다 — **그게 깨진 아이콘의 정체였다.**"""
    import src.seller_console.views as V
    c = _client()
    with patch.object(V, "_get_owned_item", lambda i: _row(_extra_with_translation())):
        r = c.get("/seller/collect/image-ko/i1/0")
    assert r.status_code == 404


def test_detail_kind_is_served_separately():
    import src.seller_console.views as V
    from src.db import image_ko_blobs_pg as blobs
    blobs.put("i1", 0, b"gallery-bytes")
    blobs.put("i1", 0, b"detail-bytes", kind="detail")
    c = _client()
    with patch.object(V, "_get_owned_item", lambda i: _row(_extra_with_translation())):
        assert c.get("/seller/collect/image-ko/i1/0").data == b"gallery-bytes"
        assert c.get("/seller/collect/image-ko/i1/0?kind=detail").data == b"detail-bytes"


# ---------------------------------------------------------------------------
# ② ★ 렌더된 <img src>를 실제로 GET 한다
# ---------------------------------------------------------------------------

def _img_srcs(html: str) -> list:
    """렌더 HTML에서 우리 서버로 가는 이미지 주소만 뽑는다."""
    out = []
    for m in re.finditer(r"""src=["'](/seller/collect/image-ko/[^"']+)["']""", html):
        out.append(m.group(1))
    # JS가 문자열로 조립하는 경우(`e.url`)는 시드된 plan에서 뽑는다.
    for m in re.finditer(r'"url":\s*"(/seller/collect/image-ko/[^"]+)"', html):
        out.append(m.group(1))
    return sorted(set(out))


def test_every_rendered_image_url_actually_returns_an_image():
    """★★ **「URL이 있다」가 아니라 「이미지가 온다」를 잰다.**

    D2 계약은 쓰기만 쟀다 — 읽는 쪽 계약이 없어서, 저장소를 옮기며 데이터를 잃고도
    전부 초록이었다. 이 계약이 그 구멍이다.
    """
    import src.seller_console.views as V
    from src.db import image_ko_blobs_pg as blobs
    blobs.put("i1", 0, JPG, seller_id="u1")
    ex = _extra_with_translation()
    c = _client()
    with patch.object(V, "_get_owned_item", lambda i: _row(ex)):
        html = c.get("/seller/collect/preview/i1?drawer=1").get_data(as_text=True)
        srcs = _img_srcs(html)
        assert srcs, "렌더 HTML에 번역본 주소가 없다"
        for u in srcs:
            r = c.get(u)
            assert r.status_code == 200, f"{u} → {r.status_code}"
            assert r.headers["Content-Type"].startswith("image/"), u
            assert r.data, f"{u} 가 빈 바이트를 돌려준다"


def test_a_missing_translation_is_not_rendered_as_an_image():
    """바이트가 없으면 **그 주소를 그리지 않는다** — 깨진 아이콘을 만들지 않는다."""
    import src.seller_console.views as V
    ex = _extra_with_translation()          # blob은 넣지 않는다(= 사라진 상태)
    c = _client()
    with patch.object(V, "_get_owned_item", lambda i: _row(ex)):
        html = c.get("/seller/collect/preview/i1?drawer=1").get_data(as_text=True)
    assert "번역본 사라짐" in html or "저장된 번역본이 없습니다" in html, \
        "사라진 사실을 화면이 말하지 않는다"


# ---------------------------------------------------------------------------
# ③ 사라진 번역본은 어디에도 쓰이지 않는다
# ---------------------------------------------------------------------------

def test_plan_marks_a_translation_with_no_bytes_as_gone():
    from src.services.image_translate_store import effective_plan
    plan = effective_plan(_extra_with_translation(), item_id="i1")
    assert plan[0]["gone"] is True
    assert plan[0]["translatable"] is False, "쓸 수 있다고 말하면 안 된다"
    assert plan[0]["source"] == "original"


def test_plan_is_fine_once_the_bytes_are_there():
    from src.db import image_ko_blobs_pg as blobs
    from src.services.image_translate_store import effective_plan
    blobs.put("i1", 0, JPG)
    plan = effective_plan(_extra_with_translation(), item_id="i1")
    assert plan[0]["gone"] is False and plan[0]["source"] == "translated"
    assert plan[0]["bytes"] == len(JPG)


def test_unknown_storage_does_not_kill_a_translation():
    """★ **「물어보지 못했다」로 멀쩡한 번역본을 지우지 않는다.**

    DB가 잠깐 대답을 안 했다고 화면이 「번역본 사라짐」이라 적으면, 사람은 없는 사고를 쫓는다.
    「행이 없다」와 「못 물어봤다」는 다른 말이고, 그 둘을 같은 값으로 돌려주면 구분이 사라진다.
    """
    from src.services.image_translate_store import effective_images, effective_plan
    with patch("src.db.image_ko_blobs_pg.status_for_item", return_value=None):
        plan = effective_plan(_extra_with_translation(), item_id="i1")
        eff = effective_images(_extra_with_translation(), item_id="i1")
    assert plan[0]["gone"] is False, "모름을 사라짐으로 읽었다"
    assert eff[0] == "/seller/collect/image-ko/i1/0", "모름인데 원본으로 되돌렸다"


def test_cdn_urls_are_not_judged_by_our_storage():
    """외부 주소는 우리 저장소와 무관하게 산다 — 바이트가 없다고 죽이지 않는다."""
    from src.services.image_translate_store import effective_plan
    ex = _extra_with_translation("https://res.cloudinary.com/x/0.jpg")
    plan = effective_plan(ex, item_id="i1")
    assert plan[0]["gone"] is False and plan[0]["source"] == "translated"


def test_effective_images_never_returns_a_dead_url():
    """★ 등록에 **죽은 주소를 내보내지 않는다** — 내보내면 마켓이 404를 본다."""
    from src.services.image_translate_store import effective_images
    eff = effective_images(_extra_with_translation(), item_id="i1")
    assert eff == ["https://o/0.jpg", "https://o/1.jpg"], "사라진 번역본을 등록에 실었다"


def test_upload_route_passes_item_id_so_it_can_check():
    """등록 경로가 `item_id`를 넘겨야 바이트를 볼 수 있다 — 안 넘기면 적힌 대로 나간다."""
    src = (ROOT / "src/seller_console/views.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "collect_upload")
    body = ast.unparse(fn)
    assert "effective_images(_uex, item_id=_uid" in body.replace("\n", " ") or \
           ("item_id=_uid" in body and "effective_images" in body)


# ---------------------------------------------------------------------------
# ④ 썸네일 탭은 등록에 나갈 목록을 **그린다**
# ---------------------------------------------------------------------------

def test_thumbnail_tab_draws_effective_not_originals():
    """D2-2를 반쪽만 했었다 — 뱃지는 「번역본」인데 그림은 중국어 원본이었다."""
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    seg = tpl.split("function renderGallery", 1)[1][:1400]
    assert "kgpEffectiveImages(urls)" in seg, "썸네일 탭이 원본만 그린다"


def test_the_model_still_holds_originals():
    """★★ 보여 주는 그림만 바꾼다 — **모델은 원본**이라야 저장이 원본을 안 덮는다."""
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    seg = tpl.split("function _initImages", 1)[1][:500]
    assert "_EXTRA.images" in seg and "images_ko" not in seg, \
        "이미지 행 모델이 번역본으로 오염됐다 — 저장하면 원본이 사라진다"


def test_screen_does_not_use_a_gone_translation():
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    seg = tpl.split("function kgpEffectiveImages", 1)[1][:700]
    assert "plan.gone" in seg, "화면이 사라진 번역본을 그대로 쓴다"


# ---------------------------------------------------------------------------
# ⑤ 진단 화면 — 로그를 회수시키지 않는다
# ---------------------------------------------------------------------------

def test_diagnostic_screen_exists_and_is_admin_only():
    from src.order_webhook import app
    rules = {str(r) for r in app.url_map.iter_rules()}
    assert "/seller/admin/image-storage" in rules
    assert "/seller/admin/image-storage/backfill" in rules


def test_diagnostic_shows_bytes_cdn_and_reason():
    import src.seller_console.views as V
    from src.db import image_ko_blobs_pg as blobs
    blobs.put("i1", 0, JPG, seller_id="u1")
    blobs.set_cdn("i1", 0, "", error="boom")
    ex = _extra_with_translation()
    c = _client()
    with patch.object(V, "_sourcing_require_admin", lambda: None), \
         patch("src.seller_console.collect_history_store.list_items",
               return_value=[_row(ex)]):
        html = c.get("/seller/admin/image-storage").get_data(as_text=True)
    assert "저장소 진단" in html
    assert "boom" in html, "백필 실패 사유를 화면이 말하지 않는다"
    assert "KB" in html, "바이트 유무를 말하지 않는다"


def test_diagnostic_never_shows_env_values(monkeypatch):
    """env는 **이름과 존재 여부만** — 값은 진단에도 나오지 않는다."""
    import src.seller_console.views as V
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "super-secret-value")
    c = _client()
    with patch.object(V, "_sourcing_require_admin", lambda: None), \
         patch("src.seller_console.collect_history_store.list_items", return_value=[]):
        html = c.get("/seller/admin/image-storage").get_data(as_text=True)
    assert "CLOUDINARY_API_SECRET" in html
    assert "super-secret-value" not in html, "★ 시크릿 값이 화면에 나왔다"


def test_diagnostic_does_not_probe_externally_unless_asked():
    """외부 확인은 **눌렀을 때만** — 열 때마다 나가면 그게 곧 왕복 비용이다."""
    src = (ROOT / "src/seller_console/views.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "image_storage_diag")
    body = ast.unparse(fn)
    assert 'probe' in body and "check_one" in body
    assert "if probe and" in body.replace("\n", " ")


def test_owner_never_has_to_read_render_logs_for_this():
    """진단이 화면에 있으면 **로그 회수를 시키지 않는다**(오너 지시 F27-4)."""
    tpl = (ROOT / "src/seller_console/templates/image_storage_diag.html").read_text(encoding="utf-8")
    for want in ("바이트", "CDN", "백필", "등록에 나감"):
        assert want in tpl
    assert "지금 올리기" in tpl, "배포를 기다려야만 백필이 돈다"


def test_no_live_calls_in_this_contract_file():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert "requests" not in mods and "urllib" not in mods
