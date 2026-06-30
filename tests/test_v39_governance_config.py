"""tests/test_v39_governance_config.py — 프로젝트 거버넌스 파일 설치 + AI 상세 humanizer 의도.

오너 제공: .mcp.json(커넥터)·CLAUDE.md(지침)·디자인 스킬. AI 상세 생성은 humanizer 의도(사람처럼·번역체 금지) 적용.
"""
from __future__ import annotations

import json
from pathlib import Path


def test_mcp_json_present_no_secrets():
    p = Path(".mcp.json")
    assert p.exists(), ".mcp.json 누락"
    data = json.loads(p.read_text(encoding="utf-8"))
    servers = data.get("mcpServers", {})
    assert "apify" in servers and "cloudinary" in servers   # 수집 보강·이미지 변환 커넥터
    # 시크릿/토큰 하드코딩 0(키·시크릿 류 문자열 금지)
    blob = p.read_text(encoding="utf-8").lower()
    for bad in ("secret", "api_key", "apikey", "password", "token\""):
        assert bad not in blob, f".mcp.json에 시크릿 흔적: {bad}"


def test_claude_md_governance_and_memory_preserved():
    t = Path("CLAUDE.md").read_text(encoding="utf-8")
    # 거버넌스(지침) 블록
    assert "프로젝트 지침" in t
    assert "git·머지 규칙" in t and "셀프 점검" in t
    assert "gogabridj-design/SKILL.md" in t          # UI=디자인 스킬
    assert "humanizer" in t                          # 상세/카피=humanizer
    # 누적 작업 메모리(검증된 팩트) 보존
    assert "누적 작업 메모리" in t
    assert "Shopify" in t and "쿠팡" in t             # 기존 마켓 연동 팩트 보존


def test_design_skill_installed():
    s = Path(".claude/skills/gogabridj-design/SKILL.md")
    assert s.exists()
    body = s.read_text(encoding="utf-8")
    assert "디지털 한지 위의 금속활자" in body
    assert "name: gogabridj-design" in body


def test_ai_description_prompt_applies_humanizer_intent():
    src = Path("src/seller_console/ai/translator.py").read_text(encoding="utf-8")
    # 사람처럼·번역체/AI 티 금지 의도가 프롬프트에 명시
    assert "사람이 직접 쓴 것처럼" in src
    assert "번역체" in src
    assert "지어내지" in src                          # 없는 정보 날조 금지(정직)
