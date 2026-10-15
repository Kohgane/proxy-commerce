"""Y8(오너 2026-10-13) — 사전검증 보류 사유를 **AI가 고친다**(Anthropic 우선 · OpenAI 폴백 — `src.ai.llm`).

흐름(사전검증 잡이 부른다): 사전검증 → 고칠 수 있는 보류만 골라(`plan`) AI에 묻고 → 검사(가드)를 통과한 답만 수집 기록에
적용(`manual_fields`에 `ai:` 표시) → 그 마켓만 다시 사전검증. 최대 2회전 · 상품당 AI 호출 6회.

고칠 수 있는 것(종류 = `kind`):
  a `option_value`   옵션 값 미해석 — 값마다 한국어(발송 소요 꼬리는 떼고 · 원문 숫자·영문 보존) → `option_value_overrides`
  a' `option_short`    Y11-P 네이버 옵션값 25자 초과 — 한국어 값을 25자 안으로 줄임(겹침 없이 · 지금 값의 숫자·영문 보존) → 같은 칸
  b `naver_category` 네이버 카테고리 후보 중 **하나만**(후보 밖 ID는 버림) + 한 줄 이유 → `naver_category_id`
  c (상품명)         표시광고·금지어·원문 남은 상품명 — `reject_autofix`(#886)가 고친다(이 모듈은 카드 줄·되돌리기만 합친다).
                     그 답에도 같은 가드(IP·상표·원문에 없는 영문 이름)를 건다 — `reject_autofix._changes`
  d `detail`         상세 본문 비어 있음/가게 UI 글자 → 상세 초안(기존 `_pv_auto_detail` — Anthropic 우선으로 바뀜). 여기선 카드 줄·되돌리기만
  e `notice`         고시정보 빈칸 — **원문에 적힌 것만**(원산지 등). 못 찾으면 그대로(「상세페이지 참조」 유지) → `origin`
  f `coupang_axis`   쿠팡 「메타 속성 고르기」 — 메타에 없는 옵션 축 이름을 그 카테고리 메타 속성 중 하나로(목록 밖 금지)
                     → `coupang_option_names`(쿠팡 전용 — 네이버 그룹 이름·화면엔 안 나감, 편집 화면 드롭다운과 같은 표)
    `coupang_attr`   쿠팡 필수 구매옵션(메타 속성) 값이 비었을 때 근거 있는 값 → `coupang_attributes`

AI가 절대 안 건드리는 것: 가격·마진·배송·브랜드 칸(GENERIC)·등록된 마켓 기록·「그래도 등록」 플래그·선주문 보류.
가드: IP·상표 게이트(`ko_polish.ip_hits/mark_hits/replica_hits`), 원문에 없는 고유명(`invented_names`), 한자·가나가 섞인 답은 버림.
되돌리기: `revert(ex, key)` — 원래 값으로 돌리고 그 항목은 다시 AI가 고치지 않게 막는다(→ 다시 보류).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_ROUNDS = 2
MAX_CALLS = 6
RETRY_AFTER = timedelta(hours=24)          # 검사에 떨어진 항목은 하루 동안 다시 묻지 않는다(같은 돈을 또 쓰지 않게)

KIND_LABEL = {"option_value": "옵션값", "option_short": "옵션값 축약", "naver_category": "카테고리", "coupang_category": "쿠팡 카테고리", "title": "상품명", "detail": "상세",
              "notice": "고시정보", "coupang_attr": "쿠팡 필수옵션", "coupang_axis": "쿠팡 옵션 속성"}
_KANA = re.compile(r"[぀-ヿ]")
_HAN = re.compile(r"[㐀-鿿豈-﫿]")
_MAX_VALUE = 25


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def has_cjk(s: str) -> bool:
    """중국어(한자)·일본어(가나)가 섞였는가 — 한국 마켓에 나갈 AI 답이면 버린다."""
    return bool(_HAN.search(str(s or "")) or _KANA.search(str(s or "")))


def guard(text: str, src: str = "") -> str:
    """AI 답 검사 — 통과면 "", 아니면 버리는 이유. IP·상표 게이트 + 한자·가나 + 원문에 없는 고유명."""
    t = str(text or "").strip()
    if not t:
        return "빈 답"
    if has_cjk(t):
        return "한자·가나가 섞인 답"
    from src.collectors import ko_polish as _kp
    for fn, why in ((_kp.ip_hits, "영화·게임·애니 IP"), (_kp.mark_hits, "상표"), (_kp.replica_hits, "레플리카 상표")):
        try:
            hit = fn(t)
        except Exception:
            hit = []
        if hit:
            return f"{why}({', '.join(hit)})가 들어간 답"
    if src:
        try:
            inv = _kp.invented_names(src, t)
        except Exception:
            inv = []
        if inv:
            return f"원문에 없는 고유명({', '.join(inv)})을 만든 답"
    return ""


# ── 기록(수집 기록 extra) ────────────────────────────────────────────────────────────────────────

def fixes_of(ex: dict) -> Dict[str, dict]:
    v = ex.get("ai_fixes") if isinstance(ex, dict) else None
    return v if isinstance(v, dict) else {}


def blocked(ex: dict) -> Dict[str, str]:
    v = ex.get("ai_fix_blocked") if isinstance(ex, dict) else None
    return v if isinstance(v, dict) else {}


def _recently_tried(ex: dict, key: str) -> bool:
    t = (ex.get("ai_fix_tried") or {}).get(key) if isinstance(ex.get("ai_fix_tried"), dict) else None
    try:
        return bool(t) and datetime.now(timezone.utc) - datetime.fromisoformat(str(t)) < RETRY_AFTER
    except Exception:
        return False


def _skip(ex: dict, key: str) -> bool:
    return key in blocked(ex) or key in fixes_of(ex) or _recently_tried(ex, key)


def _mark(ex: dict, key: str, kind: str, label: str, before: Any, after: Any, why: str, meta: dict) -> None:
    ex.setdefault("ai_fixes", {})[key] = {"kind": kind, "label": label, "before": before, "after": after,
                                          "why": str(why or "")[:160], "at": _now(),
                                          "provider": meta.get("provider", ""), "model": meta.get("model", "")}
    man = dict(ex.get("manual_fields") or {}) if isinstance(ex.get("manual_fields"), dict) else {}
    man[key] = "ai:" + _now()
    ex["manual_fields"] = man


def _tried(ex: dict, key: str, why: str) -> None:
    ex.setdefault("ai_fix_tried", {})[key] = _now()
    ex.setdefault("ai_fix_rejects", {})[key] = str(why or "")[:200]


# ── 계획: 보류 결과 → 고칠 일 ───────────────────────────────────────────────────────────────────

def _res_get(r, k, default=None):
    return r.get(k, default) if isinstance(r, dict) else getattr(r, k, default)


def _held(results, fix: str = "", code: str = "", detail: str = "") -> List[str]:
    out = []
    for r in results or []:
        if _res_get(r, "ok"):
            continue
        fixes = _res_get(r, "fixes") or []
        details = " ".join(str(x) for x in (_res_get(r, "details") or [])) + " " + str(_res_get(r, "message") or "")
        if (fix and fix in fixes) or (code and _res_get(r, "error_code") == code) or (detail and detail in details):
            out.append(str(_res_get(r, "market") or ""))
    return out


_KO_MARKETS = ("coupang", "smartstore", "elevenst")


def _is_ko(m: str) -> bool:
    return str(m or "").split(":")[0] in _KO_MARKETS


def plan(pd: dict, ex: dict, results) -> List[dict]:
    """고칠 일 목록 `[{kind, markets, keys, ...}]` — AI 호출 하나에 일 하나. 막힌 항목(되돌리기)·최근 실패는 뺀다."""
    tasks: List[dict] = []
    # a 옵션 값
    mk = [m for m in _held(results, fix="translate") + _held(results, detail="옵션 값 미해석") if _is_ko(m)]
    if mk:
        from src.seller_console.upload_dispatcher import unresolved_option_values
        vals = [v for v in unresolved_option_values(pd) if not _skip(ex, "option_value:" + v)]
        if vals:
            tasks.append({"kind": "option_value", "markets": sorted(set(mk)), "values": vals[:30]})
    # a' 옵션 값 축약(네이버 25자) — 지금 한국어 값이 상한을 넘는 것만(원문 열쇠로 덮어쓴다)
    mk = [m for m in _held(results, fix="option_short") if _is_ko(m)]
    if mk:
        drop_stale_short(ex, pd)
        rows = [r for r in long_option_values(pd) if not _skip(ex, "option_short:" + r["src"])]
        if rows:
            tasks.append({"kind": "option_short", "markets": sorted(set(mk)), "rows": rows[:30],
                          "siblings": all_option_values(pd)[:60]})
    # b 네이버 카테고리
    mk = _held(results, fix="naver_category")
    if mk and not _skip(ex, "naver_category"):
        try:
            from src.uploaders import naver_categories as _nc
            h = _nc.hold(pd) or {}
        except Exception:
            h = {}
        if h.get("candidates"):
            tasks.append({"kind": "naver_category", "markets": mk, "candidates": h["candidates"][:5],
                          "images": _rep_images(pd)})
    # c 상품명(표시광고·금지어·원문)은 `reject_autofix`(#886)가 같은 잡에서 먼저 고친다 — 여기서 또 묻지 않는다(카드 줄·되돌리기만 합친다)
    # e 고시정보(원산지 등)
    mk = _held(results, detail="고시정보 실값 미확인")
    if mk and not _skip(ex, "notice:origin"):
        tasks.append({"kind": "notice", "markets": mk})
    # f 쿠팡 필수 구매옵션
    names: List[str] = []
    mk = []
    for r in results or []:
        if _res_get(r, "ok") or not str(_res_get(r, "market") or "").startswith("coupang"):
            continue
        for d in _res_get(r, "details") or []:
            d = str(d)
            m1 = re.match(r"필수 옵션(?:\(택1\))?:\s*(.+?)(?:\s+—.*)?$", d)
            if m1:
                for n in re.split(r",\s*|\s+또는\s+", m1.group(1)):
                    n = n.strip()
                    if n and n not in names and not _skip(ex, "coupang_attr:" + n):
                        names.append(n)
                mk.append(str(_res_get(r, "market")))
    if names:
        tasks.append({"kind": "coupang_attr", "markets": sorted(set(mk)), "names": names[:6]})
    # f' 쿠팡 「메타 속성 고르기」 — 메타에 없는 옵션 축 이름을 이 카테고리 메타 속성 중 하나로(고를 목록 = 쿠팡 메타 그대로)
    picks, mk = [], []
    for r in results or []:
        if _res_get(r, "ok") or not str(_res_get(r, "market") or "").startswith("coupang"):
            continue
        for p in _res_get(r, "name_picks") or []:
            orig = str((p or {}).get("orig") or "").strip()
            if orig and p.get("choices") and not _skip(ex, "coupang_axis:" + orig) and all(x["orig"] != orig for x in picks):
                picks.append({"orig": orig, "label": str(p.get("label") or orig), "candidate": str(p.get("candidate") or ""),
                              "choices": [str(c) for c in p["choices"]][:40]})
                mk.append(str(_res_get(r, "market")))
    if picks:
        tasks.append({"kind": "coupang_axis", "markets": sorted(set(mk)), "picks": picks[:4]})
    return tasks


def long_option_values(pd: dict, cap: int = 0) -> List[dict]:
    """한국어 옵션 값이 네이버 상한(25자)을 넘는 것 `[{src, ko}]` — **SKU 원문 스펙 조각**을 열쇠로(네이버 계획이 찾는 그 열쇠).

    Y11-Q(오너 2026-10-16 00:38): 예전엔 화면 옵션 목록에서 열쇠를 뽑아 **한국어 값**이 열쇠로 저장됐다 — 네이버 계획은
    SKU 원문(「雾蓝色半皮【…】」)으로 덮어쓰기를 찾으니 못 찾아 축약이 적용되지 않았고, 재검증해도 25자 초과 그대로였다.
    """
    from src.collectors import option_ko as K
    from src.uploaders.naver_options import OPTION_NAME_MAX, _skus
    cap = cap or OPTION_NAME_MAX
    out: List[dict] = []
    for k in _skus(pd):
        for s_ in (k.get("spec") or []):
            src = str(s_ or "").strip()
            ko = (K.spec_ko(pd, [src]) or [""])[0]
            if src and ko and len(ko) > cap and all(x["src"] != src for x in out):
                out.append({"src": src, "ko": ko})
    return out


_SHORT_KEEP = ("풀가죽", "반가죽", "발받침", "오토만", "스툴", "세트")


def _words(s: str) -> List[str]:
    return [w for w in re.split(r"[\s/·,()\[\]+]+", str(s or "")) if w]


def short_guard(ko: str, short: str) -> str:
    """Y11-Q 축약 품질 — 통과면 "", 아니면 버리는 이유.

    ① 단어 중간 절단 금지: 줄인 값의 낱말마다 원래 값의 낱말(또는 붙어 있던 낱말 몇 개를 이은 것) — 「천연소」(천연+소가죽의 「소」) 버림.
    ② 지킬 말: 색상(원래 값 첫 낱말)·가죽 등급(풀가죽/반가죽)·발받침·오토만 등은 원래 값에 있으면 줄인 값에도 있어야 한다.
    """
    ow = _words(ko)
    joined = {"".join(ow[i:j]) for i in range(len(ow)) for j in range(i + 1, min(len(ow), i + 4) + 1)}
    cut = [w for w in _words(short) if w not in joined]
    if cut:
        return f"단어 중간 절단({', '.join(cut[:3])})"
    flat = re.sub(r"\s+", "", short)
    lost = [k for k in _SHORT_KEEP if k in ko and k not in flat]
    if ow and ow[0] not in flat:
        lost.insert(0, f"색상 「{ow[0]}」")
    if lost:
        return f"지킬 말 빠짐({', '.join(lost[:3])})"
    return ""


def drop_stale_short(ex: dict, pd: dict) -> List[str]:
    """열쇠가 SKU 원문 스펙이 아닌 옛 축약(Y11-P 첫 등록 — 한국어 값 열쇠)을 지운다 — AI가 만든 값만, 수집 원본은 그대로."""
    raws = {str(x).strip() for k in (pd.get("skus") or []) if isinstance(k, dict) for x in (k.get("spec") or [])}
    fx = fixes_of(ex)
    stale = [k for k in list(fx) if k.startswith("option_short:") and k.split(":", 1)[1] not in raws]
    if not stale:
        return []
    ov = dict(ex.get("option_value_overrides") or {}) if isinstance(ex.get("option_value_overrides"), dict) else {}
    for k in stale:
        src = k.split(":", 1)[1]
        if ov.get(src) == fx[k].get("after"):
            ov.pop(src, None)
        fx.pop(k, None)
    ex["option_value_overrides"] = ov
    pd["option_value_overrides"] = dict(ov)
    return stale


def all_option_values(pd: dict) -> List[str]:
    from src.collectors import option_ko as K
    return [v["ko"] or v["src"] for a in K.options_view(pd) for v in a["values"]]


def _rep_images(pd: dict) -> List[str]:
    """대표 사진 1장(카테고리 고르기용 — Y11-O 「상품명·이미지로」). http(s) 주소만."""
    for k in ("images_ko", "images"):
        for x in pd.get(k) or []:
            u = x.get("url") if isinstance(x, dict) else x
            if isinstance(u, str) and u.startswith(("http://", "https://")):
                return [u]
    return []


def record_fixed_category(pd: dict, ex: dict, results) -> bool:
    """Y11-O — 고정 매핑표로 정한 네이버 카테고리를 수집 기록에 적고 「AI가 고쳤어요 — 카테고리」 줄에 올린다(AI 호출 없음).
    스마트스토어를 검증했을 때만 · 오너가 지정했거나 되돌렸으면 손대지 않는다. 적었으면 True."""
    if not any(str(_res_get(r, "market") or "").startswith("smartstore") for r in results or []):
        return False
    if str(ex.get("naver_category_id") or "").strip() or _skip(ex, "naver_category"):
        return False
    try:
        from src.uploaders import naver_categories as _nc
        cid, src = _nc.pick(pd)
        if src != "map" or not cid:
            return False
        s = _nc.suggest(pd)
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[AI 자동수정] 고정 매핑표 기록 실패: %s", exc)
        return False
    alts = " · ".join(a.get("name", "").split(">")[-1] for a in s.get("alts") or [] if a.get("name"))
    ex["naver_category_id"] = cid
    pd["naver_category_id"] = cid
    pd["naver_category_auto"] = {"after": cid, "provider": "map"}
    _mark(ex, "naver_category", "naver_category", f"{s.get('name') or cid}" + (f" (다른 후보: {alts})" if alts else ""),
          "", cid, s.get("map_why") or f"고정 매핑표 — 쿠팡 「{s.get('coupang') or ''}」", {"provider": "map", "model": ""})
    return True


def record_coupang_rule(pd: dict, ex: dict, results) -> bool:
    """Y11O-1 — 상품명 규칙이 쿠팡 예측 리프를 바로잡았으면 「AI가 고쳤어요 — 쿠팡 카테고리」 줄에 적는다(AI 호출 없음).
    쿠팡을 검증했을 때만 · 오너가 되돌렸으면(막힘) 다시 적지 않는다. 되돌리면 그 상품은 규칙을 끈다(`overlay`)."""
    if not any(str(_res_get(r, "market") or "").startswith("coupang") for r in results or []):
        return False
    if _skip(ex, "coupang_category"):
        return False
    try:
        from src.uploaders import naver_categories as _nc
        g = _nc.coupang_guess(pd)
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[AI 자동수정] 쿠팡 상품명 규칙 기록 실패: %s", exc)
        return False
    if not g.get("rule_why"):
        return False
    pred = g.get("predicted") or {}
    _mark(ex, "coupang_category", "coupang_category", f"{pred.get('name') or pred.get('id')} → {g.get('name')}",
          str(pred.get("id") or ""), str(g.get("id") or ""), g["rule_why"], {"provider": "rule", "model": ""})
    return True


# ── AI 호출 ────────────────────────────────────────────────────────────────────────────────────

_SYSTEM = ("당신은 해외 구매대행 상품을 한국 오픈마켓(쿠팡·네이버 스마트스토어)에 올리는 등록 담당자입니다. "
           "주어진 사실에서만 답하고 없는 정보(브랜드·소재·수치·원산지·인증)는 지어내지 마세요. "
           "상표·브랜드·캐릭터·영화·게임 이름은 새로 넣지 마세요. 답은 JSON 객체 하나만(설명·코드 펜스 없이).")


def _context(pd: dict) -> str:
    title = str(pd.get("title_ko") or pd.get("title") or "")[:120]
    src = str(pd.get("title_src") or pd.get("title_en") or "")[:160]
    opts = []
    for o in (pd.get("options") or [])[:4]:
        if isinstance(o, dict):
            vals = [str(v) for v in (o.get("values") or [])][:12]
            opts.append(f"- {o.get('name_ko') or o.get('name')}: {', '.join(vals)}")
    return f"상품명(한국어): {title}\n원문 상품명: {src or '(없음)'}\n옵션:\n" + ("\n".join(opts) or "(없음)")


def _prompt(task: dict, pd: dict) -> Tuple[str, str]:
    """`(prompt, size)`"""
    k = task["kind"]
    if k == "option_value":
        return (_context(pd) + "\n\n아래 옵션 값(중국어 등 원문)을 한국 쇼핑몰 옵션 값으로 옮기세요.\n"
                "규칙: 한국어(또는 원문의 영문·숫자 그대로), 25자 이하, 원문의 숫자·영문·단위는 빠짐없이 그대로. "
                "값 끝의 발송 소요(예: 2-3周发货·现货·预售)는 옵션 값이 아니니 빼고 핵심만. 색 이름은 자연스러운 한국어 색 이름. "
                "판촉어(신상·인기·특가) 금지.\n"
                "값:\n" + "\n".join(f"- {v}" for v in task["values"])
                + '\n\n답 형식: {"values": {"원문 값": "한국어 값", ...}}', "small")
    if k == "option_short":
        from src.uploaders.naver_options import OPTION_NAME_MAX as _cap
        # 재료 = 용어집·번역 사슬(`resolve_option_value`)이 이미 옮긴 한국어 값 — 원문을 다시 옮기지 않고 줄이기만
        return (_context(pd) + f"\n\n네이버 스마트스토어 옵션 값은 {_cap}자까지예요. 아래 한국어 옵션 값을 **{_cap}자 이하**로 줄이세요.\n"
                "규칙: **색상·가죽 등급(풀가죽/반가죽)·발받침 여부는 반드시 남기고**, 소재 수식어(천연·소가죽·가죽·포함 등)처럼 "
                "옵션끼리 같은 말부터 **낱말째** 빼세요. 낱말을 중간에서 자르지 마세요(「천연 소가죽」→「천연소」 금지). "
                "예: 「블랙 풀가죽 아닐린 가죽 / 발받침 포함 천연 소가죽」 → 「블랙 풀가죽 아닐린 발받침」. "
                "지금 값에 있는 숫자·영문은 그대로. 새 정보·판촉어 금지. "
                "아래 「다른 옵션 값」과 **같아지면 안 돼요**(서로 다른 옵션은 다른 값).\n"
                "줄일 값:\n" + "\n".join(f"- {r['ko']}" for r in task["rows"])
                + "\n다른 옵션 값:\n" + "\n".join(f"- {x}" for x in task.get("siblings") or [])
                + '\n\n답 형식: {"values": {"지금 값": "줄인 값", ...}}', "small")
    if k == "naver_category":
        cands = "\n".join(f"- {c['id']}: {c.get('name')}" for c in task["candidates"])
        photo = "첨부한 대표 사진과 " if task.get("images") else ""
        return (_context(pd) + f"\n\n{photo}상품명을 보고 이 상품에 가장 맞는 네이버 카테고리를 아래 후보 중 **하나만** 고르세요(후보 밖 ID 금지).\n"
                + cands + '\n\n답 형식: {"id": "후보 ID", "why": "한 줄 이유(30자 이내)"}', "small")
    if k == "notice":
        spec = "\n".join(f"- {a}: {b}" for sp in (pd.get("detail_specs") or [])[:20]
                         if isinstance(sp, (list, tuple)) and len(sp) >= 2 for a, b in [sp[:2]])
        desc = str(pd.get("description") or "")[:1200]
        return (_context(pd) + f"\n\n규격표:\n{spec or '(없음)'}\n상세 원문:\n{desc or '(없음)'}\n\n"
                "상품정보고시의 원산지(제조국)가 위 규격표·상세 원문에 **글자로 적혀 있으면** 그 나라를 한국어로 답하세요"
                "(예: 产地 中国 → 중국). 적혀 있지 않으면 null(추정 금지 — 소싱처 나라로 짐작하지 마세요).\n"
                '답 형식: {"origin": "나라 이름 또는 null", "why": "근거가 된 원문 글자"}', "small")
    if k == "coupang_axis":
        rows = []
        for p in task["picks"]:
            vals = next((o.get("values") for o in (pd.get("options") or []) if isinstance(o, dict)
                         and p["orig"] in (o.get("src_name"), o.get("name"))), []) or []
            rows.append(f"- 옵션 「{p['label']}」(원문 {p['orig']}) 값 예: {', '.join(str(v) for v in vals[:6])}\n"
                        f"  고를 수 있는 쿠팡 메타 속성: {' | '.join(p['choices'])}")
        return (_context(pd) + "\n\n쿠팡 카테고리 메타에 이 옵션 이름이 없어 등록이 멈췄어요. 각 옵션을 **아래 목록 중 하나**의 "
                "쿠팡 메타 속성으로 연결하세요(목록 밖 이름 금지 · 값의 뜻과 맞는 것 · 맞는 게 없으면 그 옵션은 빼세요).\n"
                + "\n".join(rows) + '\n\n답 형식: {"picks": [{"orig": "원문 옵션 이름", "meta": "고른 메타 속성", "why": "한 줄 근거"}]}',
                "small")
    if k == "coupang_attr":
        return (_context(pd) + "\n\n쿠팡 카테고리가 요구하는 필수 구매옵션 값을 정하세요: " + ", ".join(task["names"])
                + "\n위 상품명·옵션에 근거가 있는 값만(한국어 또는 숫자, 30자 이하). 근거가 없으면 그 속성은 빼세요. "
                "수량·개수 속성은 묶음 표시가 없으면 1.\n"
                '답 형식: {"attributes": [{"name": "속성 이름", "value": "값", "why": "근거"}]}', "small")
    return "", "small"


def _call(task: dict, pd: dict) -> dict:
    from src.ai import llm
    prompt, size = _prompt(task, pd)
    imgs = list(task.get("images") or [])
    r = llm.complete(prompt, system=_SYSTEM, size=size, max_tokens=1200, purpose="ai_fix:" + task["kind"],
                     timeout=20.0, json_mode=True, images=imgs or None)
    if imgs and not r.get("text") and not r.get("no_key"):           # 사진을 못 읽었으면(주소 막힘 등) 상품명만으로 한 번 더
        r = llm.complete(prompt, system=_SYSTEM, size=size, max_tokens=1200, purpose="ai_fix:" + task["kind"],
                         timeout=20.0, json_mode=True)
    r["json"] = llm.parse_json(r.get("text") or "") if r.get("text") else None
    return r


# ── 적용 ──────────────────────────────────────────────────────────────────────────────────────

def _apply(task: dict, ans: dict, pd: dict, ex: dict, meta: dict) -> List[str]:
    """검사를 통과한 답을 `ex`(수집 기록)와 `pd`(이번 검증 재료)에 적용 — 적용한 열쇠 목록."""
    from src.collectors import option_leadtime as _olt
    from src.uploaders.coupang_options import lost_tokens
    done: List[str] = []
    k = task["kind"]
    if k == "option_value":
        got = ans.get("values") if isinstance(ans.get("values"), dict) else {}
        ov = dict(ex.get("option_value_overrides") or {}) if isinstance(ex.get("option_value_overrides"), dict) else {}
        for v in task["values"]:
            key = "option_value:" + v
            ko = str(got.get(v) or "").strip()
            core = (_olt.parse(v) or {}).get("core") or v            # 발송 소요 꼬리를 뗀 원문으로 숫자·영문 검사
            why = guard(ko) or ("25자 초과" if len(ko) > _MAX_VALUE else "") \
                or ("원문 숫자·영문 빠짐(" + ", ".join(lost_tokens(core, ko)) + ")" if lost_tokens(core, ko) else "")
            if why:
                _tried(ex, key, why)
                continue
            before = ov.get(v, "")
            ov[v] = ko
            _mark(ex, key, k, f"{_olt.display(core)} → {ko}", before, ko, "", meta)
            done.append(key)
        if done:
            ex["option_value_overrides"] = ov
            pd["option_value_overrides"] = dict(ov)
    elif k == "option_short":
        from src.uploaders.naver_options import OPTION_NAME_MAX as _cap
        got = ans.get("values") if isinstance(ans.get("values"), dict) else {}
        ov = dict(ex.get("option_value_overrides") or {}) if isinstance(ex.get("option_value_overrides"), dict) else {}
        taken = {str(x).strip() for x in (task.get("siblings") or [])} - {r["ko"] for r in task["rows"]}
        for r in task["rows"]:
            key = "option_short:" + r["src"]
            short = str(got.get(r["ko"]) or "").strip()
            why = guard(short) or (f"{_cap}자 초과" if len(short) > _cap else "") \
                or ("다른 옵션 값과 같아짐" if short in taken else "") or short_guard(r["ko"], short) \
                or ("지금 값의 숫자·영문 빠짐(" + ", ".join(lost_tokens(r["ko"], short)) + ")" if lost_tokens(r["ko"], short) else "")
            if why:
                _tried(ex, key, why)
                continue
            taken.add(short)
            before = ov.get(r["src"], "")
            ov[r["src"]] = short
            _mark(ex, key, k, f"{r['ko']} → {short}", before, short, f"{len(r['ko'])}자 → {len(short)}자", meta)
            done.append(key)
        if done:
            ex["option_value_overrides"] = ov
            pd["option_value_overrides"] = dict(ov)
    elif k == "naver_category":
        cid = str(ans.get("id") or "").strip()
        cand = next((c for c in task["candidates"] if str(c["id"]) == cid), None)
        if not cand:
            _tried(ex, "naver_category", f"후보 밖 ID({cid or '없음'})")
            return done
        before = str(ex.get("naver_category_id") or "")
        ex["naver_category_id"] = cid
        pd["naver_category_id"] = cid
        pd["naver_category_auto"] = {"after": cid, "provider": meta.get("provider") or "ai"}
        others = " · ".join(str(c.get("name") or c["id"]) for c in task["candidates"] if str(c["id"]) != cid)[:160]
        _mark(ex, "naver_category", k, f"{cand.get('name')}" + (f" (다른 후보: {others})" if others else ""),
              before, cid, str(ans.get("why") or ""), meta)
        done.append("naver_category")
    elif k == "notice":
        origin = ans.get("origin")
        origin = str(origin).strip() if origin not in (None, "", "null") else ""
        if not origin or guard(origin) or len(origin) > 20:
            _tried(ex, "notice:origin", "원문에 원산지 표기 없음" if not origin else (guard(origin) or "20자 초과"))
            return done
        before = str(ex.get("origin") or "")
        ex["origin"] = origin
        pd["origin"] = origin
        _mark(ex, "notice:origin", k, f"원산지 {origin}", before, origin, str(ans.get("why") or ""), meta)
        done.append("notice:origin")
    elif k == "coupang_axis":
        got = ans.get("picks") if isinstance(ans.get("picks"), list) else []
        names = dict(ex.get("coupang_option_names") or {}) if isinstance(ex.get("coupang_option_names"), dict) else {}
        for p in task["picks"]:
            key = "coupang_axis:" + p["orig"]
            a = next((x for x in got if isinstance(x, dict) and str(x.get("orig") or "").strip() == p["orig"]), None)
            chosen = str((a or {}).get("meta") or "").strip()
            if not chosen or chosen not in p["choices"]:
                _tried(ex, key, "목록 밖 이름" if chosen else "답 없음")
                continue
            before = names.get(p["orig"], "")
            names[p["orig"]] = chosen
            _mark(ex, key, k, f"{p['label']} → {chosen}", before, chosen, str((a or {}).get("why") or ""), meta)
            done.append(key)
        if done:
            ex["coupang_option_names"] = names
            pd["coupang_option_names"] = dict(names)
    elif k == "coupang_attr":
        got = ans.get("attributes") if isinstance(ans.get("attributes"), list) else []
        cur = [a for a in (ex.get("coupang_attributes") or []) if isinstance(a, dict)]
        for n in task["names"]:
            key = "coupang_attr:" + n
            a = next((x for x in got if isinstance(x, dict) and str(x.get("name") or "").strip() == n), None)
            val = str((a or {}).get("value") or "").strip()
            why = "근거 없음(답 없음)" if not val else (guard(val) or ("30자 초과" if len(val) > 30 else ""))
            if why:
                _tried(ex, key, why)
                continue
            before = next((str(x.get("attributeValueName") or "") for x in cur if x.get("attributeTypeName") == n), "")
            cur = [x for x in cur if x.get("attributeTypeName") != n] + [{"attributeTypeName": n, "attributeValueName": val}]
            _mark(ex, key, k, f"{n} {val}", before, val, str((a or {}).get("why") or ""), meta)
            done.append(key)
        if done:
            ex["coupang_attributes"] = cur
            pd["coupang_attributes"] = list(cur)
    return done


def run_round(pd: dict, ex: dict, results, *, calls_left: int) -> Dict[str, Any]:
    """한 회전 — 일마다 AI 한 번(남은 호출 안에서). `{calls, usd, applied:[key], markets:[재검증할 마켓], log:[...]}`."""
    out = {"calls": 0, "usd": 0.0, "applied": [], "markets": [], "log": [], "providers": []}
    for task in plan(pd, ex, results):
        if out["calls"] >= calls_left:
            out["log"].append(f"{KIND_LABEL[task['kind']]}: 호출 상한(상품당 {MAX_CALLS}회)에 걸려 건너뜀")
            break
        r = _call(task, pd)
        out["calls"] += 1
        out["usd"] += float(r.get("usd") or 0)
        if r.get("provider"):
            out["providers"].append(f"{r['provider']}:{r.get('model')}")
        if not r.get("json"):
            why = r.get("error") or "JSON 답이 아님"
            out["log"].append(f"{KIND_LABEL[task['kind']]}: AI 실패 — {str(why)[:120]}")
            if r.get("no_key"):
                break
            continue
        keys = _apply(task, r["json"], pd, ex, {"provider": r.get("provider"), "model": r.get("model")})
        out["log"].append(f"{KIND_LABEL[task['kind']]}: {len(keys)}개 적용")
        if keys:
            out["applied"] += keys
            out["markets"] += [m for m in task["markets"] if m not in out["markets"]]
    return out


def overlay(pd: dict, ex: dict) -> dict:
    """저장된 AI 수정을 이번 재료(`pd` — 화면이 보낸 상품)에 얹는다. 사전검증·등록이 **같은 값**을 보게.

    화면은 사전검증 전에 그린 값을 들고 있다(AI가 고친 뒤 새로고침 안 함) — 저장본이 정본. 단 셀러가 그 칸을
    AI 뒤에 손으로 바꿨으면(화면 값이 AI 전 값도 AI 값도 아님) 셀러 값을 둔다.
    """
    # Y11O-1: 카테고리 상품명 규칙의 라운지 신호(원문 「躺椅」 등)는 저장본 원문 상품명에 있다 — 화면은 한국어 상품명만 보낸다
    src_titles = " ".join(dict.fromkeys(str(ex.get(k) or "") for k in ("title", "title_en", "title_src") if ex.get(k)))
    if src_titles and not pd.get("category_text"):
        pd["category_text"] = src_titles
    if "naver_category" in blocked(ex):
        pd["naver_category_no_auto"] = True          # Y11-O: 되돌린 카테고리를 고정 매핑표·쿠팡 예측이 다시 채우지 않게
    if "coupang_category" in blocked(ex):
        pd["coupang_category_no_override"] = True    # Y11O-1: 되돌린 쿠팡 상품명 규칙은 그 상품에서 끈다
    fx = fixes_of(ex)
    rev = {k: v for k, v in blocked(ex).items() if isinstance(v, dict) and "after" in v}
    if not fx and not rev:
        return pd
    ov = dict(pd.get("option_value_overrides") or {}) if isinstance(pd.get("option_value_overrides"), dict) else {}
    attrs = [a for a in (pd.get("coupang_attributes") or []) if isinstance(a, dict)]
    for key, f in fx.items():
        after, before = f.get("after"), f.get("before")
        if key.startswith(("option_value:", "option_short:")):
            v = key.split(":", 1)[1]
            if ov.get(v) in (None, "", before, after):
                ov[v] = after
        elif key == "naver_category":
            if str(pd.get("naver_category_id") or "") in ("", str(before or ""), str(after)):
                pd["naver_category_id"] = after
                # Y11-O: 출처(고정 매핑표·AI) — 카드가 「카테고리 지정」(오너)과 구분해 「카테고리 자동」으로
                pd["naver_category_auto"] = {"after": after, "provider": f.get("provider") or ""}
        elif key == "notice:origin":
            pd["origin"] = pd.get("origin") or after
        elif key.startswith("coupang_axis:"):
            cn = dict(pd.get("coupang_option_names") or {}) if isinstance(pd.get("coupang_option_names"), dict) else {}
            o = key.split(":", 1)[1]
            if cn.get(o) in (None, "", before, after):
                cn[o] = after
            pd["coupang_option_names"] = cn
        elif key.startswith("coupang_attr:"):
            n = key.split(":", 1)[1]
            cur = next((a for a in attrs if a.get("attributeTypeName") == n), None)
            if cur is None:
                attrs.append({"attributeTypeName": n, "attributeValueName": after})
            elif str(cur.get("attributeValueName") or "") in ("", str(before or "")):
                cur["attributeValueName"] = after
    # 되돌린 항목 — 화면이 아직 AI 값을 들고 있으면(되돌린 뒤 새로고침 전) 원래 값으로
    for key, r in rev.items():
        after, before = r.get("after"), r.get("before") or ""
        if key.startswith(("option_value:", "option_short:")):
            v = key.split(":", 1)[1]
            if ov.get(v) == after:
                if before:
                    ov[v] = before
                else:
                    ov.pop(v, None)
        elif key == "naver_category" and str(pd.get("naver_category_id") or "") == str(after):
            pd["naver_category_id"] = before
        elif key.startswith("coupang_axis:"):
            cn = dict(pd.get("coupang_option_names") or {}) if isinstance(pd.get("coupang_option_names"), dict) else {}
            o = key.split(":", 1)[1]
            if cn.get(o) == after:
                if before:
                    cn[o] = before
                else:
                    cn.pop(o, None)
                pd["coupang_option_names"] = cn
        elif key == "notice:origin" and pd.get("origin") == after:
            pd["origin"] = before
        elif key.startswith("coupang_attr:"):
            n = key.split(":", 1)[1]
            attrs = [a for a in attrs if not (a.get("attributeTypeName") == n and a.get("attributeValueName") == after)] + \
                ([{"attributeTypeName": n, "attributeValueName": before}] if before and not any(
                    a.get("attributeTypeName") == n for a in attrs) else [])
    pd["option_value_overrides"] = ov
    pd["coupang_attributes"] = attrs
    return pd


# ── 카드 · 되돌리기 ────────────────────────────────────────────────────────────────────────────

def summary(ex: dict) -> Dict[str, Any]:
    """카드 한 줄 「AI가 고쳤어요 — 옵션값 2개 · 카테고리 1개」 + 항목별 되돌리기 재료. 고친 게 없으면 {}."""
    fx = fixes_of(ex)
    items = [{"key": k, "kind": v.get("kind"), "kind_label": KIND_LABEL.get(v.get("kind"), v.get("kind")),
              "label": v.get("label"), "why": v.get("why", ""), "at": v.get("at")} for k, v in fx.items()]
    # #886 반려 사유 자동 수정(상품명·쿠팡 상품명·옵션 값 글자) — 같은 줄에 합친다. 칸마다 되돌리기(`reject:<n>`)
    rec = ex.get("reject_autofix") if isinstance(ex.get("reject_autofix"), dict) else None
    if rec and rec.get("status") == "done" and not rec.get("undone"):
        for i, c in enumerate(rec.get("changes") or []):
            if c.get("undone"):
                continue
            kl = KIND_LABEL["option_value"] if c.get("field") == "option" else KIND_LABEL["title"]
            items.append({"key": f"reject:{i}", "kind": "reject", "kind_label": kl,
                          "label": f"{c.get('label')} 「{c.get('before')}」 → 「{c.get('after')}」", "why": "", "at": rec.get("at")})
    a = ex.get("detail_auto") if isinstance(ex.get("detail_auto"), dict) else None
    if a and a.get("provider") in ("anthropic", "openai") and "detail" not in blocked(ex):
        items.append({"key": "detail", "kind": "detail", "kind_label": KIND_LABEL["detail"], "label": "상세 초안",
                      "why": "", "at": a.get("at")})
    if not items:
        return {}
    cnt: Dict[str, int] = {}
    for it in items:
        cnt[it["kind_label"]] = cnt.get(it["kind_label"], 0) + 1
    order = list(dict.fromkeys(KIND_LABEL.values()))
    keys = sorted(cnt, key=lambda k: order.index(k) if k in order else len(order))
    # Y11-P: 「옵션값 3개 축약」(오너 문구) — 축약은 말 순서가 다르다
    fmt = {"옵션값 축약": lambda n: f"옵션값 {n}개 축약"}
    return {"line": "AI가 고쳤어요 — " + " · ".join(fmt.get(k, lambda n, k=k: f"{k} {n}개")(cnt[k]) for k in keys),
            "items": items}


def revert(ex: dict, key: str) -> bool:
    """되돌리기 — 원래 값으로 돌리고 그 항목은 다시 AI가 고치지 않게 막는다(다음 사전검증에서 그 보류가 다시 보인다)."""
    key = str(key or "")
    if key.startswith("reject:"):
        # #886 기록의 그 칸만 되돌린다(`reject_autofix.apply`가 되돌린 칸은 싣지 않는다 · 같은 재료로 다시 묻지 않는다)
        rec = ex.get("reject_autofix") if isinstance(ex.get("reject_autofix"), dict) else None
        try:
            c = (rec or {}).get("changes", [])[int(key.split(":", 1)[1])]
        except (ValueError, IndexError, TypeError):
            return False
        if not isinstance(c, dict) or c.get("undone"):
            return False
        c["undone"] = _now()
        if all(x.get("undone") for x in rec.get("changes") or []):
            rec["undone"], rec["undone_at"] = True, _now()
        return True
    if key == "detail":
        if not isinstance(ex.get("detail_auto"), dict):
            return False
        ex.pop("detail_auto", None)
        ex.setdefault("ai_fix_blocked", {})["detail"] = _now()
        return True
    f = fixes_of(ex).get(key)
    if not f:
        return False
    before = f.get("before")
    if key.startswith(("option_value:", "option_short:")):
        ov = dict(ex.get("option_value_overrides") or {})
        v = key.split(":", 1)[1]
        if before:
            ov[v] = before
        else:
            ov.pop(v, None)
        ex["option_value_overrides"] = ov
    elif key == "naver_category":
        ex["naver_category_id"] = before or ""
    elif key == "notice:origin":
        if before:
            ex["origin"] = before
        else:
            ex.pop("origin", None)
    elif key.startswith("coupang_axis:"):
        cn = dict(ex.get("coupang_option_names") or {})
        o = key.split(":", 1)[1]
        if before:
            cn[o] = before
        else:
            cn.pop(o, None)
        ex["coupang_option_names"] = cn
    elif key.startswith("coupang_attr:"):
        n = key.split(":", 1)[1]
        cur = [x for x in (ex.get("coupang_attributes") or []) if isinstance(x, dict) and x.get("attributeTypeName") != n]
        if before:
            cur.append({"attributeTypeName": n, "attributeValueName": before})
        ex["coupang_attributes"] = cur
    ex["ai_fixes"].pop(key, None)
    man = ex.get("manual_fields") if isinstance(ex.get("manual_fields"), dict) else {}
    man.pop(key, None)
    ex.setdefault("ai_fix_blocked", {})[key] = {"at": _now(), "after": f.get("after"), "before": before}
    return True
