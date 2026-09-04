"""tests/test_v39_h_audit.py — v39 H: 전수 점검(CI 게이트). 같은 유형 결함을 전 화면에서 잡는다.

v39 신규 유형까지 횡단 점검:
  (a) 플레이스홀더 토큰 노출  (b) 좁은칸 라벨 세로 쪼개짐  (c) 새 창 이탈  (d) 아이콘/globe 잔재
  (e) PWA 설치/공유 동작  (f) 모바일 드로어 바텀시트  (g) 수집 상세 404 박멸

UI 변화 없는 가드 — 이 7개 PASS가 산출물(정직, before/after 캡처 없음).
"""
from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

import pytest

TPL = "src/seller_console/templates"
HIST = Path(f"{TPL}/collect_history.html").read_text(encoding="utf-8")
PREVIEW = Path(f"{TPL}/collect_preview.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


# (a) 플레이스홀더 토큰 — strip 동작 + 수집 경로 전수 적용 + 사용자 템플릿 리터럴 0
def test_a_placeholder_tokens_killed():
    from src.collectors.universal_scraper import strip_placeholder_tokens as strip
    assert strip("X {REGION_NAME - Temu Republic of Korea}") == "X"
    api = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    views = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert "strip_placeholder_tokens" in api and "strip_placeholder_tokens" in views
    # 사용자 노출 템플릿에 미치환 토큰 리터럴 잔존 0
    for f in glob.glob(f"{TPL}/*.html"):
        s = Path(f).read_text(encoding="utf-8")
        assert "{REGION_NAME" not in s and "%PRODUCT_NAME%" not in s, f


# (b) 좁은칸 라벨 세로 쪼개짐 — 마켓 선택은 균등 그리드 + nowrap, break-all은 마켓명에 미사용
def test_b_no_vertical_label_split():
    # ★ 6-c(2026-09-03): 마켓 타일 CSS가 템플릿 <style> → app.css로 이관됐다(소스만 교체).
    _css = Path("src/static/app.css").read_text(encoding="utf-8")
    assert "market-grid" in PREVIEW and "col-6 col-md-4" not in PREVIEW
    # 마켓명 라벨에 break-all(글자 단위 줄바꿈) 미사용 — break-all은 긴 URL/에러에만 허용
    name_block = _css.split(".market-tile .market-name")[1][:280]
    assert "white-space: nowrap" in name_block
    assert "break-all" not in name_block


# (c) 새 창 이탈 — 수집 목록 클릭=드로어(원본 도메인 새 탭 0)
def test_c_no_new_window_escape():
    assert "kgp-open-drawer" in HIST
    assert 'target="_blank" rel="noopener noreferrer">{{ it.domain' not in HIST


# (d) 아이콘/globe — favicon 브릿지(흰 배경 마크), 확장 FAB 신규 마크, globe 0
def test_d_icons_bridge_no_globe():
    fav = Path("src/seller_console/static/favicon.svg").read_text(encoding="utf-8")
    assert "bridge gateway mark" in fav and "globe" not in fav.lower()
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "globe" not in cs.lower() and 'fill="#ffffff"' in cs   # 신규 흰 배경 마크


# (e) PWA — manifest 고가브릿지·공유는 share 라우트·설치 버튼 연결
@pytest.mark.parametrize("fn", ["manifest.json", "manifest.webmanifest"])
def test_e_pwa_install_share(fn):
    m = json.loads(Path(f"src/seller_console/static/{fn}").read_text(encoding="utf-8"))
    assert m["name"] == "고가브릿지"
    assert m["background_color"] == "#f5efe3"
    assert m["share_target"]["action"] == "/seller/collect/share"


# (f) 모바일 드로어 — 바텀시트(아래→위) + 44px 터치 + sticky 액션바
def test_f_mobile_bottom_sheet():
    _css = Path("src/static/app.css").read_text(encoding="utf-8")
    assert "translateY(100%)" in _css                      # 아래에서 올라오는 바텀시트
    assert "border-radius: var(--radius-2xl) var(--radius-2xl) 0 0" in _css   # 6-c: 토큰화
    assert "kgp-action-bar" in PREVIEW and "min-height: 44px" in _css


# (g) 수집 상세 404 박멸 — 미존재도 200 '수집 실패'
def test_g_missing_preview_not_404(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.get("/seller/collect/preview/zzz-missing")
    assert r.status_code == 200 and "수집 실패" in r.get_data(as_text=True)
