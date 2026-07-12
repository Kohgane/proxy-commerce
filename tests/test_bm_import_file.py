"""tests/test_bm_import_file.py — 북마클릿 파일 받기 라우트(크롬 가져오기 + ICON 속성).

POST /seller/bookmarklet/file → 토큰 발급(Supabase 1단계, 폴백 시 인메모리) 후 NETSCAPE
북마크 HTML(ICON=브릿지 base64 + javascript 수집 코드) 다운로드. 토큰 저장 실패면 파일도 실패(정직).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
            s["user_email"] = "demo@goga.kr"
        yield c


@pytest.fixture
def token_ok(monkeypatch):
    # 토큰 저장소(Supabase/Sheets) 미설정 환경에서 파일 생성 로직만 결정적으로 검증.
    from src.auth import personal_tokens as pt
    monkeypatch.setattr(pt, "generate_token",
                        lambda **k: {"raw_token": "tok_test123", "expires_at": "2027-01-01T00:00:00Z"})


def test_download_netscape_file_with_icon(client, token_ok):
    r = client.post("/seller/bookmarklet/file", data={"translate": "1"})
    assert r.status_code == 200
    assert "text/html" in r.headers.get("Content-Type", "")
    cd = r.headers.get("Content-Disposition", "")
    assert "attachment" in cd and "filename" in cd
    body = r.get_data(as_text=True)
    assert "<!DOCTYPE NETSCAPE-Bookmark-file-1>" in body
    assert 'HREF="javascript:(function' in body            # 수집 코드 baked
    assert 'ICON="data:image/png;base64,' in body          # 브릿지 마크 아이콘 고정
    # v49 STEP3: 앵커 텍스트=가시 문자열 '고가수집'(제로폭 U+200B는 가져오기 후 이름이 투명/빈칸으로
    #   보여 못 찾는 버그의 근원 → 오너 실기기 확정. 이제 이름이 또렷이 보인다).
    assert "></A>" in body  # v56: 앵커 텍스트 빈 문자열(오너 요청 — 파비콘만 표시)
    assert "​</A>" not in body                          # 제로폭 폐기(투명 이름 버그 박멸)
    assert "translate:true" in body or "translate:" in body                        # 번역 ON 반영
    # v59 STEP1: HREF는 퍼센트 인코딩 → 엔티티(&quot; 등) 0개, 큰따옴표는 %22로. (엔티티 SyntaxError 근절)
    import re as _re
    _href = _re.search(r'<A HREF="([^"]*)"', body).group(1)
    assert _href.count("&") == 0, "HREF에 & 잔존(엔티티 방식 회귀)"
    assert "%22" in _href                                   # 큰따옴표 퍼센트 인코딩
    assert "/api/v1/collect/extension" in body             # 서버 수집 엔드포인트


def test_translate_off_reflected(client, token_ok):
    r = client.post("/seller/bookmarklet/file", data={"translate": "0"})
    body = r.get_data(as_text=True)
    assert "TR=false" in body  # v56: 코어가 TR 변수로 번역 반영


def test_token_save_failure_no_file(client, monkeypatch):
    from src.auth import personal_tokens as pt
    def _boom(*a, **k):
        raise RuntimeError("시트 잠금(429)")
    monkeypatch.setattr(pt, "generate_token", _boom)
    r = client.post("/seller/bookmarklet/file", data={"translate": "1"})
    assert r.status_code == 503
    d = r.get_json()
    assert d and d.get("ok") is False and "파일" in d.get("error", "")


def test_source_contract():
    v = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert '@bp.post("/bookmarklet/file")' in v
    assert "_netscape_bookmark" in v and "_bridge_icon_data_uri" in v
