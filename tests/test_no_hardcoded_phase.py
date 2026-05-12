"""tests/test_no_hardcoded_phase.py — AI 화면 Phase 하드코딩 회귀 방지."""
from __future__ import annotations

import os


def test_no_hardcoded_phase_in_ai_templates():
    root = os.path.dirname(os.path.dirname(__file__))
    targets = [
        os.path.join(root, "src", "ai_listing", "routes.py"),
        os.path.join(root, "src", "dashboard", "admin_views.py"),
    ]

    forbidden_literals = [
        "Phase 149</small>",  # /seller/listing/ai-create 헤더
        "AI 상품등록 자동화 (Phase 149)",  # /admin/diagnostics AI 카드
        "Phase 149 mock status",  # routes.py api_status 응답
    ]
    offenders: list[str] = []
    for path in targets:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if any(token in content for token in forbidden_literals):
            offenders.append(path)

    assert not offenders, f"AI 화면에 하드코딩 Phase 문구가 남아있습니다: {offenders}"
