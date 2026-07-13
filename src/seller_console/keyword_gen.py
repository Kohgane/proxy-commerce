"""src/seller_console/keyword_gen.py — v62 STEP4: 키워드 서버 생성(클라 추출 폐지).

저장 시 서버가 생성: 제목 핵심 명사구(브랜드·모델·용도) + 카테고리 + 옵션명 + 상세 빈출어.
불용어(도메인명·수식어·'Chat history'류 오염어) 필터. OPENAI 가용 시 정제, 미가용 시 규칙 기반.
"""
from __future__ import annotations

import re
from collections import Counter

from .category_classifier import CATEGORY_OPTIONS

# 카테고리 코드 → 한글 라벨(키워드용).
_CAT_KO = {code: label for code, label in CATEGORY_OPTIONS} if CATEGORY_OPTIONS else {}

# 불용어: 마케팅 수식어·일반어·단위·색상 일반어(상품명 특정성 낮음).
_STOPWORDS = {
    "the", "and", "for", "with", "new", "hot", "sale", "best", "premium", "official",
    "free", "shipping", "set", "pack", "pcs", "pc", "kit", "size", "color", "colour",
    "품질", "정품", "인기", "최고", "특가", "무료", "배송", "세트", "사이즈", "색상", "컬러",
    "상품", "제품", "판매", "구매", "추천", "신상", "할인", "이벤트", "옵션", "선택",
}
# 오염어(v60 스코프 공유): 확장 UI·페이지 크롬·도메인.
_CONTAM = re.compile(
    r"(chat\s*history|채팅\s*기록|고가수집|고가브릿지|gogabridj|kgp[-_ ]|사이드\s*패널|sidebar|assistant|"
    r"copilot|rufus|번역까지|수집\s*중|https?://|www\.|\.com\b|\.co\.[a-z]{2}|수집기|amazon\.com|temu\.com)",
    re.I,
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[가-힣]{2,}")


# 토큰 단위 오염어(제목이 토큰화되면 'Chat history'→'chat'+'history'로 쪼개져 구문 정규식이 못 잡음).
_CONTAM_TOKENS = {
    "chat", "history", "채팅", "기록", "sidebar", "assistant", "copilot", "rufus",
    "고가수집기", "고가수집", "고가브릿지", "gogabridj", "kgp", "수집기", "패널", "panel",
    "overlay", "widget", "extension", "확장",
}


def _is_contaminated(s: str) -> bool:
    if not s:
        return False
    if _CONTAM.search(str(s)):
        return True
    return str(s).strip().lower() in _CONTAM_TOKENS   # 토큰 단위 오염어


def _clean_token(t: str) -> str:
    t = (t or "").strip().strip(".,-_/|()[]{}").strip()
    return t


def _title_phrases(title: str) -> list:
    """제목에서 핵심 명사구 후보 — 브랜드(첫 토큰류)·모델(영숫자)·용도(한글 명사). 수식어 제외."""
    out, seen = [], set()
    toks = [_clean_token(t) for t in _TOKEN_RE.findall(title or "")]
    for t in toks:
        if not t or len(t) < 2:
            continue
        low = t.lower()
        if low in _STOPWORDS or _is_contaminated(t):
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def generate_keywords(title: str = "", category: str = "", options=None,
                      desc_text: str = "", brand: str = "", limit: int = 15) -> list:
    """규칙 기반 키워드 생성(우선순위: 제목 명사구 → 브랜드 → 카테고리 → 옵션명 → 상세 빈출어).
    오염어·불용어 필터, 중복 제거, 8~15개. (OPENAI 정제는 refine_keywords 훅에서.)"""
    kws, seen = [], set()

    def _add(v):
        v = _clean_token(v)
        if not v or len(v) < 2:
            return
        if v.lower() in _STOPWORDS or _is_contaminated(v):
            return
        key = v.lower()
        if key not in seen:
            seen.add(key)
            kws.append(v)

    # 1) 브랜드(있으면 최우선) + 제목 핵심 명사구
    if brand:
        _add(brand)
    for p in _title_phrases(title):
        _add(p)
    # 2) 카테고리 라벨
    cat_label = _CAT_KO.get(category, "")
    if cat_label:
        _add(cat_label)
    # 3) 옵션명(값 아님 — 옵션명이 상품 특성)
    for opt in (options or []):
        if isinstance(opt, dict) and opt.get("name"):
            _add(str(opt["name"]))
    # 4) 상세 빈출어(2회+ 등장한 의미 토큰)
    if desc_text:
        cnt = Counter()
        for t in _TOKEN_RE.findall(desc_text):
            t = _clean_token(t)
            if len(t) >= 2 and t.lower() not in _STOPWORDS and not _is_contaminated(t):
                cnt[t] += 1
        for t, n in cnt.most_common(30):
            if n >= 2:
                _add(t)
            if len(kws) >= limit:
                break
    return kws[:limit]


def refine_keywords(title: str, base_keywords: list) -> list:
    """OPENAI 가용 시 상품명 문맥으로 키워드 정제(선택). 미가용/실패 시 base 그대로(가짜 생성 0)."""
    import os
    try:
        from src.utils.env import env_present
    except Exception:
        env_present = lambda k: bool(os.getenv(k))   # noqa: E731
    if not env_present("OPENAI_API_KEY") or os.getenv("ADAPTER_DRY_RUN") == "1":
        return base_keywords
    try:
        import json as _json
        import requests as _req
        from src.utils.env import env_str
        prompt = (
            "다음 상품명과 후보 키워드로 한국 오픈마켓 검색 키워드 8~12개를 JSON 배열로 정제하세요. "
            "브랜드·모델·용도 위주, 마케팅 수식어·도메인·중복 제외.\n"
            f"상품명: {title}\n후보: {', '.join(base_keywords[:20])}\n"
            '형식: {"keywords":["..."]}'
        )
        r = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {env_str('OPENAI_API_KEY')}", "Content-Type": "application/json"},
            json={"model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.2, "max_tokens": 300,
                  "response_format": {"type": "json_object"}},
            timeout=12,
        )
        r.raise_for_status()
        data = _json.loads(r.json()["choices"][0]["message"]["content"])
        out = [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip() and not _is_contaminated(str(k))]
        return out or base_keywords
    except Exception:
        return base_keywords
