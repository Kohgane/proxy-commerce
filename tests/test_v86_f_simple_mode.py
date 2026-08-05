"""tests/test_v86_f_simple_mode.py — v86-F: 목록 타일 간이 수집을 정직하게 표기.

■ 오너 지적
아마존 목록 타일 수집이 `mode:'full'`로 저장된다 — 실제로는 **제목·이미지(+목록가)뿐**인데
상세페이지 수집분과 목록에서 구별이 안 된다(정직 데이터 위반: '간이' 뱃지가 안 뜬다).

■ 수리 방침
1. 확장 타일 경로(`kgpQuickCollect` 단건 / 벌크)가 `mode:'simple'`을 실어 보낸다 — 단일 헬퍼 1곳.
2. **서버가 그 값을 그대로 믿지 않는다.** 구버전 확장·mode를 빠뜨린 새 호출부에서 같은 사고가
   조용히 재발하므로, 상세·옵션·스펙·갤러리가 전부 비면 서버가 간이로 **강등**한다.
   (반대로 올리진 않는다 — 클라가 간이라고 했으면 간이. 보수적 방향만 허용.)
3. 보강(enrich)이 실제로 상세를 채우면 간이를 해제한다 — 안 그러면 뱃지가 영구히 남아 소음이 된다.
4. 콘솔 '간이' 뱃지는 core(북마클릿)·simple(타일) 두 모드 모두에 뜬다. 판정은 한 곳에서만 정의한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.api.extension_api import SIMPLE_COLLECT_MODES, _resolve_collect_mode

CS = Path("extensions/chrome-collector/content_script.js")


# ── 1. 확장: 타일 경로가 mode:'simple'을 싣는다 ───────────────────────────────

def test_tile_payload_forces_simple_mode():
    src = CS.read_text(encoding="utf-8")
    assert "function _kgpTileMeta(" in src, "타일 페이로드 단일 헬퍼가 없다"
    seg = src.split("function _kgpTileMeta(", 1)[1].split("\n}", 1)[0]
    assert 'mode: "simple"' in seg, "타일 페이로드에 mode:'simple' 미강제"


def test_both_tile_paths_use_the_single_helper():
    """단건(호버 수집)·벌크(선택/전체 수집) 두 경로가 같은 헬퍼를 쓴다 — 두 벌이면 한쪽만 또 샌다."""
    src = CS.read_text(encoding="utf-8")
    assert src.count("_kgpTileMeta(") >= 3, ("정의 1 + 호출 2가 아니다", src.count("_kgpTileMeta("))
    # 옛 인라인 리터럴이 남아 있으면 그 경로는 여전히 mode 없이 나간다.
    assert "{ url: card.url, title: card.title, image: card.image" not in src, \
        "단건 경로에 인라인 페이로드 잔존(헬퍼 미경유)"


# ── 2. 서버: 클라 주장이 아니라 실체로 판정 ───────────────────────────────────

def test_tile_like_payload_is_downgraded_even_when_client_says_full():
    """★핵심 — 구버전 확장이 full이라 주장해도 제목+이미지뿐이면 간이로 강등."""
    payload = {"mode": "full", "title": "Stainless Tumbler",
               "images": ["https://m.media-amazon.com/images/I/71a.jpg"], "price": "24.99"}
    assert _resolve_collect_mode(payload) == "simple", "타일형 페이로드가 full로 저장된다(원 사고 재발)"


@pytest.mark.parametrize("field,value", [
    ("description", "이 텀블러는 이중벽 진공 단열로 12시간 보온됩니다. 뚜껑은 분리 세척 가능."),
    ("options", [{"name": "색상", "values": ["블랙", "실버"]}]),
    ("detail_specs", [{"k": "용량", "v": "30oz"}]),
    ("gallery_images", ["https://x/1.jpg", "https://x/2.jpg"]),
    ("detail_images", ["https://x/d1.jpg"]),
    ("reviews", [{"text": "좋아요"}]),
])
def test_substantive_payload_stays_full(field, value):
    """상세·옵션·스펙·갤러리 중 하나라도 실체가 있으면 full 유지 — 과잉 강등 금지."""
    payload = {"mode": "full", "title": "T", "images": ["https://x/a.jpg"], field: value}
    assert _resolve_collect_mode(payload) == "full", (f"{field}가 있는데 간이로 강등됐다", payload)


def test_multiple_images_alone_counts_as_full():
    """갤러리를 여러 장 받았으면 타일 수집이 아니다(타일은 대표 1장)."""
    payload = {"mode": "full", "title": "T", "images": ["https://x/a.jpg", "https://x/b.jpg"]}
    assert _resolve_collect_mode(payload) == "full"


def test_price_alone_does_not_rescue_from_simple():
    """가격은 목록 카드에도 실린다 — '상세를 받았다'의 근거가 못 된다."""
    payload = {"mode": "full", "title": "T", "images": ["https://x/a.jpg"],
               "price": "24.99", "currency": "USD"}
    assert _resolve_collect_mode(payload) == "simple"


@pytest.mark.parametrize("mode", sorted(SIMPLE_COLLECT_MODES))
def test_client_declared_simple_is_never_upgraded(mode):
    """클라가 간이라고 하면 실체가 풍부해도 간이 유지 — 강등 방향만 허용(보수적)."""
    payload = {"mode": mode, "title": "T", "description": "x" * 80,
               "options": [{"name": "색상"}], "images": ["a", "b", "c"]}
    assert _resolve_collect_mode(payload) == mode


def test_bookmarklet_core_mode_preserved():
    """v81 북마클릿 코어 폴백은 'core' 그대로 — 'simple'로 뭉개면 원인 구분이 사라진다."""
    assert _resolve_collect_mode({"mode": "core", "title": "T"}) == "core"


# ── 3. 보강되면 간이 해제 ─────────────────────────────────────────────────────

def test_enrich_clears_simple_only_when_fields_actually_filled():
    """보강 큐가 돌기만 하고 못 채웠으면 간이 유지 — 가짜 승격 금지."""
    api = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    seg = api.split("extra[\"enriched\"] = True", 1)[1].split("_upd = {", 1)[0]
    assert "SIMPLE_COLLECT_MODES" in seg, "보강 후 간이 해제 로직이 없다 — 뱃지가 영구 잔존"
    assert "if changed" in seg, "채운 게 없어도 승격한다 — 가짜 성공"


# ── 4. 콘솔 '간이' 뱃지 ───────────────────────────────────────────────────────

def test_console_badge_covers_both_simple_modes():
    views = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    seg = views.split('it["is_core"]', 1)[0][-400:]
    assert "SIMPLE_COLLECT_MODES" in seg, "뱃지 판정이 리터럴 비교 — 모드 집합과 두 벌이 된다"
    assert 'it["collect_mode"]' in views, "어느 간이인지 템플릿이 구분할 값이 없다"


def test_badge_tooltip_distinguishes_tile_from_bookmarklet():
    """같은 '간이'라도 원인이 다르다 — 타일은 확장 정상 동작, 북마클릿은 수집기 미로드."""
    rows = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    assert "{% if it.is_core %}" in rows and "간이" in rows
    assert "it.collect_mode == 'simple'" in rows, "타일 간이에도 '확장 미로드' 문구가 뜬다(오안내)"
    assert "목록 타일에서 간이 수집" in rows
