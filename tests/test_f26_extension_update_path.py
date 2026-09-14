"""F26 계약 — 재로딩 안내가 갱신 안내인 척했다.

## 실측 (오너 2026-09-14)

콘솔 배너가 「`chrome://extensions`에서 새로고침하면 최신 추출기로 갱신됩니다」라고 적혀 있었다.
**거짓이다.** 압축해제 로드 확장은 **폴더 내용이 안 바뀌면** 새로고침해도 그대로다.
서버 zip이 새 버전이어도 로컬 폴더는 옛날 것이라, 사람은 새로고침을 반복하고
배너는 영원히 「낮아요」를 띄운다 — 오너는 8번 재설치했다.

## 그래서 재는 것

  ① 갱신 **경로**가 안내에 다 있는가(받기 → 덮어쓰기 → 새로고침).
  ② 콘솔이 아는 최신 버전과 zip 안 버전이 **같은 소스**에서 나오는가.
     두 벌이면 언젠가 갈리고, 갈리면 배너가 영원히 「낮아요」이거나 조용하다.
  ③ 버튼이 **어느 화면에서도** 한 클릭 거리인가(모바일 포함).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extensions/chrome-collector"


@pytest.fixture
def client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
    return c


# ---------------------------------------------------------------------------
# ① 갱신 경로가 안내에 다 있다
# ---------------------------------------------------------------------------

def test_banner_no_longer_claims_refresh_alone_updates():
    """「새로고침하면 갱신됩니다」는 **거짓**이었다 — 그 문장이 남아 있으면 안 된다."""
    tpl = (ROOT / "src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
    assert "새로고침(재로딩)하면 최신 추출기로 갱신됩니다" not in tpl
    # 세 단계가 다 있어야 사람이 실제로 갱신할 수 있다.
    seg = tpl.split("보다 낮아요", 1)[1][:900]
    assert "/seller/extension/download" in seg, "받는 길이 없다"
    assert "덮어쓰기" in seg, "덮어쓰라는 말이 없다 — 이게 빠져서 8번 재설치했다"
    assert "새로고침" in seg


def test_install_page_says_overwrite_too():
    tpl = (ROOT / "src/seller_console/templates/extension_install.html").read_text(encoding="utf-8")
    assert "덮어쓴" in tpl or "덮어쓰기" in tpl
    assert "새로고침만 하면" in tpl, "새로고침만으로 안 된다는 사실을 말하지 않는다"


# ---------------------------------------------------------------------------
# ② 버전은 한 소스에서 나온다
# ---------------------------------------------------------------------------

def test_console_version_delegates_to_the_zip_builder():
    """콘솔이 **zip을 만드는 그 코드**에 묻는다 — 읽는 코드를 두 벌로 두지 않는다."""
    src = (ROOT / "src/seller_console/views.py").read_text(encoding="utf-8")
    body = src.split("def _chrome_extension_version", 1)[1][:700]
    assert "from src.build_extension import read_version" in body
    assert "json.load" not in body, "manifest를 따로 또 읽고 있다(두 벌)"


def test_console_version_equals_zip_manifest_version(client):
    """콘솔이 말하는 최신 버전 == **실제 zip 안 manifest 버전**.

    어긋나면 배너가 영원히 「낮아요」이거나(콘솔이 높게 읽음),
    갱신이 있는데도 조용하다(콘솔이 낮게 읽음).
    """
    import io
    import zipfile
    from src.seller_console.views import _chrome_extension_version

    r = client.get("/seller/extension/download")
    assert r.status_code == 200, "zip 배포 경로가 죽었다"
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        in_zip = json.loads(z.read("manifest.json").decode("utf-8"))["version"]
    assert _chrome_extension_version() == in_zip


def test_zip_filename_carries_the_same_version(client):
    r = client.get("/seller/extension/download")
    from src.seller_console.views import _chrome_extension_version
    assert f"gogasujipgi-v{_chrome_extension_version()}.zip" in r.headers.get(
        "Content-Disposition", "")


def test_store_doc_does_not_hardcode_a_version():
    """게시 문서에 버전을 적어 두면 올릴 때마다 어긋난다 — manifest가 정본이다."""
    doc = (EXT / "STORE_LISTING.md").read_text(encoding="utf-8")
    assert not re.search(r"현재 main 버전 \*\*1\.\d+\.\d+\*\*", doc)
    assert "manifest.json`이 정본" in doc


# ---------------------------------------------------------------------------
# ③ 어느 화면에서도 한 클릭
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ua", [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1 Mobile/15E148",
])
def test_sidebar_button_renders_on_desktop_and_mobile(client, ua):
    """사이드바 버튼은 **렌더된 HTML에** 있어야 한다(CSS로 숨는지와 별개다).

    F21에서 로그아웃이 「지워진 게 아니라 닿을 수 없는 곳에」 있었다 — 같은 함정을 피한다.
    """
    r = client.get("/seller/collect/history", headers={"User-Agent": ua})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'class="kgp-extdl"' in html
    assert "/seller/extension/download" in html
    assert "고가수집기 다운로드" in html


def test_sidebar_button_shows_the_latest_version(client):
    from src.seller_console.views import _chrome_extension_version
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert f'data-latest="{_chrome_extension_version()}"' in html


def test_sidebar_help_has_all_three_steps():
    tpl = (ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    seg = tpl.split('id="kgpExtDlHelp"', 1)[1][:800]
    for step in ("압축 풀기", "덮어쓰기", "새로고침"):
        assert step in seg, f"{step} 단계가 없다"


def test_chrome_extensions_is_a_copy_button_not_a_link():
    """크롬은 `chrome://` 링크 클릭을 막는다 — 링크로 두면 눌러도 아무 일이 없다."""
    tpl = (ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    seg = tpl.split('id="kgpExtDlHelp"', 1)[1][:900]
    assert 'href="chrome://extensions"' not in seg
    assert "kgpExtDlCopy" in seg


def test_sidebar_styles_use_tokens_not_hardcoded_values():
    """하드코딩 hex/px 금지(app.css 토큰 단일 소스)."""
    css = (ROOT / "src/seller_console/static/console.css").read_text(encoding="utf-8")
    seg = css.split(".kgp-extdl-help {", 1)[1][:600]
    assert "var(--" in seg
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", seg), "하드코딩 hex"
