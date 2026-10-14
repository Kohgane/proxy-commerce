"""Y11-D(오너 2026-10-14 17:26~17:30 캡처) — 5건.

1. 하루 상한: 보내기 전에 본다(거부 0) · 상한은 실패 배지가 아니다 · 이미지 큐는 크론 틱이 깨운다(→ test_y11c_translate_queue 쪽에 상한 계약)
2. 수집 URL이 광고 클릭 링크(click.simba.taobao.com) — 정규 주소 + raw_url 보존 · 「주소 후보」도 정규 주소
3. 상품명 괄호 반토막 — 원제 「VRSUK{비즈니스 시리즈} 심플 리클라이너…」 그대로 고정
4. 대표 사진 소품 글자(책등) — 작고 흐리면 주의로, 진짜 낱말·상표면 면적 무관 「반려 가능」 유지 · 편집하면 다시 잰다
5. 상세페이지 꾸미기 빈 블록 — 빈 <img> 0 · 저장 시 「빈 블록 n개 무시」 · 빈 마켓 칸이 공통을 가리지 않게
"""
from __future__ import annotations

import io
import json

import pytest

VRSUK_SIMBA = ("https://click.simba.taobao.com/cc_im?p=%B0%EC%B9%AB%D2%CE&s=1234&k=5&e=abcd%26skuId%3D6301579486784%26q%3Dx"
               "&mm_sceneid=1_0_1_0&a=2&id=748639898871&spm=a230r.1.14.1")


def _client(user):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = user
    return c


# ── 1. 이미지 큐는 크론 틱이 깨운다 ──────────────────────────────────────────────────────────

def test_cron_tick_kicks_the_image_queue(monkeypatch):
    """실측: `/cron/translate-drain`은 글 번역 큐·파일럿만 돌렸다 — 이미지 큐는 접수·「다시 번역」 때만 돌아,
    카운터를 정정해도(320 → 185) 대기 114장이 그대로 섰다. 이제 틱마다 깨운다."""
    from src.pricing import cron as C
    from src.services import image_translate_auto as A
    from src.services import workers as W
    import src.seller_console.translate_worker as TW
    from src.order_webhook import app
    kicked = []
    monkeypatch.delenv("IMAGE_TRANSLATE_AUTO_SYNC", raising=False)
    monkeypatch.setattr(A, "kick", lambda: kicked.append(1))
    monkeypatch.setattr(TW, "drain_once", lambda **k: {"ok": True, "processed": 0, "remaining": 0})
    monkeypatch.setattr(C, "_run_pilot_finish_tick", lambda **k: {"gated": True})
    monkeypatch.setattr(W, "lease", lambda *a, **k: True)
    monkeypatch.setattr(W, "release", lambda *a, **k: None)
    monkeypatch.setattr(W, "record_run", lambda *a, **k: None)
    C._tick_lock.acquire(blocking=False)
    r = C._run_full_tick(app, limit=1, pilot_chunk=1, tick_budget=20.0)
    assert kicked == [1] and r.get("imgko_kick") is True


# ── 2. 광고 클릭 링크 → 정규 주소 ──────────────────────────────────────────────────────────────

def test_simba_ad_link_is_canonicalised_and_raw_kept():
    from src.collectors.product_key import canonical_source_url, normalize_product_key
    assert canonical_source_url(VRSUK_SIMBA) == "https://item.taobao.com/item.htm?id=748639898871&skuId=6301579486784"
    assert canonical_source_url("https://click.simba.taobao.com/cc_im?p=x&id=12") == "https://item.taobao.com/item.htm?id=12"
    assert canonical_source_url("https://click.simba.taobao.com/cc_im?p=x") == "https://click.simba.taobao.com/cc_im?p=x"  # 상품번호 없으면 그대로
    assert canonical_source_url("https://detail.tmall.com/item.htm?id=1") == "https://detail.tmall.com/item.htm?id=1"
    assert normalize_product_key(VRSUK_SIMBA) == normalize_product_key(canonical_source_url(VRSUK_SIMBA))   # 중복 판정 그대로


def test_collect_append_stores_canonical_url_and_raw_url_and_address_candidates_show_it():
    from src.seller_console import collect_history_store as S
    from src.seller_console.upload_dispatcher import payload_diagnosis
    iid = S.append(source="extension", url=VRSUK_SIMBA, seller_id="y11d-url", title="VRSUK", price="1", currency="CNY",
                   extra={"title_ko": "VRSUK 의자"})
    iid = iid[0] if isinstance(iid, tuple) else iid
    row = S.get(iid, seller_ids={"y11d-url"})
    assert row["url"] == "https://item.taobao.com/item.htm?id=748639898871&skuId=6301579486784"
    assert json.loads(row["extra_json"])["raw_url"] == VRSUK_SIMBA
    d = payload_diagnosis({"url": row["url"]}, row)
    urls = [(c["source"], c["url"]) for c in d.get("candidates") or d.get("cands") or []]
    assert any("url 컬럼" in s and u.startswith("https://item.taobao.com/") for s, u in urls)
    assert any("raw_url" in s and "click.simba" in u for s, u in urls)
    assert not any("click.simba" in u for s, u in urls if "raw_url" not in s)      # 정규 주소만 「쓰는」 후보


# ── 3. 괄호 묶음은 통째로 ───────────────────────────────────────────────────────────────────

def test_brace_group_is_never_cut_in_half_vrsuk():
    from src.uploaders import coupang_title as ct
    src = {"title_ko": "VRSUK{비즈니스 시리즈} 심플 리클라이너 오일 왁스 가죽 사무용 회전 승강 1인 의자",
           "title_src": "VRSUK{商务系列}简约躺椅油蜡皮办公旋转升降现货单椅", "title_original": "", "brand": "",
           "options": [], "skus": []}
    assert ct.brand_of(src) == "VRSUK"
    assert ct.build_name(src, "front")["name"] == "VRSUK 비즈니스 시리즈 심플 리클라이너 오일 왁스 가죽 사무 회전 승강 의자"
    assert ct.build_name(src, "omit")["name"].startswith("비즈니스 시리즈 ")     # 「시리즈 심플…」(반토막) 아님
    for t in ("A[수납 박스] 정리함", "B(대형 사이즈) 러그"):
        n = ct.build_name({"title_ko": t, "brand": "", "options": [], "skus": []}, "omit")["name"]
        assert n.startswith(("수납 박스", "대형 사이즈")), n                   # 묶음 낱말이 다 남는다
    n = ct.build_name({"title_ko": "수행 방패(SPORTLINK)는 자석 충전식 스마트폰 거치대", "brand": "", "options": [], "skus": []}, "omit")["name"]
    assert "SPORTLINK" not in n and n.startswith("자석")                         # 한글 없는 묶음은 통째로 뗀다


# ── 4. 소품 글자(작음) — 주의 · 진짜 낱말·상표는 반려 가능 유지 ──────────────────────────────────

def _jpeg(w=800, h=800):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), (250, 250, 250)).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture
def ocr(monkeypatch):
    from src.services import image_text_precheck as P
    from src.services import ocr_tencent as O
    state = {"text": "", "boxes": []}
    monkeypatch.setattr(P, "all_text", lambda raw: (bool(state["text"]), state["text"][:40]))
    monkeypatch.setattr(O, "read_boxes", lambda raw: {"ok": True, "boxes": state["boxes"], "size": [800, 800]})
    return state


def test_tiny_blurry_prop_text_is_not_text_at_all_vrsuk(ocr):
    """VRSUK 대표사진 실측: 책등 글자 「OUIY TAHTZ OYLNTE」「HRるtk工4品る艺k blllY」(OCR이 깨진 글자로 읽음).
    Y11-D는 「소품 글자(작음)」 주의였다 → Y11-G(오너): 소품 글자는 글자가 아니다 — 줄 자체가 없다.
    반례: 책·포스터 상품이면 소품 규칙을 끈다 → 예전 「소품 글자(작음)」 줄로 돌아온다."""
    from src.services import coupang_image_check as C
    ocr["text"] = "OUIY TAHTZ OYLNTE HRるtk工4品る艺k blllY"
    ocr["boxes"] = [{"x": 600, "y": 300, "w": 30, "h": 40, "src": "OUIY TAHTZ OYLNTE", "conf": 62.0},
                    {"x": 640, "y": 300, "w": 25, "h": 40, "src": "HRるtk工4品る艺k blllY", "conf": 55.0}]
    r = C.check_bytes(_jpeg())
    assert not {"text", "text_small"} & {f["key"] for f in r["flags"]}
    assert r["prop_only"] and r["prop_n"] == 2 and r["text"] is False
    book = C.apply_exempt(r, True)
    keys = {f["key"]: f for f in book["flags"]}
    assert keys["text_small"]["line"].startswith("소품 글자(작음) — 지우려면 사진 편집") and keys["text_small"]["hold"] is False


@pytest.mark.parametrize("words", ["www.tmall.com", "OFFICIAL STORE", "VRSUK Italian brand"])
def test_small_watermark_with_real_word_stays_rejection(ocr, words):
    """반례(오너 Y11-D): 작은 워터마크·로고는 진짜 반려 사유 — 사진·워터마크 낱말이 있으면 소품이 아니고 「반려 가능」 유지."""
    from src.services import coupang_image_check as C
    ocr["text"] = words
    ocr["boxes"] = [{"x": 700, "y": 760, "w": 60, "h": 20, "src": words, "conf": 60.0}]
    keys = {f["key"] for f in C.check_bytes(_jpeg())["flags"]}
    assert "text" in keys and "text_small" not in keys, words


def test_trademark_on_a_prop_is_not_a_rejection(ocr):
    """Y11-G(오너): 소품(책 표지)의 상표 토큰은 차단·주의가 아니다 — 대표사진 판정엔 줄 없음(위험 목록에 「참고」만, 별도 테스트)."""
    from src.services import coupang_image_check as C
    ocr["text"] = "Zaha Hadid"
    ocr["boxes"] = [{"x": 700, "y": 760, "w": 60, "h": 20, "src": "Zaha Hadid", "conf": 60.0}]
    r = C.check_bytes(_jpeg())
    assert r["prop_only"] and not {"text", "text_small"} & {f["key"] for f in r["flags"]}


def test_big_or_confident_text_stays_rejection(ocr):
    from src.services import coupang_image_check as C
    ocr["text"] = "OUIY TAHTZ"
    ocr["boxes"] = [{"x": 0, "y": 0, "w": 400, "h": 100, "src": "OUIY TAHTZ", "conf": 60.0}]      # 면적 6%
    assert "text" in {f["key"] for f in C.check_bytes(_jpeg())["flags"]}
    ocr["boxes"] = [{"x": 600, "y": 300, "w": 30, "h": 40, "src": "OUIY TAHTZ", "conf": 97.0}]    # 작지만 또렷
    assert "text" in {f["key"] for f in C.check_bytes(_jpeg())["flags"]}
    ocr["boxes"] = []                                                                              # 상자를 못 읽음 → 내리지 않는다
    assert "text" in {f["key"] for f in C.check_bytes(_jpeg())["flags"]}


def test_editing_the_rep_photo_rejudges_on_the_new_url(monkeypatch):
    """편집으로 지우면 대표 사진 주소가 편집본으로 바뀌어 판정은 그 주소로 새로 돈다(주소별 캐시 — 옛 판정이 따라오지 않는다)."""
    from src.services import coupang_image_check as C
    from src.services import image_translate_store as S
    calls = []
    monkeypatch.setattr(C, "enabled", lambda: True)
    monkeypatch.setattr(C, "_bytes_for", lambda url: (calls.append(url) or _jpeg(), ""))
    from src.services import image_text_precheck as P
    monkeypatch.setattr(P, "all_text", lambda raw: (False, ""))
    ex = {"images": ["https://img.alicdn.com/rep.jpg"],
          "images_ko": [{"idx": 0, "status": "done", "use": True, "url": "https://res.cloudinary.com/x/edit/1.jpg",
                         "edit": {"url": "https://res.cloudinary.com/x/edit/1.jpg", "by": "user", "ops": [{"id": "t0", "action": "erase"}]}}]}
    rep = S.effective_images(ex, kind="gallery")[0]
    assert rep == "https://res.cloudinary.com/x/edit/1.jpg"
    C.check_url(rep)
    assert calls == [rep]


# ── 5. 빈 블록 ──────────────────────────────────────────────────────────────────────────────

def test_blank_blocks_never_reach_the_payload_and_save_says_so():
    from src.seller_console.upload_dispatcher import render_detail_blocks_html
    blocks = {"common": [{"type": "text", "content": "원목 의자"}], "coupang": [{"type": "image", "content": ""}]}
    html = render_detail_blocks_html(blocks, "coupang")
    assert "<img" not in html and "원목 의자" in html                          # 빈 이미지 0 · 빈 마켓 칸이 공통을 가리지 않는다
    from src.seller_console import collect_history_store as St
    iid = St.append(source="extension", url="https://detail.tmall.com/item.htm?id=9", seller_id="y11d-blk", title="x",
                    price="1", currency="CNY", extra={})
    iid = iid[0] if isinstance(iid, tuple) else iid
    r = _client("y11d-blk").post(f"/seller/collect/preview/{iid}/save", json={
        "title": "x", "detail_blocks": {"common": [{"type": "text", "content": "원목 의자"}, {"type": "image", "content": " "}],
                                         "coupang": [{"type": "image", "content": ""}]}}).get_json()
    assert r["ok"] and r["notice"] == "빈 블록 2개 무시"
    saved = json.loads(St.get(iid, seller_ids={"y11d-blk"})["extra_json"])["detail_blocks"]
    assert saved == {"common": [{"type": "text", "content": "원목 의자"}]}
