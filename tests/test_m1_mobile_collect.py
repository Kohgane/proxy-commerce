"""tests/test_m1_mobile_collect.py — M1-1: 모바일 단건 수집 엔드포인트.

**왜 새 엔드포인트인가(실측 근거):** 기존 진입점 셋 중 어느 것도 단축어·봇을 받지 못한다.
  · `/seller/collect/quick`·`/collect/share` → **로그인 세션** 필요(단축어·봇엔 세션이 없다)
  · `/api/v1/collect/bulk` → 토큰은 되지만 **비동기**(job_id 폴링)
  · `/api/v1/collect/extension` → 확장이 만든 페이로드(제목·이미지·HTML) 전제
그래서 **토큰 + 동기 + 단건**이 필요했다. 수집 코어는 벌크와 공유한다(이중 구현 금지).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.api import extension_api as api


@pytest.fixture
def client():
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_store():
    from src.seller_console import collect_history_store as store
    store._in_memory.clear()
    yield
    store._in_memory.clear()


def _auth(monkeypatch, user_id="u1"):
    monkeypatch.setattr(api, "_require_token",
                        lambda scopes=None: {"user_id": user_id, "email": f"{user_id}@x.kr"})


class _Draft:
    title = "PopSockets 그립톡"
    images = ["https://x/a.jpg"]
    price = "19900"
    currency = "KRW"


def test_route_exists_and_requires_token(client):
    """토큰 없으면 401 — 세션 쿠키로는 열리지 않는다(봇·단축어 전용 경로)."""
    r = client.post("/api/v1/collect/one", json={"url": "https://x.com/dp/1"})
    assert r.status_code == 401
    assert r.get_json()["ok"] is False


@pytest.mark.parametrize("send", ["json", "form", "query"])
def test_accepts_url_from_any_shape(client, monkeypatch, send):
    """★ 단축어가 만들기 쉬운 형태를 다 받는다 — JSON · form · 쿼리."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    url = "https://www.amazon.com/dp/B0TEST0001"
    if send == "json":
        r = client.post("/api/v1/collect/one", json={"url": url})
    elif send == "form":
        r = client.post("/api/v1/collect/one", data={"url": url})
    else:
        r = client.post(f"/api/v1/collect/one?url={url}")
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] is True, d
    assert d["item_id"] and d["title"] == "PopSockets 그립톡"


def test_extracts_url_from_shared_text(client, monkeypatch):
    """공유 시트가 제목·본문만 줄 때 거기서 URL을 건져 낸다(기존 share와 동형)."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    r = client.post("/api/v1/collect/one",
                    json={"text": "이거 봐봐 https://item.rakuten.co.jp/shop/abc 괜찮네"})
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_rejects_non_url_honestly(client, monkeypatch):
    _auth(monkeypatch)
    r = client.post("/api/v1/collect/one", json={"url": "그냥 텍스트"})
    assert r.status_code == 400 and "URL" in r.get_json()["error"]


def test_failure_is_honest_not_fake_success(client, monkeypatch):
    """★ 수집 실패는 가짜 성공이 되지 않는다 — 사유를 담아 502."""
    _auth(monkeypatch)

    def _boom(u):
        raise RuntimeError("봇 차단(403)")
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: _boom)
    r = client.post("/api/v1/collect/one", json={"url": "https://x.com/dp/1"})
    d = r.get_json()
    assert r.status_code == 502 and d["ok"] is False
    assert "봇 차단" in d["error"]                    # 원문이 올라온다
    assert "확장" in d["message"]                     # 다음 행동을 알려준다


def test_duplicate_uses_existing_normalized_key(client, monkeypatch):
    """중복 방지는 **기존 정규화 키**(v42 1-3)를 쓴다 — 새 규칙을 만들지 않는다."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    url = "https://www.amazon.com/dp/B0TEST0002"
    first = client.post("/api/v1/collect/one", json={"url": url}).get_json()
    assert first["ok"] and not first["duplicate"]
    # 같은 상품, 트래킹 파라미터만 다른 URL → 같은 키로 잡힌다.
    again = client.post("/api/v1/collect/one",
                        json={"url": url + "?ref=sr_1_3&keywords=grip"}).get_json()
    assert again["ok"] is True and again["duplicate"] is True
    assert again["item_id"] == first["item_id"]


def test_collect_core_is_shared_with_bulk():
    """★ 이중 구현 금지 — 벌크와 단건이 **같은 코어**를 부른다.

    벌크 안에 있던 `process_url`을 모듈 레벨 `collect_one_url`로 끌어올렸고,
    벌크는 그걸 감싸기만 한다. 수집 로직이 두 벌 생기면 한쪽만 고쳐진다.
    """
    src = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert src.count("def collect_one_url") == 1
    assert "return collect_one_url(url, seller_id=seller_id_val" in src   # 벌크가 위임
    assert 'collect_one_url(url, seller_id=seller_id, source="mobile")' in src  # 단건이 위임
    # 벌크·단건 어느 쪽도 이력 저장을 **직접** 하지 않는다 — 코어만 한다.
    bulk = src.split("def _run_bulk_job")[1].split("@extension_bp")[0]
    one = src.split("def collect_one()")[1].split("@extension_bp")[0]
    for name, body in (("bulk", bulk), ("one", one)):
        assert "history_append" not in body, f"{name}이 이력 저장을 따로 한다"


def test_durable_gate_survived(client, monkeypatch):
    """영속 저장이 확인될 때만 ok — v38 P0 게이트가 새 경로에도 살아 있다."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: ("id-1", False))      # 비영속
    r = client.post("/api/v1/collect/one", json={"url": "https://x.com/dp/9"})
    assert r.status_code == 502 and "영속" in r.get_json()["error"]


# ── M1-2: 파이프 연결 — 수집이 수집 이력에서 끝나지 않는다 ────────────────────
# 폰에서 소싱할 때 필요한 건 '수집됨'이 아니라 **취급 가능한가 · 얼마에 팔리나**다.
# 판정은 콘솔 화면과 같은 배선(`build_review_for_urls`)을 그대로 탄다.

def test_m1_2_review_is_opt_in(client, monkeypatch):
    """기본은 수집만 — `review=1`을 줘야 판정이 붙는다(느린 판정을 강요하지 않는다)."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    d = client.post("/api/v1/collect/one", json={"url": "https://x.com/dp/10"}).get_json()
    assert d["ok"] is True and "review" not in d


@pytest.mark.parametrize("send", ["json", "query"])
def test_m1_2_review_verdict_rides_the_pipe(client, monkeypatch, send):
    """★ 수집한 URL이 **등록 파이프 검수표를 그대로 통과**해 판정이 돌아온다."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    monkeypatch.setattr("src.seller_console.views.build_review_for_urls",
                        lambda urls, cap=50: {
                            "review_pass": [{"title_ko": "그립톡", "excluded": False,
                                             "cost_krw": 9000, "sale_krw": 19900,
                                             "margin_pct": 27.4, "net_krw": 5400,
                                             "ship_status": "배송가능", "ship_reason": "실측",
                                             "warnings": []}],
                            "excluded": [], "failed": []})
    url = "https://x.com/dp/11"
    if send == "json":
        r = client.post("/api/v1/collect/one", json={"url": url, "review": 1})
    else:
        r = client.post(f"/api/v1/collect/one?url={url}&review=1")
    rv = r.get_json()["review"]
    assert rv["ok"] is True and rv["verdict"] == "검수 통과"
    assert rv["sale_krw"] == 19900 and rv["margin_pct"] == 27.4
    assert rv["ship_status"] == "배송가능"


def test_m1_2_excluded_carries_reason(client, monkeypatch):
    """취급 제외도 **사유와 함께** 올라온다 — 조용한 탈락 금지."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    monkeypatch.setattr("src.seller_console.views.build_review_for_urls",
                        lambda urls, cap=50: {
                            "review_pass": [],
                            "excluded": [{"title_ko": "가품 의심", "excluded": True,
                                          "forbidden_detail": {"kind_ko": "금지어",
                                                               "term": "레플리카"},
                                          "warnings": []}],
                            "failed": []})
    rv = client.post("/api/v1/collect/one",
                     json={"url": "https://x.com/dp/12", "review": 1}).get_json()["review"]
    assert rv["verdict"] == "취급 제외" and "레플리카" in rv["reason"]


def test_m1_2_review_failure_does_not_break_collect(client, monkeypatch):
    """판정이 터져도 **수집 성공은 성공이다** — 판정 실패만 정직하게 알린다."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    monkeypatch.setattr("src.seller_console.views.build_review_for_urls",
                        lambda urls, cap=50: (_ for _ in ()).throw(RuntimeError("환율 조회 불가")))
    d = client.post("/api/v1/collect/one",
                    json={"url": "https://x.com/dp/13", "review": 1}).get_json()
    assert d["ok"] is True and d["item_id"]              # 수집은 살아 있다
    assert d["review"]["ok"] is False and "환율" in d["review"]["error"]


def test_m1_2_review_wiring_is_single_source():
    """★ 이중 구현 금지 — 콘솔 화면과 모바일 API가 **같은 조립**을 부른다.

    환율·금지어·채널을 붙이는 배선이 두 벌이면 한쪽만 갱신된다.
    """
    views = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert views.count("def build_review_for_urls") == 1
    assert views.count("build_source_review(") == 1      # 조립은 헬퍼 안에서만
    assert "review = build_review_for_urls(raw_urls)" in views    # 콘솔 라우트가 위임
    api_src = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert "build_review_for_urls" in api_src and "build_source_review" not in api_src


# ── M1-4: 단축어 가이드 — 셀러가 실제로 따라 할 수 있는가 ─────────────────────

def test_m1_4_shortcut_guide_is_in_app_and_actionable(monkeypatch):
    """가이드는 **화면 안**에 있고, 그대로 따라 하면 되는 값만 담는다."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    html = app.test_client().get("/seller/extension").get_data(as_text=True)
    assert "단축어" in html
    for needed in ("/api/v1/collect/one", "POST", "Authorization", "Bearer",
                   "/seller/me/tokens", "review"):
        assert needed in html, needed


def test_m1_4_guide_hides_developer_surface():
    """★ 일반 유저 화면에 개발 표기 금지 — 환경변수·문서 경로·내부 모듈명 0."""
    tpl = Path("src/seller_console/templates/extension_install.html").read_text(encoding="utf-8")
    for leaked in ("TELEGRAM_COLLECT", "SELLER_ID", "docs/", "src/", "collect_one_url"):
        assert leaked not in tpl, leaked


def test_m1_4_doc_covers_failure_paths():
    """문서(운영자용)는 **실패 경로**까지 적는다 — 가짜 성공을 기대하게 두지 않는다."""
    doc = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    for topic in ("401", "400", "502", "봇 차단", "duplicate", "review"):
        assert topic in doc, topic
    # 텔레그램 잠금 3종이 문서에 다 있어야 오너가 설정할 수 있다.
    for env in ("TELEGRAM_COLLECT_WEBHOOK_SECRET", "TELEGRAM_COLLECT_CHAT_IDS",
                "TELEGRAM_COLLECT_SELLER_ID"):
        assert env in doc, env
    assert "토큰은 비밀번호와 같습니다" in doc      # 유출 주의 안내
