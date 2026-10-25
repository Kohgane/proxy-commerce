"""순찰 106-B(오너 2026-10-26) — 사전검증 「등록 품질」 줄: **보류가 아니라 주의**(등록은 막지 않는다).

배경(순찰 99, 원피스 `5d1b6679`): 사전검증 「통과」 안에 틀린 값 넷이 그대로 나갈 뻔했다 — 사이즈 「36 80-105근」(斤을 단위만 바꿈),
상품명 「Taffa 타파파 …」(가게 한자 이름 음차), 상세 17·18 중국 가게 배송·반품 약관, 원피스가 「대형화물」. 고친 뒤에도 같은 유형을
다음 상품에서 사람이 먼저 보게 한 자리에 모은다.

  ① option_cjk     나가는 옵션 값에 한자·「斤/근」이 남음      → 규칙(斤→kg 환산) · 그 밖 한자는 Y8 AI 옵션 값 고치기(같은 검사)
  ② title_brand    상품명이 브랜드 판정(`ko_polish.brand_prefix`)과 어긋남 — 가게 한자 이름 음차 → 규칙(라틴 표기 + 나머지)
  ③ shop_policy    나가는 상세 사진에 가게 약관 조각 2개 이상(「그래도 넣기」로 들어간 장) → 그 장 「그래도 넣기」 풀기(빠진다)
  ④ apparel_bulky  의류인데 배송이 대형화물                     → 자동으로 못 고침(무게·크기 직접 넣기 — 사이즈표 몸무게일 수 있다)

「자동 수정」(`apply_fixes`)은 고친 값을 수집 기록에 적고 `ai_fixes`에 남긴다(Y8 「AI가 고쳤어요」 줄 · 되돌리기 그대로).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_JIN_KO = re.compile(r"\d\s*근(?![가-힣])")          # 「80-105근」(근육·근처 같은 낱말은 아님)
_HANGUL_WORD = re.compile(r"^[가-힣]+$")
APPAREL_CODES = ("CLO",)


def _has_han(s: str) -> bool:
    from src.collectors.ko_polish import has_han
    return has_han(s)


def _bad_option_values(pd: dict) -> List[Dict[str, str]]:
    """나가는 옵션 값(`option_ko.options_view` — 쿠팡·네이버와 같은 사슬) 중 한자·斤·근이 남은 것 `[{src, out, why}]`."""
    from src.collectors import option_ko
    out = []
    for axis in option_ko.options_view(pd):
        for v in axis.get("values") or []:
            sent = str(v.get("ko") or v.get("src") or "")
            why = ("근(斤) 단위" if ("斤" in sent or _JIN_KO.search(sent)) else ("한자" if _has_han(sent) else ""))
            if why:
                out.append({"src": str(v.get("src") or ""), "out": sent, "why": why})
    return out


def _title_brand(ex: dict, pd: dict) -> Dict[str, str]:
    """상품명 맨 앞이 브랜드 판정과 어긋나면 `{want, now, han, latin}` — 아니면 {}."""
    from src.collectors.ko_polish import brand_prefix
    info = brand_prefix(str(ex.get("title") or pd.get("title_src") or ""), ex)
    if not info:
        return {}
    now = str(pd.get("title_ko") or pd.get("title") or "").strip()
    toks = now.split()
    if not toks:
        return {}
    latin, han = info["latin"], info["han"]
    rest = toks
    if toks[0].upper() == latin.upper():
        rest = toks[1:]
    # 음차 = 라틴 다음(또는 맨 앞) 낱말이 한글뿐이고 글자 수가 한자 수와 같다(唐发发 → 타파파)
    if rest and _HANGUL_WORD.match(rest[0]) and len(rest[0]) == len(han):
        want = " ".join([latin] + rest[1:]).strip()
        return {"want": want, "now": now, "han": han, "latin": latin, "dropped": rest[0]}
    return {}


def _policy_images(ex: dict) -> List[int]:
    """나가는(제외 안 된) 상세 사진 중 가게 약관 조각이 2개 이상인 장의 번호(0부터)."""
    from src.services import detail_image_plan as dip
    originals = [u for u in (ex.get("detail_images") or []) if u]
    hits = []
    for e in ex.get("detail_images_ko") or []:
        if not isinstance(e, dict):
            continue
        i = int(e.get("idx", -1))
        if not (0 <= i < len(originals)):
            continue
        text = dip.entry_text(e)
        if len([t for t in dip.SHOP_POLICY if t in text]) < dip.SHOP_POLICY_MIN:
            continue
        if dip.verdict(e, originals[i])["use"] != "excluded":
            hits.append(i)
    return sorted(set(hits))


def _apparel_bulky(pd: dict) -> str:
    """의류인데 배송 계산이 대형화물이면 그 줄(배송 엔진 문구) — 아니면 ""."""
    code = str(pd.get("category_code") or pd.get("category") or "").upper()
    if code not in APPAREL_CODES:
        try:
            from src.seller_console.category_classifier import classify
            code = str((classify(str(pd.get("title_ko") or pd.get("title") or "")) or {}).get("code") or "")
        except Exception:                                        # noqa: BLE001
            code = ""
    if code not in APPAREL_CODES:
        return ""
    try:
        from src.seller_console.shipping_ratio import estimate
        est = estimate(pd, str(pd.get("seller_id") or ""), "coupang")
    except Exception as exc:                                     # noqa: BLE001 — 못 재면 말하지 않는다(가짜 경고 금지)
        logger.warning("[등록 품질] 배송 판정 실패: %s", exc)
        return ""
    if est.get("state") == "bulky" or est.get("bulky") or est.get("code") == "bulky_carrier":
        return str(est.get("line") or "대형화물")
    return ""


def checks(ex: dict, pd: dict) -> List[Dict[str, Any]]:
    """`[{code, line, fix}]` — `fix`는 `rule`(규칙으로 고침) · `ai`(AI로 고침) · `""`(사람이 고칠 것)."""
    ex, pd = ex or {}, pd or {}
    out: List[Dict[str, Any]] = []
    try:
        bad = _bad_option_values(pd)
        if bad:
            jin = [b for b in bad if b["why"].startswith("근")]
            out.append({"code": "option_cjk", "fix": "rule" if len(jin) == len(bad) else "ai", "n": len(bad),
                        "line": f"옵션 값에 한자·근(斤) 단위가 남았어요 {len(bad)}개 — 「{bad[0]['out'][:30]}」"
                                + (" · 斤은 kg으로 환산해요(1근 = 0.5kg)" if jin else "")})
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[등록 품질] 옵션 값 검사 실패: %s", exc)
    try:
        tb = _title_brand(ex, pd)
        if tb:
            out.append({"code": "title_brand", "fix": "rule",
                        "line": f"상품명에 가게 한자 이름 「{tb['han']}」의 음차 「{tb['dropped']}」가 들어갔어요 — "
                                f"브랜드는 「{tb['latin']}」로만: 「{tb['want'][:40]}」"})
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[등록 품질] 상품명 브랜드 검사 실패: %s", exc)
    try:
        pi = _policy_images(ex)
        if pi:
            out.append({"code": "shop_policy", "fix": "rule", "idx": pi,
                        "line": f"상세 {', '.join(str(i + 1) for i in pi[:6])}번 사진에 중국 가게 배송·반품 약관이 있어요"
                                " — 「그래도 넣기」로 들어간 장이에요(한국 손님에겐 틀린 약속)"})
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[등록 품질] 상세 약관 검사 실패: %s", exc)
    try:
        ab = _apparel_bulky(pd)
        if ab:
            out.append({"code": "apparel_bulky", "fix": "",
                        "line": "의류인데 배송이 대형화물로 잡혔어요 — 사이즈표의 몸무게를 상품 무게로 읽었을 수 있어요. "
                                "「무게·크기 직접 넣기」로 바로잡아 주세요(" + ab[:60] + ")"})
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[등록 품질] 의류 배송 검사 실패: %s", exc)
    return out


def card(flags: List[Dict[str, Any]]) -> Dict[str, Any]:
    """카드에 실을 모양 — `{lines:[{code, line, fix}], fixable}`. 비면 {}."""
    if not flags:
        return {}
    return {"lines": [{"code": f["code"], "line": f["line"], "fix": f.get("fix") or ""} for f in flags],
            "fixable": sum(1 for f in flags if f.get("fix"))}


def _fix_options(ex: dict, pd: dict, log: List[str], left: List[str], *, ai: bool) -> None:
    from src.collectors.ko_polish import fix_jin_ko, jin_to_kg, has_han
    from src.services import ai_fix
    ov = dict(ex.get("option_value_overrides") or {}) if isinstance(ex.get("option_value_overrides"), dict) else {}
    need_ai = []
    for b in _bad_option_values(pd):
        src, now = b["src"], b["out"]
        new = fix_jin_ko(src, now) if b["why"].startswith("근") else now
        if "斤" in new:
            new = jin_to_kg(new)
        if new != now and not has_han(new) and not _JIN_KO.search(new):
            before = ov.get(src, "")
            ov[src] = new
            ai_fix._mark(ex, "option_value:" + src, "option_value", f"{now} → {new}", before, new, "규칙(斤→kg)",
                         {"provider": "rule", "model": "listing_quality"})
            log.append(f"옵션 값 「{now}」 → 「{new}」")
        else:
            need_ai.append(src)
    ex["option_value_overrides"] = ov
    pd["option_value_overrides"] = dict(ov)
    if not need_ai:
        return
    if not ai:
        left += [f"옵션 값 「{v}」 — AI로 고칠 차례(이번엔 규칙만)" for v in need_ai]
        return
    # Y8 경로 그대로 — 같은 프롬프트·같은 검사(한자·가나·IP·상표·원문 숫자 빠짐)·같은 기록(되돌리기)
    task = {"kind": "option_value", "markets": [], "values": need_ai[:30]}
    r = ai_fix._call(task, pd)
    if not r.get("json"):
        left.append(f"옵션 값 {len(need_ai)}개 — AI가 못 고쳤어요({str(r.get('error') or 'JSON 답 아님')[:80]})")
        return
    keys = ai_fix._apply(task, r["json"], pd, ex, {"provider": r.get("provider"), "model": r.get("model")})
    log.append(f"옵션 값 {len(keys)}개 AI로 고침")
    miss = [v for v in need_ai if "option_value:" + v not in keys]
    if miss:
        left.append(f"옵션 값 {len(miss)}개는 AI 답이 검사에서 떨어졌어요 — 옵션 탭에서 직접 고쳐 주세요(「{miss[0][:20]}」)")


def apply_fixes(ex: dict, pd: dict, *, ai: bool = True) -> Dict[str, Any]:
    """「자동 수정」 — `ex`(수집 기록)·`pd`(이번 재료)를 고친다. `{applied:[줄], left:[줄], changed: bool}`. 저장은 부르는 쪽."""
    log: List[str] = []
    left: List[str] = []
    for f in checks(ex, pd):
        c = f["code"]
        try:
            if c == "option_cjk":
                _fix_options(ex, pd, log, left, ai=ai)
            elif c == "title_brand":
                tb = _title_brand(ex, pd)
                if tb:
                    ex["title_ko"] = pd["title_ko"] = tb["want"]
                    if pd.get("title") == tb["now"]:
                        pd["title"] = tb["want"]
                    ex.setdefault("quality_fixes", []).append({"code": c, "before": tb["now"], "after": tb["want"]})
                    log.append(f"상품명 「{tb['now'][:30]}」 → 「{tb['want'][:30]}」")
            elif c == "shop_policy":
                idx = set(_policy_images(ex))
                for e in ex.get("detail_images_ko") or []:
                    if isinstance(e, dict) and int(e.get("idx", -1)) in idx and e.get("promo_include"):
                        e.pop("promo_include", None)
                left_idx = _policy_images(ex)
                n = len(idx) - len(left_idx)
                if n:
                    log.append(f"상세 약관 사진 {n}장 「그래도 넣기」 풀기 — 등록에서 빠져요")
                if left_idx:
                    left.append(f"상세 {', '.join(str(i + 1) for i in left_idx)}번은 자동으로 못 뺐어요 — 상세 사진 목록에서 빼 주세요")
            elif c == "apparel_bulky":
                left.append("의류 대형화물 — 무게·크기는 자동으로 못 고쳐요(「무게·크기 직접 넣기」)")
        except Exception as exc:                                 # noqa: BLE001 — 한 항목 실패가 나머지를 막지 않는다
            logger.warning("[등록 품질] 자동 수정 실패 %s: %s", c, exc)
            left.append(f"{c} — 고치다 실패({type(exc).__name__})")
    return {"applied": log, "left": left, "changed": bool(log)}
