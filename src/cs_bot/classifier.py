from __future__ import annotations

import re

KEYWORDS_KO = {
    "refund": ["환불", "취소", "반품", "돌려"],
    "shipping": ["배송", "언제", "도착", "운송장", "트래킹"],
    "size": ["사이즈", "치수", "크기", "맞나"],
    "stock": ["재고", "품절", "있나"],
    "general": [],
}
KEYWORDS_EN = {
    "refund": ["refund", "cancel", "return", "money back"],
    "shipping": ["shipping", "delivery", "tracking", "where"],
    "size": ["size", "fit", "measurement"],
    "stock": ["stock", "available", "out of"],
    "general": [],
}
KEYWORDS_JA = {
    "refund": ["返金", "キャンセル", "返品"],
    "shipping": ["配送", "発送", "追跡", "いつ"],
    "size": ["サイズ", "寸法"],
    "stock": ["在庫", "売り切れ"],
    "general": [],
}
KEYWORDS_ZH = {
    "refund": ["退款", "取消", "退货"],
    "shipping": ["配送", "物流", "什么时候"],
    "size": ["尺寸", "大小"],
    "stock": ["库存", "缺货"],
    "general": [],
}

PRIORITY_BY_CATEGORY = {
    "refund": 2,
    "shipping": 1,
    "size": 1,
    "stock": 1,
    "general": 0,
}


def detect_language(text: str) -> str:
    """문자 빈도 기반 빠른 감지."""
    src = text or ""
    if not src.strip():
        return "ko"

    if re.search(r"[\u3040-\u30ff]", src):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", src):
        return "ko"

    han = len(re.findall(r"[\u4e00-\u9fff]", src))
    latin = len(re.findall(r"[A-Za-z]", src))
    if han > 0 and latin == 0:
        return "zh"
    if latin > 0:
        return "en"
    return "ko"


def classify(text: str, language: str | None = None) -> tuple[str, int]:
    """카테고리 + priority 반환."""
    raw = (text or "").strip().lower()
    lang = language or detect_language(raw)
    table = {
        "ko": KEYWORDS_KO,
        "en": KEYWORDS_EN,
        "ja": KEYWORDS_JA,
        "zh": KEYWORDS_ZH,
    }.get(lang, KEYWORDS_KO)

    best_category = "general"
    best_score = 0
    for category, keywords in table.items():
        score = 0
        for keyword in keywords:
            kw = keyword.lower()
            if kw in raw:
                score += 2
        if score > best_score:
            best_score = score
            best_category = category

    priority = PRIORITY_BY_CATEGORY.get(best_category, 0)
    if best_category == "shipping":
        delayed_hints = ["48", "48h", "2일", "이틀", "지연", "늦", "late", "delayed"]
        if any(h in raw for h in delayed_hints):
            priority = 2
    return best_category, priority
