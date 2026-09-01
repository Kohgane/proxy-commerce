"""tests/test_m1_taobao_probe.py — 프로브 스크립트의 **순수 로직**만 검증.

네트워크 층(L1~L3)은 이 컨테이너에서 못 돈다 — 에이전트 프록시가 타오바오 계열 CONNECT를
403으로 막는다(실측: 전 호스트 HTTP 000). 그래서 프로브는 **오너 서버에서 돌리는 도구**이고,
여기서는 서버에 가기 전에 틀리면 안 되는 것(서명·URL 승격·커버리지 판정)만 못박는다.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("taobao_probe", "scripts/taobao_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def test_mtop_signature_matches_public_algorithm():
    """★ md5(token & t & appKey & data) — 공개 알고리즘 그대로. 틀리면 L2가 통째로 헛돈다."""
    token, t, key, data = "abc123", "1700000000000", "12574478", '{"itemNumId":"1"}'
    expected = hashlib.md5(f"{token}&{t}&{key}&{data}".encode()).hexdigest()
    assert probe._mtop_sign(token, t, key, data) == expected


@pytest.mark.parametrize("url,expected", [
    ("https://item.taobao.com/item.htm?id=666666666666", "666666666666"),
    ("https://detail.tmall.com/item.htm?spm=a1z&id=12345678", "12345678"),
    ("https://world.taobao.com/item/987654321.htm", "987654321"),
    ("https://item.taobao.com/item.htm", ""),          # 못 뽑으면 빈 문자열(추측 금지)
])
def test_item_id_extraction(url, expected):
    assert probe._item_id(url) == expected


@pytest.mark.parametrize("thumb,origin", [
    ("https://gw.alicdn.com/bao/uploaded/abc_430x430q90.jpg",
     "https://gw.alicdn.com/bao/uploaded/abc.jpg"),
    ("https://img.alicdn.com/x/def_800x800.jpg", "https://img.alicdn.com/x/def.jpg"),
    ("https://gw.alicdn.com/x/ghi_60x60q75.png", "https://gw.alicdn.com/x/ghi.png"),
])
def test_l5_origin_promotion(thumb, origin):
    """L5 — alicdn 크기 접미 제거(라쿠텐 동형 규칙)."""
    assert probe.strip_alicdn_suffix(thumb) == origin


def test_l5_leaves_plain_urls_alone():
    """접미가 없으면 건드리지 않는다 — 멀쩡한 URL을 망가뜨리지 않는다."""
    u = "https://gw.alicdn.com/bao/uploaded/plain.jpg"
    assert probe.strip_alicdn_suffix(u) == u


def test_coverage_reads_signals_not_guesses():
    """커버리지는 **신호가 있을 때만** True — 없으면 False(빈 판정을 O로 올리지 않는다)."""
    empty = probe._coverage_from_html("<html></html>")
    assert set(empty) == set(probe.FIELDS) and not any(empty.values())

    rich = probe._coverage_from_html(
        '<div class="tb-main-title"></div>{"price":"19.9"}{"skuBase":{}}{"skuId":"1"}'
        '<img src="https://gw.alicdn.com/bao/uploaded/a_430x430q90.jpg">descUrl')
    assert all(rich.values()), rich


def test_block_markers_cover_login_and_captcha():
    """로그인 벽·캡차 신호를 잡아야 '뚫렸다'고 오판하지 않는다."""
    for m in ("login.taobao.com", "captcha", "FAIL_SYS_USER_VALIDATE"):
        assert m in probe._BLOCK_MARKERS


def test_probe_does_not_use_login_credentials():
    """★ 게스트 전용 — 계정 쿠키·자격을 태우지 않는다(차단 위험 + 서버 수집은 어차피 게스트)."""
    src = Path("scripts/taobao_probe.py").read_text(encoding="utf-8")
    for banned in ("TAOBAO_COOKIE", "password", "login(", "os.getenv"):
        assert banned not in src, banned


def test_network_failure_is_reported_not_swallowed():
    """네트워크가 막히면 **사유를 담아** 반환한다 — 조용히 빈 결과로 넘기지 않는다."""
    out = probe._probe_l1("https://item.taobao.com/item.htm?id=1", timeout=1)
    assert out["layer"].startswith("L1")
    assert out.get("error") or out.get("status") is not None
