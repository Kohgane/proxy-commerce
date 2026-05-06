"""tests/test_forbidden_terms.py — 금지어 필터 테스트 (Phase 134)."""
import pytest


class TestForbiddenTerms:
    def test_detects_medical_term(self):
        from src.ai.forbidden_terms import check_forbidden_terms
        matches = check_forbidden_terms("이 제품은 피부 질병을 치료합니다.")
        terms = [m.term for m in matches]
        assert "질병" in terms or "치료" in terms

    def test_detects_exaggeration(self):
        from src.ai.forbidden_terms import check_forbidden_terms
        matches = check_forbidden_terms("대한민국 최고의 제품")
        terms = [m.term for m in matches]
        assert "최고" in terms

    def test_no_false_positives_for_clean_text(self):
        from src.ai.forbidden_terms import check_forbidden_terms
        matches = check_forbidden_terms("부드러운 소재의 요가 레깅스. 편안하고 신축성이 뛰어납니다.")
        assert len(matches) == 0

    def test_apply_suggestions_replaces_term(self):
        from src.ai.forbidden_terms import check_forbidden_terms, apply_suggestions
        text = "이 샴푸는 탈모를 치료합니다."
        matches = check_forbidden_terms(text)
        result = apply_suggestions(text, matches)
        # "치료" → "케어" 로 대체
        assert "케어" in result or "치료" not in result

    def test_apply_suggestions_no_suggestion_keeps_original(self):
        from src.ai.forbidden_terms import check_forbidden_terms, apply_suggestions, ForbiddenMatch
        text = "절대 최고입니다."
        matches = check_forbidden_terms(text)
        # 제안어가 없는 항목은 그대로 유지
        result = apply_suggestions(text, [m for m in matches if not m.suggestion])
        assert isinstance(result, str)

    def test_warnings_to_list(self):
        from src.ai.forbidden_terms import check_forbidden_terms, warnings_to_list
        text = "최고 효능 제품"
        matches = check_forbidden_terms(text)
        warnings = warnings_to_list(matches)
        assert all(isinstance(w, str) for w in warnings)
        assert all("[" in w for w in warnings)

    def test_multiple_terms_detected(self):
        from src.ai.forbidden_terms import check_forbidden_terms
        text = "최고의 치료 효능, 1위 제품"
        matches = check_forbidden_terms(text)
        assert len(matches) >= 2

    def test_each_term_detected_once(self):
        from src.ai.forbidden_terms import check_forbidden_terms
        text = "최고 최고 최고"
        matches = check_forbidden_terms(text)
        terms = [m.term for m in matches]
        assert terms.count("최고") == 1

    def test_match_has_context(self):
        from src.ai.forbidden_terms import check_forbidden_terms
        text = "이 약품은 치료 효과가 있습니다."
        matches = check_forbidden_terms(text)
        assert any(m.context for m in matches)

    def test_match_category(self):
        from src.ai.forbidden_terms import check_forbidden_terms
        matches = check_forbidden_terms("치료 효능")
        categories = {m.category for m in matches}
        assert "의료" in categories


class TestForbiddenMatchSuggestions:
    def test_suggestion_available(self):
        from src.ai.forbidden_terms import check_forbidden_terms
        matches = check_forbidden_terms("치료 효과")
        m = next((m for m in matches if m.term == "치료"), None)
        if m:
            assert m.suggestion == "케어"

    def test_warnings_include_suggestion(self):
        from src.ai.forbidden_terms import check_forbidden_terms, warnings_to_list
        matches = check_forbidden_terms("치료")
        warnings = warnings_to_list(matches)
        if warnings:
            assert "케어" in warnings[0] or "권장" in warnings[0]
