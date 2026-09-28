"""M3 — 폰 1탭 수집(공유 시트) · M3-iOS 아이폰 단축어(오너 2026-09-28).

  ① 아이폰 단축어: `GET /seller/collect/share?text=<공유 입력>` → 붙여넣기와 **같은 판단점**(`collect_input`) →
     결과 화면(제목·가격·「PC 고가수집기가 켜지면 상세 보강」) · 응답 200
  ② 단축어가 URL 인코딩 없이 붙여 공유 글 속 `&`로 쿼리가 갈라져도 원문을 되살린다
  ③ 미로그인 → 로그인 → **같은 주소로** 복귀
  ④ 안드로이드 PWA share_target = POST 폼(title·text·url). 다른 사이트의 POST(위조)는 거절
  ⑤ 중복 · 링크 없음 — 정직한 결과 화면(빈 행 0)
  ⑥ 안내 1페이지(아이폰 단축어 3단계 · iCloud 배포 1줄 · 안드로이드 · 텔레그램 대안)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs

import pytest

SHARE = ("【淘宝】https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt CZ356\n"
         "「新中式双人书桌靠墙长条桌简约现代学生写字学习桌实木办公电脑桌」\n"
         "点击链接直接打开 或者 淘宝搜索直接打开")                    # 오너 실물 형식(test_c_share_text와 같은 원문)


@pytest.fixture
def client(monkeypatch):
    from src.collectors import link_diag
    # 이 환경은 e.tb.cn에 못 나간다 — 단축 링크는 「못 폈다」로 둔다(초안은 제목·tk로 선다).
    monkeypatch.setattr(link_diag, "resolve_short_link", lambda url: {"ok": False, "reason": "offline"})
    from src.order_webhook import app
    return app.test_client()


def _login(c, seller):
    with c.session_transaction() as s:
        s["user_id"] = seller


def _rows(seller):
    from src.seller_console import collect_history_store as S
    return [r for r in S.list_items(seller_ids={seller}, days=30, limit=50) or []]


def test_iphone_shortcut_get_makes_one_cny_draft_waiting_for_enrich(client, monkeypatch):
    seller = "u-m3-ios"
    _login(client, seller)
    r = client.get("/seller/collect/share?text=" + quote(SHARE))
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'data-state="draft"' in body and "新中式双人书桌" in body
    assert 'data-role="share-enrich"' in body and "PC 고가수집기가 켜지면" in body
    rows = _rows(seller)
    assert len(rows) == 1
    ex = json.loads(rows[0]["extra_json"])
    assert rows[0]["currency"] == "CNY" and ex["currency"] == "CNY"
    assert ex["enrich_state"] == "pending" and ex["mode"] == "share" and ex["share_tk"] == "nyXpT7VA7lt"
    # 5부 큐 — PC 고가수집기가 집는 자리
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": seller})
    pend = client.get("/api/v1/collect/enrich/pending").get_json()
    assert rows[0]["id"] in {p["item_id"] for p in pend["items"]}


def test_unencoded_ampersand_is_recovered(client):
    """단축어가 인코딩 없이 붙이면 `…?tk=X&un=1 「제목」`이 `text=…?tk=X` + `un=1 「제목」`으로 갈라진다."""
    seller = "u-m3-amp"
    _login(client, seller)
    raw = "【淘宝】https://e.tb.cn/h.AMPtest?tk=AmpTok1&un=abc 「实木书桌」 点击链接直接打开"
    r = client.get("/seller/collect/share?text=" + raw.replace(" ", "%20").replace("「", "%E3%80%8C").replace("」", "%E3%80%8D"))
    assert r.status_code == 200 and 'data-state="draft"' in r.get_data(as_text=True)
    ex = json.loads(_rows(seller)[0]["extra_json"])
    assert ex["title"] == "实木书桌" and ex["share_tk"] == "AmpTok1"      # 제목이 & 뒤에 있어도 살아남는다


def test_not_logged_in_goes_to_login_and_comes_back(client, monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_AUTH_ENABLED", True)
    r = client.get("/seller/collect/share?text=" + quote(SHARE), follow_redirects=False)
    assert r.status_code in (301, 302)
    nxt = parse_qs(urlparse(r.headers["Location"]).query)["next"][0]
    assert nxt.startswith("/seller/collect/share?text=") and "tk%3DnyXpT7VA7lt" in nxt.replace("tk=", "tk%3D")
    from src.auth.views import _safe_next_url
    assert _safe_next_url(nxt) == nxt                                  # 로그인 뒤 그 주소로 그대로 간다
    # 로그인한 셈 치고 그 주소를 열면 담긴다
    monkeypatch.setattr(V, "_AUTH_ENABLED", False)
    seller = "default"
    before = len(_rows(seller))
    r2 = client.get(nxt)
    assert r2.status_code == 200 and 'data-state="draft"' in r2.get_data(as_text=True)
    assert len(_rows(seller)) == before + 1


def test_android_post_form_and_forged_post_is_refused(client):
    seller = "u-m3-android"
    _login(client, seller)
    r = client.post("/seller/collect/share", data={"title": "淘宝", "text": SHARE.replace("CZ356", "CZ357"),
                                                   "url": ""}, headers={"Sec-Fetch-Site": "none"})
    assert r.status_code == 200 and 'data-state="draft"' in r.get_data(as_text=True)
    assert len(_rows(seller)) == 1
    bad = client.post("/seller/collect/share", data={"text": SHARE.replace("nyXpT7VA7lt", "Forged01")},
                      headers={"Sec-Fetch-Site": "cross-site"})
    assert bad.status_code == 403 and len(_rows(seller)) == 1           # 위조 POST는 한 줄도 안 만든다


def test_duplicate_and_no_link_are_honest(client):
    seller = "u-m3-dup"
    _login(client, seller)
    client.get("/seller/collect/share?text=" + quote(SHARE))
    r = client.get("/seller/collect/share?text=" + quote(SHARE))
    assert 'data-state="duplicate"' in r.get_data(as_text=True) and len(_rows(seller)) == 1
    r = client.get("/seller/collect/share?text=" + quote("그냥 메모 글자"))
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and 'data-state="failed"' in body and 'data-role="share-error"' in body
    assert len(_rows(seller)) == 1                                       # 빈 행을 만들지 않는다


def test_manifest_share_target_is_post_form():
    for fn in ("manifest.json", "manifest.webmanifest"):
        st = json.loads((Path("src/seller_console/static") / fn).read_text(encoding="utf-8"))["share_target"]
        assert st == {"action": "/seller/collect/share", "method": "POST",
                      "enctype": "application/x-www-form-urlencoded",
                      "params": {"title": "title", "text": "text", "url": "url"}}


def test_phone_guide_page(client, monkeypatch):
    _login(client, "u-m3-guide")
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("IOS_SHORTCUT_URL", raising=False)
    html = client.get("/seller/guide/phone").get_data(as_text=True)
    assert "https://kohganepercentiii.com/seller/collect/share?text=[단축어 입력]" in html
    for s in ("공유 시트에 표시", "URL · 텍스트", "URL 열기", "고가브릿지로 수집", "iCloud 링크 복사",
              "앱 설치", "@gogaBridz_bot", "/link 토큰"):
        assert s in html, s
    assert html.count('data-role="guide-step-') == 3 and 'data-role="shortcut-link"' not in html
    monkeypatch.setenv("IOS_SHORTCUT_URL", "https://www.icloud.com/shortcuts/abc")
    assert 'href="https://www.icloud.com/shortcuts/abc"' in client.get("/seller/guide/phone").get_data(as_text=True)
    for tpl in ("guide_phone.html", "collect_share_result.html"):
        t = Path("src/seller_console/templates/" + tpl).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", t) and not re.search(r"[\U0001F300-\U0001FAFF]", t)
