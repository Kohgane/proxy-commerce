"""src/ai/forbidden_terms.py — AI 카피 금지어 필터 (Phase 134).

의료/의약품 표현, 과장 표현, 비교 광고, 가격 허위 표현 등 검출.
매칭 시 경고 + 자동 순화 제안.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class ForbiddenMatch:
    """금지어 매칭 결과."""

    term: str
    category: str
    suggestion: str
    context: str = ""


# ---------------------------------------------------------------------------
# 금지어 사전 (term, category, suggestion)
# ---------------------------------------------------------------------------

_FORBIDDEN: List[Tuple[str, str, str]] = [
    # 의료/의약품
    ("치료", "의료", "케어"),
    ("예방", "의료", "관리"),
    ("효능", "의료", "효과"),
    ("치유", "의료", "케어"),
    ("질병", "의료", "피부 고민"),
    ("항균", "의료", "청결"),
    ("살균", "의료", "청결"),
    ("의약품", "의료", "제품"),
    ("처방", "의료", "추천"),
    ("임상", "의료", "테스트"),
    ("부작용", "의료", "주의사항"),
    # 과장
    ("최고", "과장", "인기"),
    ("1위", "과장", "베스트셀러"),
    ("세계 최초", "과장", "신제품"),
    ("절대", "과장", ""),
    ("완벽", "과장", "만족스러운"),
    ("무조건", "과장", "안심"),
    ("100%", "과장", "고품질"),
    # 비교광고
    ("타사 대비", "비교", ""),
    ("경쟁사", "비교", ""),
    ("OO보다", "비교", ""),
    # 가격 허위
    ("원가", "가격허위", "구매가"),
    ("실제가", "가격허위", "정상가"),
    ("정품 보장", "가격허위", "정품"),
    # 국내법 금지
    ("다이어트", "법규", "체형 관리"),
    ("살빼기", "법규", "체형 관리"),
    ("지방 분해", "법규", "관리"),
    ("피부 재생", "법규", "피부 개선"),
]

# 패턴 컴파일 (대소문자 무시, 공백 허용)
_COMPILED = [
    (re.compile(re.escape(term), re.IGNORECASE), term, category, suggestion)
    for term, category, suggestion in _FORBIDDEN
]


def check_forbidden_terms(text: str) -> List[ForbiddenMatch]:
    """텍스트에서 금지어 검출.

    Args:
        text: 검사할 텍스트

    Returns:
        ForbiddenMatch 목록 (빈 리스트 = 이상 없음)
    """
    matches: List[ForbiddenMatch] = []
    found_terms = set()

    for pattern, term, category, suggestion in _COMPILED:
        if term in found_terms:
            continue
        for m in pattern.finditer(text):
            if term in found_terms:
                break
            start = max(0, m.start() - 10)
            end = min(len(text), m.end() + 10)
            context = text[start:end]
            matches.append(ForbiddenMatch(
                term=term,
                category=category,
                suggestion=suggestion,
                context=context,
            ))
            found_terms.add(term)

    return matches


def apply_suggestions(text: str, matches: List[ForbiddenMatch]) -> str:
    """금지어를 제안어로 자동 대체.

    제안어가 없는 경우 금지어를 그대로 유지.

    Args:
        text: 원본 텍스트
        matches: check_forbidden_terms() 결과

    Returns:
        순화된 텍스트
    """
    result = text
    for match in matches:
        if match.suggestion:
            result = re.sub(
                re.escape(match.term),
                match.suggestion,
                result,
                flags=re.IGNORECASE,
            )
    return result


def warnings_to_list(matches: List[ForbiddenMatch]) -> List[str]:
    """ForbiddenMatch 목록을 경고 문자열 목록으로 변환."""
    return [
        f"[{m.category}] '{m.term}' → '{m.suggestion}' 로 교체 권장 (…{m.context}…)"
        if m.suggestion
        else f"[{m.category}] '{m.term}' 사용 금지 (…{m.context}…)"
        for m in matches
    ]
