"""src/seller_console/i18n.py — 셀러 콘솔 경량 i18n (v15, 한국어 기본 + 영어 1급).

원칙(오너): 국내(ko) 우선, 영어(en)도 1급으로 동작. 모든 UI 문자열을 점진적으로 외부화한다.
- 언어 선택은 `kgp_lang` 쿠키(ko|en) — 기존 /i18n/set 라우트가 설정(단일 소스).
- `t(key, lang)` 로 문구를 가져온다. 키 없으면 키 자체를 반환(누락이 화면에 드러나 정직).
- 새 문자열은 STRINGS에 ko/en 쌍으로 추가 → 템플릿에서 {{ t('key') }} 로 사용.
"""
from __future__ import annotations

SUPPORTED = ("ko", "en")
DEFAULT_LANG = "ko"

# 핵심 UI 문자열(점진 확장). ko=국내 기본, en=영어 1급.
STRINGS: dict[str, dict[str, str]] = {
    # 공통/내비
    "nav.home": {"ko": "홈(대시보드)", "en": "Home (Dashboard)"},
    "nav.collect": {"ko": "상품 수집", "en": "Collect products"},
    "nav.history": {"ko": "수집 이력", "en": "Collection history"},
    "nav.orders": {"ko": "주문 관리", "en": "Orders"},
    "nav.markets": {"ko": "마켓 연동", "en": "Connect markets"},
    "nav.help": {"ko": "도움말·가이드", "en": "Help & guides"},
    "nav.advanced": {"ko": "고급 기능 더보기", "en": "More (advanced)"},
    # 공통 액션
    "action.save": {"ko": "저장", "en": "Save"},
    "action.cancel": {"ko": "취소", "en": "Cancel"},
    "action.confirm": {"ko": "확인", "en": "Confirm"},
    "action.next": {"ko": "다음", "en": "Next"},
    "action.prev": {"ko": "이전", "en": "Back"},
    "action.logout": {"ko": "로그아웃", "en": "Log out"},
    # For Beginners 고정 버튼
    "fb.cta": {"ko": "✨ 처음이신가요?", "en": "✨ New here?"},
    "fb.hide": {"ko": "가이드 버튼 숨기기", "en": "Hide guide button"},
    # 언어 토글
    "lang.korean": {"ko": "한국어", "en": "한국어"},
    "lang.english": {"ko": "English", "en": "English"},
    "lang.label": {"ko": "언어", "en": "Language"},
    # 수집 페이지
    "collect.title": {"ko": "상품 수집 → 등록", "en": "Collect → List products"},
    "collect.what_is": {
        "ko": "상품 수집이란?",
        "en": "What is product collection?",
    },
}


def normalize_lang(lang: str | None) -> str:
    lang = (lang or "").strip().lower()
    return lang if lang in SUPPORTED else DEFAULT_LANG


def t(key: str, lang: str | None = None) -> str:
    """키에 해당하는 현지화 문구. 키 미존재 시 키를 그대로 반환(누락이 보이게 — 정직)."""
    lng = normalize_lang(lang)
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lng) or entry.get(DEFAULT_LANG) or key
