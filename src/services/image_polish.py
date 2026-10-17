"""Y11-I(오너 2026-10-14) — 번역 다듬기(자동). 텐센트 번역본의 상자 글자를 상품 설명 톤 한국어로 고쳐 **새 버전**을 만든다.

실측(VRSUK 운영 상자): 상세 13 「프로피리티어 20」(원문 영어 Proprietary 20) · 상세 17 「아만 평연 봉선」(亚曼平韧缝线) · 상세 8 「자리 Eams」(원문 Chair Eams) —
텐센트는 낱말만 옮기고 문맥(상품명·카테고리·같은 사진의 다른 줄)을 모른다.

흐름(번역 완료 직후, 큐 워커):
1. 상자별 {원문(SourceText) · 텐센트 한국어} + 상품명 · 카테고리 · 같은 사진 다른 상자를 Claude haiku 한 번에(상자 10개씩).
   규칙: 상품 설명 톤 · 브랜드·규격·숫자 보존 · 뜻 모를 원문은 빈칸(지움). 용어집(`src/uploaders/image_glossary.json`)을
   프롬프트에 넣고 텐센트 결과에도 **먼저** 적용한다(AI가 없어도 용어집 고침은 들어간다).
2. 고친 상자만 「글자 고치기」 렌더(`image_edit.apply` — 지우고 글자 얹기)로 **번역본(다듬음)** 버전을 만든다.
   텐센트 번역본은 버전 목록에 남는다(원본 불변 — Y11-E). 기본 선택은 다듬은 쪽.
3. 반례(오너): AI가 「최고·1위·100%」 같은 과장을 만들면 Y10 금지어에 걸린다 — 프롬프트에 금지어를 넣고, **금지어·과장·
   숫자 누락·새 상표 이름이 있는 상자 결과는 버린다**(그 상자는 텐센트 글자 그대로).
4. 비용: haiku 호출마다 하루 카운터(`IMAGE_POLISH_DAILY_CAP`, 기본 400) — 「오늘 텐센트 호출」 옆에 「다듬기 n/400」.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ENV_CAP = "IMAGE_POLISH_DAILY_CAP"
DEFAULT_CAP = 400
BATCH = 10
POLISH_BY = "polish"
POLISH_LABEL = "번역본(다듬음)"
#: 다듬기 프롬프트 판 — 바뀌면 옛 캐시 답은 지금 검사를 통과할 때만 다시 쓴다(Y11-L).
PROMPT_VER = "y11n-1"
_KST = timezone(timedelta(hours=9))
_GLOSSARY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploaders", "image_glossary.json")
#: 다듬기 결과에서 버리는 과장(Y10 금지어 ban_ko에 더해 — 오너 반례 「최고·1위·100%」)
_HYPE = re.compile(r"최고|1\s*위|100\s*%|백\s*퍼센트|최저가?|완벽|유일|무조건|보장|국내\s*최초|세계\s*최초|넘버\s*원|No\.?\s*1", re.I)
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def enabled() -> bool:
    return str(os.getenv("IMAGE_POLISH", "1")).strip() != "0"


def daily_cap() -> int:
    try:
        return max(0, int(os.getenv(ENV_CAP, str(DEFAULT_CAP)) or DEFAULT_CAP))
    except ValueError:
        return DEFAULT_CAP


def _day_key() -> str:
    return "imgpolish:day:" + datetime.now(_KST).strftime("%Y-%m-%d")


def today_count() -> int:
    from src.db import image_translate_queue_pg as q
    try:
        return int(q.day_count(_day_key()) or 0)
    except Exception:                                            # noqa: BLE001
        return 0


def glossary() -> List[Dict]:
    try:
        with open(_GLOSSARY_PATH, encoding="utf-8") as f:
            return [t for t in (json.load(f).get("terms") or []) if isinstance(t, dict) and t.get("src") and t.get("ko")]
    except Exception:                                            # noqa: BLE001
        return []


def _srcs(t: Dict) -> List[str]:
    v = t.get("src")
    return [str(x) for x in v] if isinstance(v, list) else [str(v or "")]


#: ⑨ 원문 유지 표기 — 상자 글자 전체가 브랜드·모델 표기면 음차하지 않고 원문 그대로(Y11X: 상세 13 「Proprietary 20」 →
#   텐센트 「프로피리티어 20」·다듬기 「프로프라이어터리 20」). ⑨의 「브랜드·모델명·™®가 붙은 낱말」과 같은 규칙을 코드로 —
#   ™®가 붙은 짧은 표기, 또는 영문 낱말(1~3개) + 숫자 모델 번호. 「Size 20」 같은 규격 낱말+숫자는 번역 대상이라 뺀다.
_KEEP_MODEL = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ&'.\-]*(?:\s[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ&'.\-]*){0,2}\s?\d{1,4}[A-Za-zÀ-ÿ]?$")
_KEEP_MARK = re.compile(r"^[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9&'.\-]*(?:\s[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9&'.\-]*){0,2}\s?[™®]$")
_SPEC_WORDS = {"size", "color", "colour", "no", "step", "page", "item", "type", "pcs", "pc", "set", "cm", "mm", "kg", "level",
               "top"}                                            # TOP1 = 판촉(「톱1」 금지어 계열) — 원문 유지 대상 아님


def keep_original(src: str) -> str:
    """⑨ 원문 유지 표기면 그 표기(앞뒤 공백 정리), 아니면 ""."""
    s = re.sub(r"\s+", " ", str(src or "")).strip()
    if not s or len(s) > 40:
        return ""
    if _KEEP_MARK.match(s):
        return s
    m = _KEEP_MODEL.match(s)
    first = re.split(r"[\s\d]", s)[0].lower().rstrip(".")
    if not m or len(re.sub(r"[^A-Za-zÀ-ÿ]", "", s)) < 3 or first in _SPEC_WORDS:
        return ""
    return s


def apply_glossary(src: str, tgt: str, terms: Optional[List[Dict]] = None) -> str:
    """원문에 용어가 있고 한국어에 그 용어의 「틀린 말」이 있으면 바른 말로(이미 바른 말이면 그대로).
    ⑨ 원문 유지 표기(`keep_original`)는 용어집 단계에서 원문 그대로 — AI가 없어도 음차가 나가지 않는다."""
    keep = keep_original(src)
    if keep:
        return keep
    out = str(tgt or "")
    for t in terms if terms is not None else glossary():
        if not any(s and s in str(src or "") for s in _srcs(t)) or t["ko"] in out:
            continue
        for bad in sorted(t.get("bad") or [], key=len, reverse=True):
            if bad and bad in out:
                out = out.replace(bad, t["ko"])
                break
    return out


def _bans(text: str) -> List[str]:
    hits = []
    try:
        from src.collectors import ko_polish as kp
        hits += [str(x) for x in kp.ban_hits(text) or []]
    except Exception:                                            # noqa: BLE001
        pass
    hits += _HYPE.findall(text or "")
    return hits


def _new_trademark(ko: str, before: str) -> str:
    """다듬은 글자에 원문·텐센트에 없던 상표 이름이 생겼나 — 그 이름(없으면 "")."""
    try:
        from src.services import risk_gate as R
        for e in R._trademark_entries():
            names, case = e.get("names") or [], bool(e.get("case"))
            got = R._find(ko, names, case)
            if got and not R._find(before, names, case):         # 같은 상표의 다른 표기(伊姆斯→임스)는 새 이름이 아니다
                return got[0]
    except Exception:                                            # noqa: BLE001
        pass
    return ""


_HAN = re.compile("[㐀-䶿一-鿿]")

#: Y11-L(오너 2026-10-14): 품목에 안 맞는 표현 — VRSUK(라운지체어) 21번 「부드럽고 쫄깃한 식감」(软糯Q弹). 품목을 정해 주고,
#   그 품목에 쓰면 안 되는 말을 프롬프트에 넣고 결과에서 막는다. `hint` = 대신 쓸 말의 결.
CATEGORY_RULES = [
    {"key": "furniture", "label": "가구",
     "match": r"의자|체어|소파|리클라이너|라운지|스툴|침대|매트리스|테이블|책상|선반|수납장|가구|chair|sofa|recliner|furniture",
     "ban": ["식감", "맛", "풍미", "쫄깃", "바삭", "고소", "착용감", "핏", "섭취", "복용", "발림"],
     "hint": "앉는 느낌·쿠션감·탄탄함·지지감·소재·마감"},
    {"key": "apparel", "label": "의류·잡화",
     "match": r"티셔츠|셔츠|바지|원피스|자켓|재킷|코트|니트|가방|신발|운동화|모자|의류|dress|shirt|bag|shoes",
     "ban": ["식감", "맛", "풍미", "쫄깃", "섭취", "복용", "쿠션감", "앉는 느낌"],
     "hint": "착용감·핏·소재·마감"},
    {"key": "food", "label": "식품",
     "match": r"식품|간식|과자|젤리|사탕|초콜릿|커피|원두|음료|라면|소스|견과",
     "ban": ["착용감", "쿠션감", "앉는 느낌", "핏", "발림"],
     "hint": "식감·맛·풍미"},
    {"key": "beauty", "label": "화장품",
     "match": r"크림|로션|세럼|에센스|화장품|샴푸|클렌징|선크림|마스크팩",
     "ban": ["식감", "맛", "쫄깃", "착용감", "쿠션감", "앉는 느낌"],
     "hint": "발림성·흡수감·향"},
    {"key": "electronics", "label": "전자기기",
     "match": r"충전기|케이블|이어폰|헤드폰|스피커|모니터|키보드|마우스|보조배터리|전자",
     "ban": ["식감", "맛", "쫄깃", "착용감", "섭취", "발림"],
     "hint": "성능·연결·소재·크기"},
]
_CODE_KEY = {"FOD": "food", "CLO": "apparel", "BAG": "apparel", "BTY": "beauty", "ELC": "electronics", "DIG": "electronics"}


def category_rule(extra: dict) -> Dict:
    """`{key, label, what, ban, hint}` — 상품명·카테고리 이름 낱말이 먼저, 없으면 정규화 카테고리 코드. 모르면 {}."""
    ex = extra or {}
    names = " ".join(str(ex.get(k) or "") for k in ("coupang_category_name", "naver_category_name", "category"))
    title = str(ex.get("title_ko") or ex.get("title") or "")
    for hay in (title, names):
        for r in CATEGORY_RULES:
            m = re.search(r["match"], hay, re.I)
            if m:
                return dict(r, what=m.group(0))
    key = _CODE_KEY.get(str(ex.get("category_code") or "").upper())
    r = next((x for x in CATEGORY_RULES if x["key"] == key), None)
    return dict(r, what=r["label"]) if r else {}


def materials(extra: dict, limit: int = 12) -> List[str]:
    """소재(옵션값 · 참수의 재질/소재 줄) — 다듬기가 상품을 알게(프롬프트 한 줄)."""
    out: List[str] = []
    for o in (extra or {}).get("options") or []:
        if isinstance(o, dict):
            for v in (o.get("values_ko") or o.get("values") or [])[:6]:
                if str(v).strip():
                    out.append(str(v).strip()[:30])
    for kv in (extra or {}).get("detail_specs") or []:
        if isinstance(kv, (list, tuple)) and len(kv) == 2 and re.search(r"재질|소재|材质|面料|材料|원단", str(kv[0])):
            out.append(f"{kv[0]}: {kv[1]}"[:40])
    return list(dict.fromkeys(out))[:limit]


def han_left(text: str) -> bool:
    """Y11-L: 텐센트 결과에 한자가 남았나 — 번역 안 된 상자(원문 전체를 새로 번역)."""
    return bool(_HAN.search(text or ""))


def _cat_ban(ko: str, rule: Optional[Dict]) -> str:
    """품목에 안 맞는 말 — 낱말 앞이 한글이면 다른 낱말의 일부다(「의식감」 ≠ 「식감」, VRSUK 24번 오탐)."""
    for w in (rule or {}).get("ban") or []:
        if re.search(r"(?<![가-힣])" + re.escape(w), ko or ""):
            return w
    return ""


def _nums(text: str) -> set:
    """글 속 숫자 집합 — 천 단위 쉼표는 뗀다(3,200 = 3200)."""
    return {n.replace(",", "") for n in _NUM.findall(text or "")}


def check(src: str, tgt: str, ko: str, rule: Optional[Dict] = None) -> str:
    """다듬은 상자 하나를 쓸 수 있나 — 버릴 사유(쓸 수 있으면 "")."""
    if ko == "":
        return ""                                                # 빈칸(지움) — 뜻 모를 원문
    keep = keep_original(src)
    if keep and re.sub(r"\s+", " ", str(ko or "")).strip() != keep:
        return f"원문 유지 표기({keep})"                         # ⑨: 브랜드·모델 표기를 음차·번역한 답은 받지 않는다
    b = _bans(ko)
    if b:
        return f"금지어·과장({b[0]})"
    if han_left(ko):
        return "한자가 남음"
    w = _cat_ban(ko, rule)
    if w:
        return f"다른 품목 표현({w})"
    before = f"{src} {tgt}"
    # Y11-M(오너): 숫자는 **집합**으로 본다 — 원문·텐센트 둘 다 있던 숫자가 다듬은 글에도 다 있으면 통과(1:0.618 같은 비율 그대로)
    lost = sorted((_nums(src) & _nums(tgt)) - _nums(ko))
    if lost:
        return f"숫자 누락({lost[0]})"
    tm = _new_trademark(ko, before)
    if tm:
        return f"없던 상표 이름({tm})"
    # 길이는 여기서 안 본다 — 상자 폭·두 줄 기준으로 polish_entry가 잰다(Y11-L 「길어서 유지」)
    return ""


_SYSTEM = (
    "너는 쇼핑몰 상품 사진 속 글자를 고치는 한국어 편집자다. 원문(중국어·이탈리아어·영어 등)과 기계 번역 한국어를 받아, 사진에 그대로 얹을 "
    "자연스러운 한국어로 고친다. 규칙: ① 상품 설명 톤(짧은 명사·설명형), 원문 뜻만 — 없는 내용·과장 추가 금지. "
    "② 브랜드·모델명·규격·숫자·단위는 원문 그대로 둔다. ③ 원문 뜻을 알 수 없거나 깨진 글자(OCR 조각)면 \"\"(빈칸 — 지울지는 사람이 정한다). "
    "④ 용어집을 반드시 따른다. ⑤ 금지어는 쓰지 않는다. ⑥ 상자 크기에 맞게 기계 번역과 비슷한 길이. "
    "⑦ 품목에 맞는 말만 — 주어진 「이 상품」 품목에 안 맞는 다른 품목 표현(예: 가구에 식감·맛·착용감)은 그 품목의 말로 바꾼다. "
    "⑧ 기계 번역(mt)이 비었거나 「redo」가 붙은 상자는 기계 번역이 실패한 것 — 원문(src) 전체를 새로 한국어로 번역한다(한자를 남기지 않는다). "
    "⑨ 중국어가 아닌 외국어(이탈리아어·영어 낱말·문장)도 한국어로 번역한다 — 단 브랜드·모델명·™®가 붙은 낱말·뜻 없는 대문자 약어·코드·"
    "영문 낱말+숫자 모델 표기(예: EHILÀ, VRSUK, ZL, Proprietary 20)는 한글로 음차하지 말고 원문 그대로 둔다. 대문자로 적혔어도 사전에 있는 낱말이면 번역한다(예: AUTOPULENTE → 셀프 클리닝, NESSUNA RIGIDITÀ → 뻣뻣함 없음). "
    "⑩ 직역 금지 — 한국 쇼핑몰 상품 상세 카피체로 쓴다(예: 「모든 한 대는 편안한 챔피언」 ✗ → 「의자 하나하나가 편안함 그 자체」 ○). "
    "출력은 JSON 하나만: {\"boxes\":[{\"id\":\"t0\",\"ko\":\"...\"}]} — 받은 id 전부."
)


def _prompt(rows: List[Dict], ctx: Dict, terms: List[Dict]) -> str:
    rule = ctx.get("rule") or {}
    lines = [f"상품명: {ctx.get('title') or '-'}", f"카테고리: {ctx.get('category') or '-'}"]
    if rule:
        lines.append(f"이 상품은 {rule['label']}({rule.get('what') or rule['label']})다 — "
                     f"{'·'.join(rule['ban'])} 같은 다른 품목 표현 금지. 그런 말이 기계 번역에 있으면 {rule['hint']} 같은 말로 바꿀 것.")
    if ctx.get("materials"):
        lines.append("소재·옵션: " + ", ".join(ctx["materials"]))
    lines += ["용어집(원문→한국어): " + ", ".join(f"{'/'.join(_srcs(t))}→{t['ko']}" for t in terms),
              "금지어: 최고, 1위, 100%, 최저가, 완벽, 유일, 무조건, 보장, 국내 최초, 세계 최초, 할인율·쿠폰 문구",
              "같은 사진의 상자들(id · 원문 · 기계 번역 · redo=기계 번역 실패라 원문 전체를 새로 번역):"]
    for r in rows:
        d = {"id": r["id"], "src": r["src"], "mt": "" if r.get("han_left") else r["tgt"]}
        if r.get("han_left"):
            d["redo"] = True
        lines.append(json.dumps(d, ensure_ascii=False))
    return "\n".join(lines)


def _parse(text: str) -> Dict[str, str]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
    except Exception:                                            # noqa: BLE001
        return {}
    out = {}
    for b in d.get("boxes") or []:
        if isinstance(b, dict) and isinstance(b.get("id"), str) and isinstance(b.get("ko"), str):
            out[b["id"]] = b["ko"].strip()
    return out


#: Y11-M(오너): 한자 남은 상자는 AI에 두 번까지 — 그래도 한자가 남으면 한자 덩어리만 텐센트 텍스트 번역으로 옮겨 끼운다.
HAN_AI_TRIES = 2
_HAN_RUN = re.compile("[㐀-䶿一-鿿]+")


def splice_han(tgt: str) -> Dict:
    """`{ok, text, why}` — 텐센트 한국어 속 한자 덩어리만 텍스트 번역해 그 자리에 끼운다(나머지 글자는 그대로)."""
    from src.services.image_translate_tencent import translate_text
    out = tgt
    for run in dict.fromkeys(_HAN_RUN.findall(tgt or "")):
        r = translate_text(run)
        if not r.get("ok") or han_left(r["text"]):
            return {"ok": False, "text": "", "why": "텍스트 번역 실패(" + (r.get("why") or "한자 남음") + ")"}
        out = out.replace(run, r["text"])
    return {"ok": True, "text": re.sub(r"\s{2,}", " ", out).strip(), "why": ""}


def _ask(rows: List[Dict], ctx: Dict, terms: List[Dict]) -> Dict:
    """AI 한 번(상자 BATCH개) — `{got, error}`. 상한이면 `{capped: True}`."""
    from src.ai import llm
    from src.db import image_translate_queue_pg as q
    took, _n = q.take_start(_day_key(), daily_cap())
    if not took:
        return {"capped": True}
    res = llm.complete(_prompt([dict(r, tgt=r["glossary"]) for r in rows], ctx, terms), system=_SYSTEM, size="small",
                       max_tokens=1200, purpose="image_polish", timeout=30.0, json_mode=True, providers=["anthropic"])
    txt = res.get("text") or ""
    why = res.get("error") or (("읽을 수 없는 답(JSON 아님" + (f", stop={res.get('stop_reason')}" if res.get("stop_reason") else "")
                                 + ")") if txt else "빈 응답")
    return {"got": _parse(txt), "error": str(why)[:60], "retried_empty": bool(res.get("retried_empty"))}


def _take(r: Dict, ko: str, ctx: Dict) -> None:
    """AI 답 하나를 상자에 — 검사 통과면 채택, 아니면 사유만 남긴다(텐센트 글자 그대로)."""
    r["ai"] = ko
    r["tries"] = int(r.get("tries") or 0) + 1
    why = check(r["src"], r["glossary"], ko, ctx.get("rule"))
    r["why"] = why
    if not why and ko != r["glossary"]:
        r["ko"], r["from"] = ko, "polish"


def polish_boxes(boxes: List[Dict], ctx: Dict, cache: Optional[Dict] = None) -> Dict:
    """상자들 → `{rows:[{id, src, tgt, glossary, ko, from, why}], calls, ai_why}`.
    `from` = polish(AI 다듬음 채택) · tmt(한자만 텍스트 번역) · glossary(용어집만) · tencent(그대로). AI가 없거나 상한이면 용어집만."""
    from src.ai import llm
    terms = glossary()
    rows = []
    for b in boxes:
        src, tgt = str(b.get("src") or ""), str(b.get("tgt") or "")
        g = apply_glossary(src, tgt, terms)
        rows.append({"id": b["id"], "src": src, "tgt": tgt, "glossary": g, "ko": g,
                     "from": "glossary" if g != tgt else "tencent", "why": "", "han_left": han_left(tgt)})
    calls, ai_why, cached = 0, "", 0
    if not rows:
        return {"rows": rows, "calls": 0, "ai_why": "", "cached": 0}
    # Y11-L(오너): 상자별 {원문, 텐센트 한국어} → 다듬은 한국어 캐시 — 렌더만 다시 할 때 AI를 다시 부르지 않는다.
    #   캐시 값도 지금 규칙(품목 금지 표현·한자·금지어…)으로 다시 검사하고, 통과한 것만 쓴다(통과 못 하면 그 상자만 다시 묻는다).
    #   같은 프롬프트 판(PROMPT_VER)의 답은 버린 것까지 그대로 쓴다(다시 물어도 같은 규칙) — 옛 판 답은 지금 검사를 통과할 때만.
    for r in rows:
        hit = (cache or {}).get((r["src"], r["tgt"]))
        if not isinstance(hit, dict) or not isinstance(hit.get("ai"), str):
            continue
        old = hit.get("pv") != PROMPT_VER
        if old and hit["ai"] == "" and r["glossary"] != r["tgt"]:
            r["cached"] = True                                   # 용어집이 고친 상자(AUTOPULENTE→셀프 클리닝) — 옛 「빈칸」 답 대신 용어집, AI 안 부름
            cached += 1
            continue
        if old and ctx.get("outbound", True):
            # Y11N-1(오너 결정): 옛 프롬프트 답은 **등록에 나가는 사진만** 다시 묻는다(직역·외국어 「빈칸」 등 옛 판 답을 새 규칙으로).
            #   제외된 사진(수상 배너·쿠폰 등)은 캐시 그대로 — 안 나가는 그림에 돈 쓸 이유 없다.
            r["reask_old"] = True
            continue
        r["tries"] = max(0, int(hit.get("tries") or 1) - 1)
        _take(r, hit["ai"], ctx)
        r["cached"] = True
        if hit.get("tmt"):
            r["tmt"] = hit["tmt"]
        cached += 1
    todo = [r for r in rows if not r.get("cached")]
    ready = llm.anthropic_ready()
    if todo and not ready:
        ai_why = "AI 다듬기 못 씀(Claude 미연결) — 용어집만 적용"
    for i in range(0, len(todo) if ready else 0, BATCH):
        chunk = todo[i:i + BATCH]
        a = _ask(chunk, ctx, terms)
        if a.get("capped"):
            ai_why = f"오늘 다듬기 상한({daily_cap()}회)을 다 써서 용어집만 적용"
            break
        calls += 1
        if not a["got"]:
            # Y11-O(오너): 빈 응답·읽을 수 없는 답이면 그 묶음을 한 번 더 묻는다(같은 공급자 빈 응답 재시도는 llm이 이미 1회)
            logger.info("[다듬기] AI 답을 못 읽음(%s) — 그 묶음 %d상자 한 번 더", a["error"], len(chunk))
            a = _ask(chunk, ctx, terms)
            if a.get("capped"):
                ai_why = f"오늘 다듬기 상한({daily_cap()}회)을 다 써서 용어집만 적용"
                break
            calls += 1
            if not a["got"]:
                ai_why = f"AI 응답을 읽지 못함({a['error']}, 다시 물어도 같음) — 용어집만 적용"
                continue
        for r in chunk:
            if r["id"] in a["got"]:
                _take(r, a["got"][r["id"]], ctx)
    # Y11-M: 한자 남은 상자 — AI 두 번째(그 상자만) → 그래도 남으면 한자만 텍스트 번역해 끼운다.
    redo = [r for r in rows if r.get("han_left") and r["from"] != "polish" and int(r.get("tries") or 0) < HAN_AI_TRIES]
    if redo and ready and not ai_why:
        a = _ask(redo, ctx, terms)
        if a.get("capped"):
            ai_why = f"오늘 다듬기 상한({daily_cap()}회)을 다 써서 용어집만 적용"
        else:
            calls += 1
            for r in redo:
                if r["id"] in a.get("got") or {}:
                    _take(r, a["got"][r["id"]], ctx)
    for r in rows:
        if not r.get("han_left") or r["from"] == "polish" or int(r.get("tries") or 0) < HAN_AI_TRIES:
            continue
        sp = {"ok": True, "text": r["tmt"], "why": ""} if r.get("tmt") else splice_han(r["glossary"])
        if not sp["ok"]:
            r["why"] = sp["why"]
            continue
        r["tmt"] = sp["text"]
        why = check(r["src"], r["glossary"], sp["text"], ctx.get("rule"))
        if why:
            r["why"] = "텍스트 번역도 " + why
            continue
        r["ko"], r["from"], r["why"] = sp["text"], "tmt", ""
    return {"rows": rows, "calls": calls, "ai_why": ai_why, "cached": cached}


def outbound(extra: dict, kind: str, idx: int) -> bool:
    """이 장이 등록에 나가나 — 상세는 판정표의 등록 순서(`outbound_pos`), 갤러리는 판촉·상표로 뺀 장이 아니면. 모르면 나간다고 본다."""
    try:
        from src.services import image_translate_store as S
        for p in S.effective_plan(extra, kind=kind):
            if int(p.get("idx", -1)) != int(idx):
                continue
            if kind == "detail":
                return int(p.get("outbound_pos") or 0) > 0
            e = next((x for x in extra.get("images_ko") or [] if isinstance(x, dict) and int(x.get("idx", -1)) == int(idx)), {})
            return not (p.get("promo_excluded") or e.get("risk_exclude"))
    except Exception as exc:                                     # noqa: BLE001
        logger.info("[다듬기] 등록 여부 판정 실패(나간다고 봄): %s", exc)
    return True


_HANGUL = re.compile(r"[가-힣]")
_HAN = re.compile(r"[\u4e00-\u9fff]")
TINY_PCT = 1.5


def tiny_latin(box: Optional[dict], size=None) -> bool:
    """Y11-W — 사진 높이의 `TINY_PCT`% 미만 상자에 한자 없는 원문(라틴 장식 글자)을 텐센트가 한국어로 칠한 것."""
    b = box or {}
    try:
        H = float((size or [0, 0])[1] or 0)
        h = float(b.get("h") or 0)
    except (TypeError, ValueError, IndexError):
        return False
    src, tgt = str(b.get("src") or ""), str(b.get("tgt") or "")
    return bool(H and 0 < h < H * TINY_PCT / 100 and src.strip() and not _HAN.search(src) and _HANGUL.search(tgt))


def restorable(e: Optional[dict]) -> bool:
    """원본 픽셀을 붙일 수 있나 — 번역본과 원본의 좌표 틀이 같은 장(identity)."""
    return str((e or {}).get("box_frame") or "") == "identity"


def ban_cut(r: dict) -> bool:
    """금지어를 빼서 문구가 반 남짓으로 줄었나(「정품 보장」 → 「정품」)."""
    ko, tgt = str(r.get("ko") or "").strip(), str(r.get("tgt") or "").strip()
    return bool(str(r.get("why") or "").startswith("금지어") and ko and tgt and len(ko) < len(tgt) * 0.6)


def foreign_revert(text: str, box: Optional[dict]) -> bool:
    """Y11-V(오너 2026-10-16 19:14 「M … ISURE에」): 텐센트가 한국어로 그린 상자를 **한글 없는 글자(원문 등)로 다시 그리기**.
    어두운 사진 위 큰 장식 글자에선 텐센트 획을 다 못 지운 채 덧그려 깨졌다(상세 14: 「이수에」 위 「ISURE」 → 「ISURE에」).
    다듬기는 이런 상자를 다시 그리지 않는다 — 텐센트 글자 그대로."""
    t, tgt = str(text or "").strip(), str((box or {}).get("tgt") or "").strip()
    return bool(t) and not _HANGUL.search(t) and bool(_HANGUL.search(tgt))


def _short_of(text, box: Optional[dict]) -> bool:
    t, tgt = str(text or "").strip(), str((box or {}).get("tgt") or "").strip()
    return bool(t and tgt and _HANGUL.search(t) and len(t) < len(tgt) * 0.6 and tgt.startswith(t))


def _redo_polish(x: dict, boxes: Optional[list] = None, size=None) -> bool:
    """다시 만들 기계 다듬음 버전 — 옛 렌더(Y11-M 이전 Cloudinary 변환·렌더 판 `RENDER_V` 미만) 또는 **지운 상자가 있는 것**(Y11-N: 다듬기는 지우지 않는다)
    또는 **한국어 상자를 한글 없는 글자로 덧그린 것**(Y11-V)."""
    from src.services import image_edit as IE
    if x.get("by") != POLISH_BY:
        return False
    by_id = {f"t{i}": b for i, b in enumerate(boxes or []) if isinstance(b, dict)}
    ops = [o for o in x.get("ops") or [] if isinstance(o, dict)]
    restored = {o.get("id") for o in ops if o.get("action") == "restore"}
    return (x.get("render") != "local" or int(x.get("render_v") or 1) < IE.RENDER_V
            or any(o.get("action") == "erase" for o in ops)
            or any(o.get("action") == "text" and foreign_revert(o.get("text"), by_id.get(o.get("id"))) for o in ops)
            # Y11-W: 반쪽 문구(금지어를 뺀 배지)를 그린 버전 · 작은 라틴 장식 글자를 되살리지 않은 버전
            or any(o.get("action") == "text" and _short_of(o.get("text"), by_id.get(o.get("id"))) for o in ops)
            or bool(size and any(tiny_latin(b, size) and i not in restored for i, b in by_id.items()))
            # Y11X: ⑨ 원문 유지 표기(「Proprietary 20」)를 음차한 채 둔 버전 — 원본 되살림이 될 때만(틀이 다르면 그대로)
            or bool(size and any(_keep_broken(b, i, ops, restored) for i, b in by_id.items())))


def _keep_broken(box: dict, bid: str, ops: list, restored: set) -> bool:
    """이 상자가 원문 유지 표기인데 그 버전에 원문(되살림 또는 원문 글자)으로 안 들어갔나."""
    keep = keep_original(box.get("src"))
    if not keep or bid in restored or str(box.get("tgt") or "").strip() == keep:
        return False
    return not any(o.get("id") == bid and o.get("action") == "text" and str(o.get("text") or "").strip() == keep for o in ops)


def old_render(e: Optional[dict]) -> bool:
    """이 장의 다듬음 버전이 다시 만들 것(`_redo_polish`)이고, 그 위에 사람이 만든 편집이 없나. 그런 장만 번역본에서 다시 다듬는다.
    Y11-M: 옛 렌더(지운 자리 위에 겹쳐 그려 번짐, 21번). Y11-N: AI 「빈칸」을 지우기로 적용한 장(쿠폰 상세 4·6번 등) — 텐센트 글자로 되돌린다."""
    from src.services import image_edit as IE
    eds = IE.edits(e or {})
    old = [x for x in eds if _redo_polish(x, (e or {}).get("boxes"), (e or {}).get("box_size") if restorable(e) else None)]
    if not old:
        return False
    keys = {f"edit:{x['n']}" for x in old}
    if any(x.get("by") != POLISH_BY and x.get("base_key") in keys for x in eds):
        return False
    return IE.current_key(e) in keys | {IE.V_TRANSLATED}


def drop_old_polish(extra: dict, kind: str, idx: int) -> int:
    """다시 만들 다듬음 버전(`_redo_polish`)을 목록에서 빼고 번역본으로 돌린다(기계가 만든 버전만 — 사람 편집·원본·번역본은 그대로). 뺀 수."""
    from src.services import image_edit as IE
    e = IE._entry(extra, kind, idx)
    if not e or not old_render(e):
        return 0
    IE._normalize(e)
    gone = [x for x in e["edits"] if _redo_polish(x, e.get("boxes"), e.get("box_size") if restorable(e) else None)]
    keys = {f"edit:{x['n']}" for x in gone}
    e["edits"] = [x for x in e["edits"] if f"edit:{x['n']}" not in keys]
    for k in keys:
        (e.get("vboxes") or {}).pop(k, None)
    if e.get("pending_select") in keys:
        e.pop("pending_select", None)
    IE.select(extra, kind, idx, IE.V_TRANSLATED)
    e.setdefault("polish_rerender", []).append({"at": datetime.now(timezone.utc).isoformat(), "dropped": sorted(keys)})
    return len(gone)


def polish_entry(extra: dict, kind: str, idx: int) -> Dict:
    """번역본 한 장 → 다듬은 버전(편집본, by=polish). 결과 `{ok, changed, version?, rows, calls, why}` — 저장은 호출부."""
    from src.services import image_edit as IE
    if not enabled():
        return {"ok": False, "why": "다듬기 꺼짐"}
    e = IE._entry(extra, kind, idx) or {}
    ok_c, _w = IE.configured()
    if not ok_c:
        return {"ok": False, "why": "사진 편집을 쓸 수 없어 다듬은 버전을 못 만듦"}
    if old_render(e):
        drop_old_polish(extra, kind, idx)                        # 옛 렌더(변환 주소·겹쳐 그림)로 만든 다듬음 — 새로 그린다
        e = IE._entry(extra, kind, idx) or {}
    if IE.current_key(e) != IE.V_TRANSLATED:
        return {"ok": False, "why": "번역본이 지금 버전이 아님(사람이 고른 버전은 건드리지 않음)"}
    if any(x.get("by") == POLISH_BY for x in IE.edits(e)):
        return {"ok": False, "why": "이미 다듬음"}
    p = IE.plan(extra, kind, idx)
    boxes = [b for b in p.get("boxes") or [] if b.get("tgt") or b.get("src")]
    if not boxes:
        return {"ok": False, "why": p.get("why") or "다듬을 글자 상자가 없음"}
    ctx = {"outbound": outbound(extra, kind, idx),
           "title": str(extra.get("title_ko") or extra.get("title") or "")[:80],
           "category": str(extra.get("coupang_category_name") or extra.get("naver_category_name")
                           or extra.get("category") or "")[:60],
           "rule": category_rule(extra), "materials": materials(extra)}
    prev_pl = e.get("polish") or {}
    cache = {}
    for r in prev_pl.get("rows") or []:
        # AI가 실제로 답한 상자만(ai 비었는데 polish = 「지움」 답 · ai 비었는데 tencent = 답 없음)
        if isinstance(r, dict) and isinstance(r.get("ai"), str) and (r["ai"] or r.get("from") == "polish" or r.get("suggest_erase")):
            cache[(str(r.get("src") or ""), str(r.get("tgt") or ""))] = {"ai": r["ai"], "pv": prev_pl.get("pv") or "",
                                                                     "tries": r.get("tries") or 1, "tmt": r.get("tmt") or ""}
    pr = polish_boxes(boxes, ctx, cache=cache)
    by_id = {b["id"]: b for b in boxes}
    ops, too_long, suggest = [], 0, 0
    for r in pr["rows"]:
        if tiny_latin(by_id.get(r["id"]) or {}, e.get("box_size")) and restorable(e):
            # Y11-W: 사진 높이 1.5% 미만 라틴 장식 글자(서명 낙서 위 이탈리아어) — 번역하지 않는다. 텐센트가 칠한 자리를 원본으로 되살린다
            r["why"], r["from"], r["ko"], r["suggest_erase"] = "작은 장식 글자 — 원본 되살림", "restore", r["src"], ""
            ops.append({"id": r["id"], "action": "restore"})
            continue
        if r["ko"] == "" and r["tgt"]:
            # Y11-N(오너): 다듬기는 지우지 않는다 — AI 「빈칸」은 지우기 **제안**으로만 남기고 텐센트 글자 그대로(픽셀 0).
            #   지우는 건 사람이 편집기에서 그 상자를 탭해 적용할 때만(자동 경로·백필 경로 둘 다 이 함수).
            r["ko"], r["from"], r["suggest_erase"] = r["tgt"], "tencent", True
            suggest += 1
            continue
        _b = by_id.get(r["id"]) or {"tgt": r["tgt"]}
        if r["ko"] == r["tgt"]:
            continue
        if foreign_revert(r["ko"], _b):
            if restorable(e):                                    # Y11-W: 원문으로 되돌릴 땐 원본 픽셀을 붙인다(다시 그리지 않음)
                r["why"], r["from"] = "원문으로 되돌림 — 원본 되살림", "restore"
                ops.append({"id": r["id"], "action": "restore"})
            else:
                r["why"] = "원문으로 되돌리기는 다시 그리지 않음(텐센트 글자 유지)"     # Y11-V: 「ISURE에」
                r["ko"], r["from"] = r["tgt"], "tencent"
            continue
        if ban_cut(r):
            # Y11-W: 금지어(보장 등)를 빼고 남은 반쪽 문구(「정품 보장」→「정품」)를 배지에 그리지 않는다 — 텐센트 글자 + 지우기 제안
            r["why"] = (r.get("why") or "금지어") + " — 반쪽 문구라 다시 그리지 않음(지우기 제안)"
            r["ko"], r["from"], r["suggest_erase"] = r["tgt"], "tencent", True
            suggest += 1
            continue
        # Y11-M: 기준 = 텐센트가 같은 상자에 그린 글자(같은 줄 수·크기의 FIT_KEEP 이상이면 들어감)
        if r["ko"] and not IE.text_fit(r["ko"], by_id.get(r["id"]) or {}, ref=r["tgt"])["fits"]:
            r["why"] = "길어서 유지(상자에 안 들어감)"               # Y11-L 반례: 줄여도 안 들어가면 텐센트 글자 그대로
            r["ko"], r["from"] = r["tgt"], "tencent"
            too_long += 1
            continue
        ops.append({"id": r["id"], "action": "text", "text": r["ko"]})
    out = {"ok": True, "changed": len(ops), "rows": pr["rows"], "calls": pr["calls"], "why": pr["ai_why"],
           "cached": int(pr.get("cached") or 0), "too_long": too_long, "suggest_erase": suggest,
           "han_left": sum(1 for r in pr["rows"] if r.get("han_left"))}
    e = IE._entry(extra, kind, idx, create=True)
    han_n = sum(1 for r in pr["rows"] if r.get("han_left"))
    han_fixed = sum(1 for r in pr["rows"] if r.get("han_left") and r["from"] in ("polish", "tmt"))
    e["polish"] = {"at": datetime.now(timezone.utc).isoformat(), "calls": pr["calls"], "changed": len(ops),
                   "rows": [{k: r.get(k, "") for k in ("id", "src", "tgt", "ko", "ai", "from", "why", "han_left", "cached",
                                                       "tries", "tmt", "suggest_erase", "reask_old")}
                            for r in pr["rows"]][:40],
                   "han_left": han_n, "han_fixed": han_fixed, "rule": (ctx["rule"] or {}).get("key", ""),
                   "cached": int(pr.get("cached") or 0), "too_long": too_long, "suggest_erase": suggest, "pv": PROMPT_VER,
                   "outbound": bool(ctx["outbound"]), "reask_old": sum(1 for r in pr["rows"] if r.get("reask_old")),
                   "why": pr["ai_why"]}
    if not ops:
        return out
    res = IE.apply(extra, kind, idx, ops, by=POLISH_BY)
    if not res.get("ok"):
        e["polish"]["why"] = str(res.get("error") or "다듬은 버전을 만들지 못함")[:120]
        return dict(out, ok=False, why=e["polish"]["why"])
    e["polish"]["version"] = res.get("version")
    _carry_boxes(e, str(res.get("version") or ""), {r["id"]: r["ko"] for r in pr["rows"]})
    return dict(out, version=res.get("version"), pending=res.get("pending"))


def _carry_boxes(e: dict, key: str, ko_by_id: Dict[str, str]) -> None:
    """다듬은 버전의 글자 상자 = 번역본 상자 + 다듬은 한국어(지운 상자는 뺌) — 편집기가 그 버전을 다시 OCR하지 않게."""
    from src.services import image_edit as IE
    ed = next((x for x in IE.edits(e) if f"edit:{x['n']}" == key), None)
    boxes, size = e.get("boxes"), e.get("box_size")
    if not ed or not isinstance(boxes, list) or not size:
        return
    out = []
    for i, b in enumerate(boxes):
        ko = ko_by_id.get(f"t{i}", b.get("tgt"))
        if ko == "":
            continue
        out.append(dict(b, tgt=ko))
    e.setdefault("vboxes", {})[key] = {"boxes": out, "size": size, "img": ed["url"], "source": "polish",
                                       "at": datetime.now(timezone.utc).isoformat(), "angle": 0}


def polish_job(item_id: str, uid: str, kind: str, idx: int) -> Dict:
    """큐 워커 — 저장된 상품을 다시 읽어 다듬고 저장. 실패해도 번역 결과는 그대로(예외 없음)."""
    from src.seller_console import collect_history_store as store
    try:
        row = store.get(item_id, seller_ids={uid}) or {}
        extra = json.loads(row.get("extra_json") or "{}") or {}
        res = polish_entry(extra, kind, idx)
        if "rows" in res:                                        # 다듬기 기록(바뀐 것 없음 포함)이 생겼을 때만 저장
            from src.services import image_edit as IE
            mine = IE._entry(extra, kind, idx)
            from src.services.image_translate_store import keys_of as _ko
            ko_key = _ko(kind)[1]
            row = store.get(item_id, seller_ids={uid}) or {}     # 그 사이 다른 장이 적혔을 수 있다 — 이 장만 바꿔 넣는다
            fresh = json.loads(row.get("extra_json") or "{}") or {}
            ents = [x for x in fresh.get(ko_key) or [] if isinstance(x, dict) and int(x.get("idx", -1)) != int(idx)]
            fresh[ko_key] = sorted(ents + [mine], key=lambda x: int(x.get("idx", -1)))
            store.update(item_id, seller_ids={uid}, extra_json=json.dumps(fresh, ensure_ascii=False))
            if res.get("version"):                               # Y11-V: 다듬은 버전이 생겼으면 네이버 본문 다시 보내기 줄
                from src.services import naver_detail_refresh as _ndr
                _ndr.enqueue_item(item_id, fresh, uid)
                from src.services import coupang_detail_refresh as _cdr   # Y11-W: 쿠팡 등록본도(승인·반려·임시저장일 때 보냄)
                _cdr.enqueue_item(item_id, fresh, uid, reason="다듬은 버전")
        logger.info("[다듬기] item=%s %s#%s 바뀐 상자 %s · haiku %s회 · %s", item_id, kind, idx, res.get("changed", 0),
                    res.get("calls", 0), res.get("why") or "ok")
        return res
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[다듬기] item=%s %s#%s 실패: %s", item_id, kind, idx, exc)
        return {"ok": False, "why": f"{type(exc).__name__}"}


def item_targets(extra: dict) -> List[Tuple[str, int]]:
    """다듬을 장 — 번역본(상자 있음)이 지금 버전이고 아직 안 다듬은 장 + 옛 렌더로 다듬은 장(Y11-M 다시 그림)."""
    from src.services import image_edit as IE
    from src.services import image_translate_store as istore
    out = []
    for kind in istore.KINDS:                                    # Y11-U: 옵션(SKU) 사진도 다듬는다
        key = istore.keys_of(kind)[1]
        for e in extra.get(key) or []:
            if not isinstance(e, dict) or e.get("status") != "done" or not istore.has_boxes(e):
                continue
            if not old_render(e) and (IE.current_key(e) != IE.V_TRANSLATED or any(x.get("by") == POLISH_BY for x in IE.edits(e))):
                continue
            out.append((kind, int(e.get("idx", -1))))
    return out


_RUN = {"busy": False}


def start_item(item_id: str) -> Dict:
    """이미 번역된 상품 한 개를 다듬는다(관리자 버튼 — 이 기능 전에 번역된 장용). 백그라운드 · 결과는 장마다 `polish` 기록."""
    import threading
    from src.services.ocr_compare_diag import _item
    if _RUN["busy"]:
        return {"ok": False, "why": "다듬는 중이에요 — 끝나면 다시 눌러 주세요"}
    row, uid = _item(item_id)
    if not row:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    targets = item_targets(json.loads(row.get("extra_json") or "{}") or {})
    if not targets:
        return {"ok": True, "n": 0, "why": "다듬을 번역본이 없어요(상자 없는 번역본·이미 다듬음·다른 버전 선택 제외)"}

    from src.db import image_translate_queue_pg as q
    _RUN["busy"] = True                                          # 시작 응답 전에 잡아 둔다(연타 두 번 시작 금지)
    started_at = datetime.now(timezone.utc).isoformat()
    q.state_set(_item_key(item_id), {"running": True, "n": len(targets), "at": started_at, "started_at": started_at})

    def _go():
        done, whys = 0, []
        try:
            for kind, idx in targets:
                r = polish_job(item_id, uid, kind, idx) or {}
                done += 1
                if r.get("why") and not r.get("changed"):
                    whys.append(str(r["why"]))
        finally:
            _RUN["busy"] = False
            q.state_set(_item_key(item_id), {"running": False, "n": len(targets), "done": done, "started_at": started_at,
                                             "why": (max(set(whys), key=whys.count) if whys else ""),
                                             "at": datetime.now(timezone.utc).isoformat()})

    threading.Thread(target=_go, daemon=True, name="image-polish").start()
    return {"ok": True, "n": len(targets)}


def _item_key(item_id: str) -> str:
    return f"imgpolish:item:{item_id}"


def item_line(item_id: str, extra: dict) -> str:
    """Y12-A(오너 2026-10-17) 결과줄 한 문장 — 「다듬기 완료 · 24장 · 바뀐 장 1」(바뀐 장 = **마지막 실행**에서 새 버전이 생긴 장 수,
    누적 아님). 상자·AI 횟수·캐시·길어서·버림 사유는 `item_detail`(접힘). 진행 중이면 「다듬기 중 · n/n장」."""
    from src.db import image_translate_queue_pg as q
    st = q.state_get(_item_key(item_id)) or {}
    pls = [e.get("polish") for key in ("images_ko", "detail_images_ko", "sku_images_ko") for e in (extra.get(key) or [])
           if isinstance(e, dict) and isinstance(e.get("polish"), dict)]
    if st.get("running"):
        since = str(st.get("at") or "")
        done = sum(1 for pl in pls if str(pl.get("at") or "") >= since) if since else 0
        return f"다듬기 중 · {min(done, int(st.get('n') or 0) or done)}/{st.get('n') or '?'}장"
    if not pls:
        return "다듬기 · 다듬은 사진이 아직 없어요" if st else ""
    return f"다듬기 완료 · {len(pls)}장 · 바뀐 장 {changed_last_run(pls, st)}"


def changed_last_run(pls: list, st: Optional[dict] = None) -> int:
    """마지막 실행에서 새 버전이 생긴 장 수. 실행 기록(`started_at`)이 있으면 그 뒤, 없으면(장 하나만 돌린 일회성·자동 다듬기)
    가장 최근 다듬기 시각부터 10분 안 — 그 묶음이 마지막 실행이다."""
    from datetime import timedelta
    ats = []
    for pl in pls:
        try:
            ats.append(datetime.fromisoformat(str(pl.get("at") or "").replace("Z", "+00:00")))
        except ValueError:
            ats.append(None)
    known = [a for a in ats if a]
    if not known:
        return 0
    start = None
    if (st or {}).get("started_at"):
        try:
            start = datetime.fromisoformat(str(st["started_at"]).replace("Z", "+00:00"))
        except ValueError:
            start = None
    if start is None or start > max(known):
        start = max(known) - timedelta(minutes=10)
    return sum(1 for pl, a in zip(pls, ats) if a and a >= start and pl.get("version"))


def item_detail(item_id: str, extra: dict) -> str:
    """접힘 — 예전 결과줄(「번역 다듬기 n장: 바뀐 상자 n · AI n회 · 버린 결과 n」 + 사유)."""
    from src.db import image_translate_queue_pg as q
    st = q.state_get(_item_key(item_id)) or {}
    rows = []
    for key, lab in (("images_ko", "사진"), ("detail_images_ko", "상세"), ("sku_images_ko", "옵션 사진")):   # Y12-A: 한 줄 장 수와 같게
        for e in extra.get(key) or []:
            pl = e.get("polish") if isinstance(e, dict) else None
            if isinstance(pl, dict):
                rows.append((f"{lab} {int(e.get('idx', -1)) + 1}", pl))
    if st.get("running"):
        # Y11-M: 이번 실행분만 센다 — 예전에 다듬은 장(13:23 상세 28번 등)까지 세면 「24/23장」이 됐다
        since = str(st.get("at") or "")
        done = sum(1 for _n, pl in rows if str(pl.get("at") or "") >= since) if since else 0
        return f"번역 다듬기 중… ({min(done, int(st.get('n') or 0) or done)}/{st.get('n') or '?'}장)"
    if not rows:
        if not st:
            return ""
        return "번역 다듬기: 다듬은 사진이 아직 없어요" + (f" — {st['why']}" if st.get("why") else "")
    changed = sum(int(pl.get("changed") or 0) for _n, pl in rows)
    calls = sum(int(pl.get("calls") or 0) for _n, pl in rows)
    # 「길어서 유지」는 따로 센다 — 버림(검사 탈락)과 섞으면 같은 상자를 두 번 센다(Y11-M: 18 = 길어서 16 + 금지어 1 + 품목 1)
    drop_why = [str(r.get("why")) for _n, pl in rows for r in pl.get("rows") or []
                if r.get("why") and not str(r.get("why")).startswith("길어서")]
    dropped = len(drop_why)
    whys = sorted({str(pl.get("why")) for _n, pl in rows if pl.get("why")})
    cached = sum(int(pl.get("cached") or 0) for _n, pl in rows)
    too_long = sum(int(pl.get("too_long") or 0) for _n, pl in rows)
    s = f"번역 다듬기 {len(rows)}장: 바뀐 상자 {changed} · AI {calls}회" + (f"(캐시 {cached}상자)" if cached else "")
    if too_long:
        s += f" · 길어서 유지 {too_long}"
    reask = sum(1 for _n, pl in rows for r in pl.get("rows") or [] if r.get("reask_old"))
    if reask:
        s += f" · 재질문 {reask}상자(옛 프롬프트)"
    sug = sum(1 for _n, pl in rows for r in pl.get("rows") or [] if r.get("suggest_erase"))
    if sug:
        s += f" · AI 지우기 제안 {sug}(편집기에서 탭해야 지움)"
    han_fixed = sum(int(pl.get("han_fixed") or 0) for _n, pl in rows)
    tmt = sum(1 for _n, pl in rows for r in pl.get("rows") or [] if r.get("from") == "tmt")
    han_n = sum(int(pl.get("han_left") or 0) for _n, pl in rows)
    if han_n:
        s += (f" · 한자 잔존 {han_fixed}상자 재번역" + (f"(텍스트 번역 {tmt})" if tmt else "")
              + (f"(못 고친 {han_n - han_fixed})" if han_n > han_fixed else ""))
    if dropped:
        kinds: Dict[str, int] = {}
        for w in drop_why:
            k = w.split("(")[0]
            kinds[k] = kinds.get(k, 0) + 1
        s += f" · AI 결과 버림 {dropped}(" + "·".join(f"{k} {n}" for k, n in sorted(kinds.items(), key=lambda x: -x[1])) + ")"
    if whys:
        s += " · " + whys[0][:60]
    return s
