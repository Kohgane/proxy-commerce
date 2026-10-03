"""F53 — 쿠팡 전용 상품명(오너 2026-09-28).

실측(캐너리 16397045086): 쿠팡에 간 이름은 `[해외직구] ` + 번역 제목 앞 50자였다 — 번역 제목은 문장형에
검색어 나열이다(「수행 방패(SPORTLINK)는 애플 워치 충전 거치대 applewatch7 9용, S8 무선 iwatch 신형 Ultra2 …」).
쿠팡 규정: **브랜드 · 상품명(제품 유형) · 핵심 속성**, 조사·문장·중복 금지.

규칙형 생성(결정적 · 공짜 · 지어내지 않는다):
  브랜드   = 상품 brand 칸, 없으면 제목 괄호 속 라틴 이름(`(SPORTLINK)`)
  제품 유형 = 번역 제목 **첫 구절**의 한글 명사(조사 제거 · 「애플 워치」→「애플워치」 같은 붙임말)
  핵심 속성 = 옵션 원문 **전부에 공통**인 용어집 토큰(三合一 → 3in1) — 색상처럼 SKU마다 다른 건 속성이 아니다
  겸용     = 원문·번역 어디에든 **실제로 있는** 액세서리만(Airpods → 에어팟). 없는 걸 붙이지 않는다
  브랜드 위치 = 카테고리별 오너 설정(앞/뒤/생략) — `coupang_title_prefs`
다른 마켓 제목은 건드리지 않는다(쿠팡 이름은 따로 `coupang_name`).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)
import re
from typing import Any, Dict, Iterable, List, Optional

MAX_LEN = 100
BRAND_POS = ("front", "back", "omit")

# 띄어 번역되는 붙임말(쿠팡 검색 표기) — 두 토큰이 나란히 올 때만 붙인다.
COMPOUNDS = {("애플", "워치"): "애플워치", ("갤럭시", "워치"): "갤럭시워치", ("에어", "팟"): "에어팟",
             ("아이", "패드"): "아이패드", ("아이", "폰"): "아이폰", ("맥", "북"): "맥북"}
# 본문에 **있을 때만** 붙이는 겸용 액세서리(패턴 → 표기).
# 耳机(이어폰)은 **일반명사**라 넣지 않는다 — 블루투스 이어폰에 「에어팟 겸용」이 붙었다(계약이 잡음).
COMPAT = ((re.compile(r"air\s*pods?|에어\s*팟", re.I), "에어팟"),
          (re.compile(r"\bpencil\b|펜슬|触控笔|电容笔", re.I), "펜슬"))
_PARTICLE_TAIL = re.compile(r"(에서|으로|은|는|을|를|의|에|로|와|과|이|가|용)$")
_HANGUL_TOKEN = re.compile(r"^[가-힣]+$")
_BRAND_PAREN = re.compile(r"\(\s*([A-Za-z][A-Za-z0-9&\-. ]{1,30}?)\s*\)")

# ── 규칙 검사(사전검증 경고) ─────────────────────────────────────────────
_SENTENCE = re.compile(r"(?:[가-힣]{2,}|\))\s*(?:은|는|을|를|에서|으로)(?=[\s,]|$)")
_PREDICATE = re.compile(r"(?:입니다|합니다|해요|됩니다|하는|되는|있는|없는)(?=[\s,.]|$)")


def check_name(name: str) -> List[str]:
    """쿠팡 상품명 규칙 경고(보류 아님) — 문장형 · 검색어 나열 · 중복 · 길이."""
    s = str(name or "").strip()
    out: List[str] = []
    if not s:
        return ["상품명이 비어 있어요"]
    if _SENTENCE.search(s) or _PREDICATE.search(s):
        out.append("문장형이에요(조사·서술어) — 쿠팡은 「브랜드 + 상품명 + 핵심 속성」만 받아요")
    if s.count(",") + s.count("，") >= 2:
        out.append("쉼표로 검색어를 나열했어요 — 검색어는 검색 태그 칸으로")
    dups = _dup_tokens(s)
    if dups:
        out.append("같은 말이 반복돼요: " + ", ".join(dups[:4]))
    if len(s) > MAX_LEN:
        out.append(f"{MAX_LEN}자를 넘어요({len(s)}자)")
    return out


def _norm_tok(t: str) -> str:
    return re.sub(r"[^\w가-힣]", "", t).lower()


def _dup_tokens(s: str) -> List[str]:
    seen, dups = set(), []
    for t in re.split(r"[\s,/·|]+", s):
        k = _norm_tok(t)
        if len(k) < 2:
            continue
        if k in seen and k not in dups:
            dups.append(k)
        seen.add(k)
    return dups


# ── 재료 뽑기 ───────────────────────────────────────────────────────────
def brand_of(product: Dict[str, Any]) -> str:
    b = str(product.get("brand") or "").strip()
    if b:
        return b
    for key in ("title_original", "title_ko", "title"):
        m = _BRAND_PAREN.search(str(product.get(key) or ""))
        if m:
            return m.group(1).strip()
    return ""


def _strip_brand_chunk(title: str, brand: str) -> str:
    t = str(title or "")
    if brand:
        # 「수행 방패(SPORTLINK)는 」 — 음역 브랜드 + (원표기) + 조사를 통째로.
        t = re.sub(r"^[^,()]{0,16}\(\s*" + re.escape(brand) + r"\s*\)\s*(?:은|는|이|가)?\s*", "", t)
        t = re.sub(re.escape(brand), " ", t, flags=re.I)
    return t.strip(" ,")


# Q(2026-10-01): 「상품 유형 명사」 — 첫 구절에 이게 하나도 없으면(「자석 충전식 스마트폰」처럼 꾸밈말에서 끊김)
#   제목 뒤쪽에서 **처음 나오는** 유형 명사를 붙인다. 실측: 「…스마트폰·시계 무선 충전 거치대…」가 `·`에서 잘려
#   쿠팡명이 「자석 충전식 스마트폰」이 됐다(거치대가 빠짐). 첫 구절에 유형 명사가 있으면 지금 규칙 그대로.
TYPE_NOUNS = (
    "거치대", "충전기", "충전 패드", "스탠드", "받침대", "홀더", "케이스", "커버", "필름", "케이블", "어댑터", "허브",
    "이어폰", "헤드폰", "스피커", "마우스", "키보드", "램프", "조명", "무드등", "시계",
    "의자", "소파", "테이블", "책상", "선반", "수납장", "정리함", "수납함", "바구니", "옷걸이", "행거", "거울", "협탁", "침대",
    "매트", "쿠션", "베개", "이불", "커튼", "러그", "카페트",
    "가방", "백팩", "지갑", "파우치", "신발", "운동화", "슬리퍼", "샌들", "모자", "벨트",
    "셔츠", "티셔츠", "바지", "치마", "원피스", "재킷", "자켓", "코트", "니트", "후드",
    "컵", "텀블러", "머그", "접시", "그릇", "냄비", "프라이팬", "도마", "칼",
)


def _type_nouns_in(text: str) -> List[str]:
    found = []
    for n in TYPE_NOUNS:
        i = text.find(n)
        if i >= 0:
            found.append((i, n))
    return [n for _i, n in sorted(found)]


def product_type(title_ko: str, brand: str = "") -> str:
    """번역 제목 첫 구절의 한글 명사(조사 제거 · 붙임말 결합). 못 찾으면 빈 문자열."""
    body = _strip_brand_chunk(title_ko, brand)
    head = re.split(r"[,，/|·]", body, maxsplit=1)[0]
    toks: List[str] = []
    for raw in head.split():
        t = raw.strip("()[]{}「」'\"")
        if not _HANGUL_TOKEN.match(t):
            continue                                  # 「applewatch7」·「9용」 같은 검색어 조각은 유형이 아니다
        if len(t) > 2:
            t = _PARTICLE_TAIL.sub("", t) if len(_PARTICLE_TAIL.sub("", t)) >= 2 else t
        toks.append(t)
    if toks and not _type_nouns_in(" ".join(toks)):
        # 한국어 명사구는 **끝 명사가 머리**다(「·시계 무선 충전 거치대」의 머리는 거치대 — 시계는 충전 대상).
        #   첫 구절 다음 구간(다음 `,`·「및」까지)에서 **마지막** 유형 명사, 없으면 그 뒤 구간들에서 처음 나오는 것.
        segs = [x for x in re.split(r"[,，/|]|\s및\s|\s그리고\s", body[len(head):]) if x.strip()]
        pick = ""
        for seg in segs:
            found = _type_nouns_in(seg)
            if found:
                pick = max(found, key=lambda n: seg.rfind(n))
                break
        if pick:
            toks.append(pick)                         # 유형 명사는 뒤에서라도 반드시(지어내지 않음 — 제목에 있는 것만)
    out: List[str] = []
    i = 0
    while i < len(toks):
        pair = tuple(toks[i:i + 2])
        if len(pair) == 2 and pair in COMPOUNDS:
            out.append(COMPOUNDS[pair]); i += 2
        else:
            out.append(toks[i]); i += 1
    return " ".join(out)


def _option_texts(product: Dict[str, Any]) -> List[str]:
    vals: List[str] = []
    opts = product.get("options")
    if isinstance(opts, list):
        for o in opts:
            if isinstance(o, dict):
                vals += [str(v) for v in (o.get("values") or []) if str(v).strip()]
    if not vals:
        for k in product.get("skus") or []:
            if isinstance(k, dict):
                spec = k.get("spec") if isinstance(k.get("spec"), list) else [k.get("name") or ""]
                s = " ".join(str(x) for x in spec if x)
                if s.strip():
                    vals.append(s)
    return vals


def common_attrs(product: Dict[str, Any]) -> List[str]:
    """옵션 원문 **전부에 공통**인 용어집 토큰(2개 이상 값일 때만). 색상처럼 갈리는 값은 여기 안 온다."""
    # 용어집은 `coupang_options` 한 곳에서만 읽는다(D3 격리 계약).
    from src.uploaders.coupang_options import common_value_tokens
    return common_value_tokens(_option_texts(product))


def compat_of(product: Dict[str, Any], exclude: Iterable[str] = ()) -> List[str]:
    text = " ".join(str(product.get(k) or "") for k in ("title_original", "title_ko", "title"))
    ex = " ".join(exclude)
    return [label for rx, label in COMPAT if rx.search(text) and label not in ex]


def _dedupe(tokens: List[str]) -> List[str]:
    seen, out = set(), []
    for t in tokens:
        k = _norm_tok(t)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def _fit(s: str) -> str:
    s = re.sub(r"\s{2,}", " ", s).strip()
    if len(s) <= MAX_LEN:
        return s
    cut = s[:MAX_LEN]
    return cut[:cut.rfind(" ")].strip() if " " in cut else cut


def build_name(product: Dict[str, Any], brand_pos: str = "front") -> Dict[str, Any]:
    """규칙형 쿠팡 상품명 → `{name, parts, warnings, source:"rule"}`. 유형을 못 찾으면 name=""(지어내지 않음)."""
    brand = brand_of(product)
    ptype = product_type(str(product.get("title_ko") or product.get("title") or ""), brand)
    attrs = [a for a in common_attrs(product) if a not in ptype]
    compat = compat_of(product, exclude=[ptype] + attrs)
    parts = {"brand": brand, "type": ptype, "attrs": attrs, "compat": compat,
             "brand_pos": brand_pos if brand_pos in BRAND_POS else "front"}
    if not ptype:
        return {"name": "", "parts": parts, "source": "rule",
                "warnings": ["제목에서 제품 유형을 찾지 못했어요 — 쿠팡 상품명을 직접 적어 주세요"]}
    core = _dedupe(attrs + ptype.split())
    body = " ".join(core)
    tail = f" ({'·'.join(compat)} 겸용)" if compat else ""
    pos = parts["brand_pos"]
    if brand and pos == "front":
        name = f"{brand} {body}{tail}"
    elif brand and pos == "back":
        name = f"{body}{tail} {brand}"
    else:
        name = f"{body}{tail}"
    name = _fit(name)
    return {"name": name, "parts": parts, "source": "rule", "warnings": check_name(name)}


# ── LLM 다듬기(오너가 누를 때만) ─────────────────────────────────────────
def llm_rewrite(product: Dict[str, Any], rule: Dict[str, Any], *, call=None) -> Dict[str, Any]:
    """규칙안을 LLM으로 다듬는다 — **규칙 검사를 통과한 결과만** 채택, 아니면 규칙안 그대로(사유 표기).

    `call(prompt) -> str`을 주입할 수 있다(테스트). 기본은 OpenAI(키 없으면 규칙안).
    """
    parts = rule.get("parts") or {}
    # Y5(오너 2026-10-04): 제목이 비면 AI에 물을 재료가 없다 — 부르지 않고 그렇게 말한다(헛호출·HTTPError 0).
    if not str(product.get("title_ko") or product.get("title") or "").strip():
        return {**rule, "note": "제목 없음 — 보강 먼저(AI 다듬기 건너뜀)"}
    prompt = ("쿠팡 상품명을 만드세요. 규칙: 「브랜드 + 제품 유형 + 핵심 속성」만, 조사·서술어·문장 금지, "
              "쉼표 나열 금지, 같은 말 반복 금지, 100자 이내, 없는 기능·스펙 추가 금지. 한 줄만 답하세요.\n"
              f"브랜드: {parts.get('brand') or '(없음)'} (위치: {parts.get('brand_pos')})\n"
              f"제품 유형: {parts.get('type')}\n핵심 속성: {', '.join(parts.get('attrs') or []) or '(없음)'}\n"
              f"겸용: {', '.join(parts.get('compat') or []) or '(없음)'}\n"
              f"원래 제목: {str(product.get('title_ko') or product.get('title') or '')[:200]}\n"
              f"규칙안: {rule.get('name')}")
    try:
        text = (call or _openai_call)(prompt)
    except Exception as exc:                          # noqa: BLE001 — 실패하면 규칙안(정직 표기)
        # Y5: 「HTTPError」 한 단어 대신 사유·HTTP 코드·재시도 여부·원문(계측에도 적재).
        try:
            from src.seller_console.ai.translator import failure_line
            why = failure_line(exc, "openai-title")
        except Exception:
            why = type(exc).__name__
        logger.warning("쿠팡 상품명 AI 다듬기 실패 — %s", why)
        return {**rule, "note": f"AI 다듬기 실패 — {why} · 규칙안을 그대로 둡니다"}
    cand = _fit(str(text or "").strip().strip("「」\"'").splitlines()[0] if text else "")
    if not cand:
        return {**rule, "note": "AI가 빈 답을 줬어요 — 규칙안을 그대로 둡니다"}
    warns = check_name(cand)
    brand = parts.get("brand") or ""
    if brand and parts.get("brand_pos") != "omit" and brand.lower() not in cand.lower():
        warns.append("브랜드가 빠졌어요")
    if warns:
        return {**rule, "note": "AI안이 규칙에 걸려 규칙안을 그대로 둡니다: " + " · ".join(warns)}
    return {"name": cand, "parts": parts, "source": "llm", "warnings": []}


def _openai_call(prompt: str) -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key or os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        raise RuntimeError("OPENAI_API_KEY 없음")
    import requests
    from decimal import Decimal
    from src.ai.budget import BudgetExceededError, BudgetGuard
    from src.seller_console.ai.translator import _OPENAI_IN_USD, _OPENAI_OUT_USD, _post_with_429_retry
    guard = BudgetGuard()                              # Y5: 서버 월 예산에 묶는다(넘으면 「서버 월 예산」으로 실패)
    if not guard.can_spend(estimated_cost_usd=Decimal(str(len(prompt))) * _OPENAI_IN_USD + Decimal("200") * _OPENAI_OUT_USD):
        raise BudgetExceededError(guard.summary())
    r = _post_with_429_retry(requests, "https://api.openai.com/v1/chat/completions",   # Y5: 429 백오프 1회
                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                             json={"model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"), "temperature": 0.2,
                                   "messages": [{"role": "user", "content": prompt}]}, timeout=20)
    return r.json()["choices"][0]["message"]["content"]


def effective_name(product: Dict[str, Any], brand_pos: Optional[str] = None) -> Dict[str, Any]:
    """등록·사전검증이 쓰는 이름: 오너가 적은 `coupang_name` → 없으면 규칙안. `{name, source, warnings}`."""
    manual = str(product.get("coupang_name") or "").strip()
    if manual:
        return {"name": _fit(manual), "source": str(product.get("coupang_name_source") or "manual"),
                "warnings": check_name(manual)}
    return build_name(product, brand_pos or str(product.get("coupang_brand_pos") or "front"))


# ── 브랜드 위치(카테고리별 오너 설정) ────────────────────────────────────
def _prefs_key(user_id: str) -> str:
    return f"coupang_title_prefs:{user_id}"


def brand_prefs(user_id: str) -> Dict[str, str]:
    """`{카테고리 코드: front|back|omit, "*": 기본}` — 없으면 기본 front."""
    try:
        from src.db import image_translate_queue_pg as st
        v = st.state_get(_prefs_key(str(user_id or "")))
    except Exception:
        v = {}
    return {str(k): str(p) for k, p in (v or {}).items() if str(p) in BRAND_POS}


def brand_pos_for(user_id: str, category: str) -> str:
    p = brand_prefs(user_id)
    return p.get(str(category or "")) or p.get("*") or "front"


def save_brand_pos(user_id: str, category: str, pos: str) -> Dict[str, str]:
    if pos not in BRAND_POS:
        raise ValueError(f"브랜드 위치는 {BRAND_POS} 중 하나여야 합니다")
    from src.db import image_translate_queue_pg as st
    cur = brand_prefs(user_id)
    cur[str(category or "*") or "*"] = pos
    st.state_set(_prefs_key(str(user_id or "")), cur)
    return cur
