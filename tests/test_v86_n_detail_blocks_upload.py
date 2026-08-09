"""tests/test_v86_n_detail_blocks_upload.py — v86-N: 드로어 '상세페이지 꾸미기' 블록이
실제 마켓 등록에 반영되게 배선.

배경: collect_preview 드로어의 v40-C 블록 에디터(마켓별 프리셋 + 미리보기)는 detail_blocks를
저장(views.py)했지만, 업로드 경로(upload_dispatcher → channel bridge)가 **detail_blocks를
소비하지 않아** 상세 꾸미기가 마켓 등록에서 유실됐다(저장-후-미사용 = 정직 데이터 결함).
채널 브리지(to_collected)는 description_html or description만 보므로 블록은 어디에도 안 갔다.

수리: upload_dispatcher._payload_for_market가 detail_blocks(마켓 오버라이드 else 공통)를
description_html로 렌더 → 브리지가 이를 사용 → coupang/smartstore/11st 등록 상세에 실반영.
드로어 미리보기(dpPreview)와 동일 시맨틱이라 '미리보기=실제 등록물'.
"""
from __future__ import annotations

from src.seller_console.upload_dispatcher import (
    UploadDispatcher,
    render_detail_blocks_html,
)
from src.channel_sync._channel_bridge import to_collected


def test_renderer_block_semantics_and_escaping():
    blocks = {
        "common": [
            {"type": "text", "content": "튼튼한 <소재> & 방수"},
            {"type": "highlight", "content": "무료배송"},
            {"type": "image", "content": "https://img.example/a.jpg?x=1&y=2"},
            {"type": "divider", "content": ""},
        ]
    }
    html = render_detail_blocks_html(blocks, "coupang")
    # 시맨틱: text=<p>, highlight=<div>, image=<img>, divider=<hr>
    assert "<p " in html and "<div " in html and "<img " in html and "<hr" in html
    # 내용은 전부 이스케이프(마크업 주입 0) — <소재>가 리터럴 태그로 새지 않는다.
    assert "&lt;소재&gt;" in html and "&amp;" in html
    assert "<소재>" not in html
    assert "https://img.example/a.jpg?x=1&amp;y=2" in html


def test_renderer_empty_and_bad_input_returns_blank():
    assert render_detail_blocks_html(None, "coupang") == ""
    assert render_detail_blocks_html({}, "coupang") == ""
    assert render_detail_blocks_html({"common": []}, "coupang") == ""
    # 공백만 있는 텍스트/이미지는 렌더 0(가짜 빈 블록 방지).
    assert render_detail_blocks_html({"common": [{"type": "text", "content": "   "}]}, "coupang") == ""


def test_market_override_else_common():
    blocks = {
        "common": [{"type": "text", "content": "공통 상세"}],
        "coupang": [{"type": "text", "content": "쿠팡 전용 상세"}],
    }
    assert "쿠팡 전용 상세" in render_detail_blocks_html(blocks, "coupang")
    # 오버라이드 없는 마켓은 공통을 사용.
    assert "공통 상세" in render_detail_blocks_html(blocks, "smartstore")
    assert "쿠팡 전용 상세" not in render_detail_blocks_html(blocks, "smartstore")


def test_payload_for_market_injects_description_html_from_blocks():
    product = {
        "title": "테스트 백팩",
        "price": "39000",
        "currency": "KRW",
        "description": "간단한 원문 설명",
        "detail_blocks": {"common": [{"type": "text", "content": "블록 상세 본문"}]},
    }
    payload, _ = UploadDispatcher._payload_for_market(product, "coupang")
    assert "블록 상세 본문" in (payload.get("description_html") or "")
    # 브리지가 그 description_html을 사용(블록이 plain description을 이긴다 — 셀러 명시적 꾸미기).
    collected = to_collected(payload)
    assert "블록 상세 본문" in collected["description_html"]
    assert "간단한 원문 설명" not in collected["description_html"]


def test_no_blocks_keeps_plain_description_fallback_no_regression():
    product = {
        "title": "테스트 백팩",
        "price": "39000",
        "currency": "KRW",
        "description": "원문 설명 유지",
    }
    payload, _ = UploadDispatcher._payload_for_market(product, "coupang")
    # 블록 없으면 description_html 미설정 → 브리지가 plain description 폴백(기존 동작 유지).
    assert not payload.get("description_html")
    collected = to_collected(payload)
    assert collected["description_html"] == "원문 설명 유지"


def test_empty_blocks_do_not_clobber_plain_description():
    product = {
        "title": "테스트 백팩",
        "price": "39000",
        "currency": "KRW",
        "description": "원문 설명",
        "detail_blocks": {"common": []},   # 에디터 열었다 빈 채로 저장
    }
    payload, _ = UploadDispatcher._payload_for_market(product, "coupang")
    assert not payload.get("description_html")
    assert to_collected(payload)["description_html"] == "원문 설명"
