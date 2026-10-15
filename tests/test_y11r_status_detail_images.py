"""Y11-R(오너 2026-10-16) — VRSUK 첫 등록 뒤 남은 일 계약.

운영 근거(읽기 전용 실측):
  - 텐센트 TextTranslate 51칸 전부 `InvalidParameterValue — 不支持的语种：zh_to_ko`(intl 엔드포인트). 줄 탓이 아니라
    **언어쌍 미지원** — 이분 탐색은 호출만 늘렸고, 60초 재시도도 같은 답. → 그 응답이면 나누지 않고 번역 체인으로.
  - 네이버 사전검증 카드 3,226,440 vs 실제 전송 4,118,850: 같은 비율(0.783) — 환율이 아니라 **마진**(사전검증 = 서버 기본 25%,
    등록 = 화면 슬라이더). → 사전검증도 화면 마진을 보낸다.
  - 쿠팡 상세는 TEXT 한 덩어리 고정이라 번역·다듬은 상세 이미지 28장이 한 장도 안 나갔다. → 이미지 블록을 먼저, 글은 아래.
  - 「검토 상태 보기」가 등록 결과 팝업에만 있었다 → 드로어 맨 위 「마켓 등록본」에서 열 때 4마켓 상태를 한 번에.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "src" / "seller_console" / "templates"


@pytest.fixture
def state(monkeypatch):
    import src.db.image_translate_queue_pg as st
    box = {}
    monkeypatch.setattr(st, "state_get", lambda k: dict(box.get(k) or {}))
    monkeypatch.setattr(st, "state_set", lambda k, v: box.__setitem__(k, json.loads(json.dumps(v))))
    return box


@pytest.fixture
def up():
    from src.uploaders.coupang_uploader import CoupangUploader
    return CoupangUploader.__new__(CoupangUploader)


IMGS = [f"https://res.cloudinary.com/x/image/upload/d{i}.jpg" for i in range(28)]


# ── 3. 쿠팡 상세 이미지 블록 ─────────────────────────────────────────────────────────────────────

def test_contents_image_block_first_then_text(up, monkeypatch):
    monkeypatch.delenv("COUPANG_DETAIL_IMAGES", raising=False)
    monkeypatch.delenv("COUPANG_DETAIL_IMAGE_CONTENTS_TYPE", raising=False)
    c = up._build_contents({"title": "VRSUK", "description_html": "<p>소재: 원목</p>", "detail_images": IMGS})
    assert [b["contentsType"] for b in c] == ["IMAGE", "TEXT"]
    assert [d["content"] for d in c[0]["contentDetails"]] == IMGS            # 28장 순서 그대로
    assert all(d["detailType"] == "IMAGE" for d in c[0]["contentDetails"])
    assert c[1]["contentDetails"][0]["content"] == "<p>소재: 원목</p>"        # 규격 글은 이미지 아래


def test_contents_without_images_is_old_text_only(up, monkeypatch):
    monkeypatch.delenv("COUPANG_DETAIL_IMAGES", raising=False)
    c = up._build_contents({"title": "VRSUK", "description_html": "본문"})
    assert c == [{"contentsType": "TEXT", "contentDetails": [{"content": "본문", "detailType": "TEXT"}]}]
    monkeypatch.setenv("COUPANG_DETAIL_IMAGES", "0")                       # 끄면 예전 형태(5,691건 검증 모양)
    c = up._build_contents({"title": "VRSUK", "description_html": "본문", "detail_images": IMGS})
    assert [b["contentsType"] for b in c] == ["TEXT"]


def test_detail_image_urls_normalize_and_filter(up):
    got = up.detail_image_urls({"detail_images": ["//img.alicdn.com/a.jpg", "https://x/b.jpg", "https://x/b.jpg",
                                                  "data:image/png;base64,AAA", "", None, "/rel/c.jpg"]})
    assert got == ["https://img.alicdn.com/a.jpg", "https://x/b.jpg"]
    assert len(up.detail_image_urls({"detail_images": [f"https://x/{i}.jpg" for i in range(60)]})) == up.DETAIL_IMAGE_MAX


def test_detail_images_ride_through_bridge_and_prepare(up):
    from src.channel_sync._channel_bridge import to_collected
    col = to_collected({"title": "VRSUK", "price": 100, "images": ["https://x/g.jpg"], "detail_images": IMGS[:3]})
    assert col["detail_images"] == IMGS[:3]
    up.CATEGORY_MAP = {}
    prepared = up.prepare_product(dict(col, title_ko="VRSUK 의자"))
    assert prepared["detail_images"] == IMGS[:3]
    assert [b["contentsType"] for b in up._build_contents(prepared)][0] == "IMAGE"


def test_sent_summary_counts_detail_images_apart_from_lines(up):
    from src.uploaders.coupang_uploader import CoupangUploader
    body = {"displayCategoryCode": 1, "items": [{"images": [{"imageType": "REPRESENTATION"}],
            "contents": up._build_contents({"title": "t", "description_html": "a\nb", "detail_images": IMGS[:5]})}]}
    s = CoupangUploader.sent_summary(body)
    assert s["detail_images"] == 5 and s["detail_lines"] == 2


def test_refresh_target_uses_translated_detail_images_and_drops_internal(monkeypatch):
    """큐 갱신(세션 없는 크론)도 등록과 같은 규칙 — 번역본 사용 반영 · 갤러리와 같은 장 제외 · 우리 서버 주소 장 제외."""
    import src.services.coupang_detail_refresh as R
    import src.services.image_translate_store as its
    import src.services.image_reachability as reach
    monkeypatch.setattr("src.seller_console.views._ensure_outward", lambda item: item)
    monkeypatch.setattr(its, "effective_images",
                        lambda ex, kind="gallery", item_id="", originals=None:
                        (["https://cdn/g.jpg"] if kind == "gallery" else
                         ["https://cdn/ko0.jpg", "https://cdn/g.jpg", "https://ours.example/i/2", "https://cdn/ko3.jpg"]))
    monkeypatch.setattr(reach, "is_internal", lambda u: "ours.example" in u)
    pd = {"images": ["o/g"], "detail_images": ["o/0", "o/1", "o/2", "o/3"]}
    skipped = R._effective_detail_images({"id": "it1", "extra_json": "{}"}, pd)
    assert pd["detail_images"] == ["https://cdn/ko0.jpg", "https://cdn/ko3.jpg"] and skipped == 1


def test_refresh_hash_changes_when_images_join(up, monkeypatch):
    """예전에 보낸 상세(글만)와 해시가 달라 VRSUK 2건이 다시 나간다(이미 같은 상세면 안 보낸다는 규칙은 그대로)."""
    import src.services.coupang_detail_refresh as R
    monkeypatch.delenv("COUPANG_DETAIL_IMAGES", raising=False)
    old = R._hash(up._build_contents({"title": "t", "description_html": "본문"}))
    new = R._hash(up._build_contents({"title": "t", "description_html": "본문", "detail_images": IMGS}))
    assert old != new


# ── 2(b). 텐센트 언어쌍 미지원 → 번역 체인 ───────────────────────────────────────────────────────

UNSUP = {"ok": False, "text": "", "why": "InvalidParameterValue", "message": "不支持的语种：zh_to_ko"}


def test_unsupported_pair_falls_back_to_chain_and_skips_tencent_after(monkeypatch, state):
    import src.uploaders.detail_translate as dt
    calls = {"tc": 0, "chain": 0}

    def tc(text):
        calls["tc"] += 1
        return dict(UNSUP)

    def chain(text):
        calls["chain"] += 1
        return {"ok": True, "text": "\n".join("번역 " + x for x in text.split("\n")), "why": "", "provider": "papago"}

    monkeypatch.setattr(dt, "_tencent", tc)
    monkeypatch.setattr(dt, "_chain", chain)
    monkeypatch.setattr(dt, "_PAIR_DOWN", {"at": 0.0, "message": ""})
    r = dt._default_translate("材质：实木\n尺寸：80cm")
    assert r["ok"] and r["provider"] == "papago" and r["tencent"]["message"].startswith("不支持")
    r2 = dt._default_translate("重量：5kg")
    assert r2["ok"] and calls == {"tc": 1, "chain": 2}                   # 10분 동안 텐센트를 다시 부르지 않는다
    assert r2["tencent"] == {"skipped": "언어쌍 미지원 — 건너뜀"}


def test_unsupported_pair_does_not_bisect(monkeypatch, state):
    """51줄 → 언어쌍 미지원은 쪼개도 같은 답 — 묶음 하나에 1회만(예전: 반으로 4단 = 최대 16회)."""
    import src.uploaders.detail_translate as dt
    dt._CACHE.clear(); dt._FAIL.clear()
    n = {"c": 0}

    def fn(text):
        n["c"] += 1
        return dict(UNSUP)

    monkeypatch.setattr(dt, "retry_sec", lambda: 3600)
    lines = [f"规格{i}：参数{i}" for i in range(51)]
    out = dt.translate_leftover("\n".join(lines), translate_fn=fn)
    assert n["c"] == 1 and out["failed"] == 51
    dt._CACHE.clear(); dt._FAIL.clear()


def test_tencent_ok_is_used_as_is(monkeypatch, state):
    import src.uploaders.detail_translate as dt
    monkeypatch.setattr(dt, "_PAIR_DOWN", {"at": 0.0, "message": ""})
    monkeypatch.setattr(dt, "_tencent", lambda t: {"ok": True, "text": "소재: 원목"})
    monkeypatch.setattr(dt, "_chain", lambda t: pytest.fail("체인을 부르면 안 된다"))
    assert dt._default_translate("材质：实木")["provider"] == "tencent"


def test_chain_echo_is_not_success(monkeypatch):
    """체인이 원문을 그대로 돌려주면(stub·fallback) 성공이 아니다 — 가짜 번역 0."""
    import src.uploaders.detail_translate as dt

    class T:
        def translate_product(self, src):
            return {"provider": "stub", "description_ko": src["description"]}

    monkeypatch.setattr("src.seller_console.ai.translator.AITranslator", T)
    assert dt._chain("材质：实木")["ok"] is False


def test_call_records_provider(monkeypatch, state):
    import src.uploaders.detail_translate as dt
    dt._call("材质：实木", lambda t: {"ok": True, "text": "소재: 원목", "provider": "papago",
                                    "tencent": {"why": "InvalidParameterValue", "message": "不支持的语种：zh_to_ko"}})
    row = state[dt.RECENT_KEY]["rows"][-1]
    assert row["provider"] == "papago" and row["tencent"]["message"].startswith("不支持") and "lines_diag" not in row


# ── 2(a). 사전검증 마진 = 등록 마진 ───────────────────────────────────────────────────────────────

def test_prevalidate_sends_slider_margin_and_server_applies():
    pv = (TPL / "collect_preview.html").read_text(encoding="utf-8")
    i = pv.index("fetch('/seller/collect/prevalidate'")
    assert "target_margin_pct: _kgpMarginPct()" in pv[i:i + 600]      # 서버 적용은 아래 기능 계약(`_pv_prepare`)이 잰다


def test_pv_prepare_applies_margin():
    from src.order_webhook import app
    from src.seller_console import views
    with app.test_request_context("/"):
        pd, _rc = views._pv_prepare({"target_margin_pct": 40}, {"title": "t", "images": []})
    assert pd["target_margin_pct"] == 40.0


# ── 1. 드로어 맨 위 「마켓 등록본」 · 4마켓 상태 한 번에 ─────────────────────────────────────────

def test_market_records_block_sits_at_drawer_top_with_auto_status():
    pv = (TPL / "collect_preview.html").read_text(encoding="utf-8")
    assert pv.index('data-role="cp-live"') < pv.index('class="kgp-etabs"')          # 탭 위 = 상시 위치
    assert "{% set ml_auto = true %}" in pv[pv.index('data-role="cp-live"'):pv.index('class="kgp-etabs"')]
    m5 = (TPL / "_m5_flow.html").read_text(encoding="utf-8")
    assert '{% set ml_auto = true %}{% include "_market_listings.html" %}' in m5
    ml = (TPL / "_market_listings.html").read_text(encoding="utf-8")
    assert 'data-auto-status="{{ ml_item }}"' in ml and "/market-status'" in ml and 'data-role="ml-sub"' in ml


def test_popup_shows_live_and_detail_sync_and_product_page_label():
    ms = (TPL / "_market_status.html").read_text(encoding="utf-8")
    assert 'data-role="mst-live"' in ms and 'data-role="mst-detail-sync"' in ms and 'data-role="mst-live-name"' in ms
    assert ">상품 페이지 열기</a>" in ms and "구매자 화면" not in ms


def test_live_line():
    from src.seller_console.listing_status import live_line
    assert live_line({"detail_lines": 51, "detail_images": 28, "items": 16, "images": 9, "category": "77834"}) == \
        "지금 쿠팡에 올라간 내용: 상세 글 51줄 · 상세 이미지 28장 · 옵션 16개 · 대표·추가 이미지 9장 · 카테고리 77834"
    assert live_line(None) == "" and live_line({}) == ""


def test_naver_link_even_when_not_on_sale(monkeypatch):
    import src.seller_console.listing_status as MS
    import src.uploaders.naver_uploader as NU

    class U:
        def __init__(self, account=None):
            pass

        def _api_request(self, m, path):
            return {"originProduct": {"statusType": "WAIT"}, "smartstoreChannelProduct": {"channelProductNo": 13813465384}}

        def product_url(self, ch):
            return f"https://smartstore.naver.com/x/products/{ch}"

    monkeypatch.setattr(NU, "NaverSmartStoreUploader", U)
    row = MS._naver({"product_id": "99", "account": "shegoga", "channel_product_no": "13813465384"})
    assert row["link"].endswith("13813465384") and row["manage_label"] == "판매자센터 열기"


def test_sync_line_states():
    from src.services.coupang_detail_refresh import sync_line
    q = [{"item_id": "it", "market": "coupang:gogane", "reason": "번역 대기", "tries": 0}]
    assert sync_line({}, "coupang:gogane", "it", q) == "상세 갱신 대기 — 번역 대기"
    assert sync_line({}, "smartstore:shegoga", "it", q) == ""
    ex = {"coupang_detail_sync": {"coupang:woojoo": {"ok": True, "state": "승인완료"}}}
    assert sync_line(ex, "coupang:woojoo", "it", []) == "새 상세를 쿠팡에 보냈어요(다시 심사)"
    ex = {"coupang_detail_sync": {"coupang:woojoo": {"ok": False, "error": "조회 실패"}}}
    assert sync_line(ex, "coupang:woojoo", "it", []).startswith("상세 갱신 실패")
