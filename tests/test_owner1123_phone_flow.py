"""오너 11-23 B 「폰 수집 → 등록 한 줄기」 PR2.

계약:
- 수집 탭: 링크 → 같은 화면에서 진행 한 줄 → 끝나면 그 상품 카드(M5 /seller/m/item/<id>) — `/collect/quick?fmt=json`.
  실패는 그 자리에 한국어 사유 + 다음 행동 하나(다시 수집 · 한도면 요금제). JS 없으면 예전 결과 화면(form GET) 그대로.
- 카드 탭 → M5(PR1) · 폰에서 3,330줄 서랍(collect_preview)을 안 연다.
- M5 실패 줄: 보이는 글자만 바꾼다 — 아는 영어 조각은 한국어, 예외 클래스 이름(URLError 등) 제거, 원문은 「원문」에 접고,
  고칠 버튼이 없으면 다음 행동 하나(키 문제 → 마켓 연동 · 그 밖 → 그 마켓만 다시 사전검증). 판정·전송 로직 불변.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

M5 = Path("src/seller_console/templates/_m5_flow.html")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


def test_quick_collect_json_points_to_m5_card(client, monkeypatch):
    from src.seller_console import views as V
    monkeypatch.setattr(V, "_quick_collect", lambda url, source="", share_raw="": {
        "ok": True, "message": "수집했어요", "item_id": "abc123", "status": 200})
    r = client.get("/seller/collect/quick?fmt=json&u=https://item.taobao.com/item.htm?id=1")
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["next"] == "/seller/m/item/abc123" and d["item_id"] == "abc123"


def test_quick_collect_json_failure_is_honest(client, monkeypatch):
    from src.seller_console import views as V
    monkeypatch.setattr(V, "_quick_collect", lambda url, source="", share_raw="": {
        "ok": False, "message": "이 사이트는 서버에서 읽을 수 없어요 — PC 확장으로 수집해 주세요.", "status": 422})
    r = client.get("/seller/collect/quick?fmt=json&u=https://x")
    d = r.get_json()
    assert r.status_code == 422 and d["ok"] is False and d["next"] == "" and "PC 확장" in d["message"]


def test_quick_collect_html_unchanged_without_fmt(client, monkeypatch):
    from src.seller_console import views as V
    monkeypatch.setattr(V, "_quick_collect", lambda url, source="", share_raw="": {
        "ok": True, "message": "수집했어요", "item_id": "abc123", "status": 200})
    html = client.get("/seller/collect/quick?u=https://x").get_data(as_text=True)
    assert "수집 완료" in html                                                   # 북마클릿 결과 화면 그대로


def test_collect_tab_stays_and_goes_to_card():
    html = Path("src/seller_console/templates/mobile_home.html").read_text(encoding="utf-8")
    assert "fetch('/seller/collect/quick?fmt=json&u=' + encodeURIComponent(u)" in html
    assert "location.href = d.next" in html and "window.kgpJobLine.show('수집 중" in html
    assert 'data-role="m-collect-result"' in html and 'data-role="m-collect-retry"' in html
    assert 'action="/seller/collect/quick" method="get"' in html                 # JS 없으면 예전 흐름


def _m5_funcs() -> str:
    src = M5.read_text(encoding="utf-8")
    start = src.index("function esc(s)")
    end = src.index("  // Z10-C: 잡조차 못 띄운 줄")
    stop = src.index("function nextAction(r)")
    stop = src.index("\n  }\n", stop) + 4
    return src[start:end] + src[end:stop] if stop > end else src[start:stop]


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
@pytest.mark.parametrize("raw, want, has_raw", [
    ("쿠팡 카테고리 메타 확인 못 함 — 다시 확인 (카테고리 76001 · Missing Coupang API credentials)",
     "쿠팡 카테고리 메타 확인 못 함 — 다시 확인 (카테고리 76001 · 쿠팡 API 키가 연결돼 있지 않아요)", True),
    ("판정 못 함 — 이미지를 내려받지 못했습니다 (URLError)", "판정 못 함 — 이미지를 내려받지 못했습니다", True),
    ("The request was rejected because the product category does not allow this attribute value",
     "마켓이 받아들이지 않았어요 — 아래 「원문」을 확인해 주세요", True),
    ("배송비가 판매가의 40%를 넘어요", "배송비가 판매가의 40%를 넘어요", False),
])
def test_m5_reasons_become_korean_raw_kept_folded(raw, want, has_raw):
    js = _m5_funcs() + f"""
    ;var h = humanReason({json.dumps(raw)});
    console.log(JSON.stringify(h));
    console.log(reasonHtml({json.dumps(raw)}));"""
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    lines = out.stdout.strip().splitlines()
    assert len(lines) == 2, out.stderr
    h = json.loads(lines[0])
    assert h["text"] == want and bool(h["raw"]) is has_raw
    assert ("<summary>원문</summary>" in lines[1]) is has_raw
    if has_raw:
        assert re.search(r"Error\b|Missing Coupang", lines[1].split("<details")[0]) is None   # 본문엔 영어 원문·코드 없음


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_m5_next_action_one_button():
    js = _m5_funcs() + """
    ;console.log(nextAction({market: 'coupang', message: 'Missing Coupang API credentials', details: []}));
    console.log(nextAction({market: 'smartstore', message: '판정 못 함', hint: '', details: []}));"""
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
    assert 'href="/seller/markets/connect/coupang"' in out[0] and "마켓 키 연결하기" in out[0]
    assert 'data-role="m5-retry-market" data-market="smartstore"' in out[1] and "다시 사전검증" in out[1]
    src = M5.read_text(encoding="utf-8")
    assert "if (!r.ok && h.indexOf('class=\"m5-fix\"') < 0 && h.indexOf('data-role=\"m5-cat-pick\"') < 0) h += nextAction(r);" in src


def test_m5_precheck_and_register_drive_the_job_line():
    src = M5.read_text(encoding="utf-8")
    assert "'사전검증 중 — 마켓 ' + (pvOrder.length - pvPending.length) + '/' + pvOrder.length + '곳'" in src
    assert "window.kgpJobLine.show('등록 중 — ' + targets.length + '곳')" in src
    assert "window.kgpJobLine.done('등록 끝 — ' + _ok + '곳 등록됨')" in src
    # 11-25 ①c: 마켓마다 한 줄 — 요청 실패도 그 마켓 줄의 사유(reasonHtml)로 그린다
    assert "message: (d.error || '등록하지 못했어요')" in src and "reasonHtml(r.message || '')" in src


def test_coupang_preview_notes_use_korean_reason_too():
    """같은 유형: 쿠팡 미리보기 카드의 보류·메모 줄도 사유 줄과 같은 번역(영어 원문은 「원문」에 접음)."""
    src = M5.read_text(encoding="utf-8")
    assert "notes.map(function (n) { return '<li>' + reasonHtml(n) + '</li>'; })" in src
    assert "notes.map(function (n) { return '<li>' + esc(n) + '</li>'; })" not in src


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
@pytest.mark.parametrize("raw, want, has_raw", [
    ("이미지를 내려받지 못했습니다(URLError)", "이미지를 내려받지 못했습니다", True),
    ("이미지를 내려받지 못했습니다(HTTPError · HTTP 403)", "이미지를 내려받지 못했습니다 (HTTP 403)", True),
    ("이미지를 내려받지 못했습니다(URL 접근 가능 여부 확인).", "이미지를 내려받지 못했습니다(URL 접근 가능 여부 확인).", False),
])
def test_coupang_check_line_hides_exception_names(raw, want, has_raw):
    """같은 유형: 쿠팡 노출 미리보기의 「판정 못 함」 줄 — 예외 이름은 보이는 글에서 빼고 원문은 title에."""
    src = Path("src/seller_console/templates/_coupang_exposure.html").read_text(encoding="utf-8")
    a = src.index("  function cpxWhy(s) {")
    b = src.index("  function checkLines(c) {")
    js = src[a:b] + f";var r = cpxWhy({json.dumps(raw)}); console.log(JSON.stringify(r));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    r = json.loads(out.stdout.strip())
    assert r["text"] == want and bool(r["raw"]) is has_raw, out.stderr
