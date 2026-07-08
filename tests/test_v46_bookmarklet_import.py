"""tests/test_v46_bookmarklet_import.py — v46 STEP4: 북마클릿 가져오기 실패 수리(URL 경량화).

진단: HTML 이스케이프는 정상(원시 큰따옴표/&/<> 0)이었고, 실패 원인은 #441이 공유 추출기(~20KB)를
인라인해 javascript: URL이 29KB가 된 것 → 크롬 '북마크 가져오기'가 그 거대 URL을 못 받음.
수리: 북마클릿 경량화(≈3KB) — 클라는 og메타+대표이미지+페이지 HTML만 보내고 서버가 추출. partial 판정도
서버 응답(d.partial). NETSCAPE 파일/ICON/이스케이프는 유지.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
API = Path("src/api/extension_api.py").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _mem():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    yield


def test_bookmarklet_url_is_import_safe():
    from src.seller_console.views import _bookmarklet_js
    js = _bookmarklet_js("https://kohganepercentiii.com", "TOK", True)
    # 29KB(추출기 인라인) → 경량. 크롬 북마크 가져오기가 받도록 넉넉히 작게.
    assert len(js) < 6000, f"bookmarklet 너무 큼: {len(js)}"
    assert "kgpExtractProduct" not in js               # 29KB 추출기 인라인 폐기
    assert "html:(document.documentElement" in js       # 페이지 HTML을 서버로(서버가 추출)


def test_netscape_file_valid_and_escaped():
    from src.seller_console.views import _bookmarklet_js, _netscape_bookmark
    js = _bookmarklet_js("https://x.com", "T", True)
    nb = _netscape_bookmark(js, "data:image/png;base64,ABCD")
    assert nb.startswith("<!DOCTYPE NETSCAPE-Bookmark-file-1>")   # 헤더 정확
    assert 'ICON="data:image/png;base64,' in nb                  # 아이콘 고정
    import re
    href = re.search(r'HREF="(.*?)" ICON', nb, re.S).group(1)
    assert '"' not in href                                        # 원시 큰따옴표 0(이스케이프됨)
    assert not re.search(r'&(?!amp;|quot;|lt;|gt;|#)', href)      # 원시 & 0
    assert "<" not in href and ">" not in href                   # 원시 <> 0


def test_bookmarklet_js_is_valid(tmp_path):
    from src.seller_console.views import _bookmarklet_js
    js = _bookmarklet_js("https://x.com", "T", False)
    f = tmp_path / "bm.js"
    f.write_text(js[len("javascript:"):], encoding="utf-8")
    out = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr


def test_server_sets_partial_for_empty(client=None):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            # 가격·이미지 없음 → 서버가 partial=true 응답(북마클릿 정직 표기용)
            r = c.post("/api/v1/collect/extension", data=json.dumps({"url": "https://x.com/g-1", "title": "t"}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            d = r.get_json()
            assert d.get("ok") is True and d.get("partial") is True
            # 가격 있으면 partial=false
            r2 = c.post("/api/v1/collect/extension", data=json.dumps({"url": "https://x.com/g-2", "title": "t2", "price": "20605", "currency": "KRW"}),
                        content_type="application/json", headers={"Authorization": "Bearer t"})
            assert r2.get_json().get("partial") is False


def test_source_contract():
    assert '"partial": _partial' in API                  # 서버 응답 partial 필드
    assert "d&&d.ok&&d.partial" in VIEWS                  # 북마클릿이 서버 partial로 정직 표기
