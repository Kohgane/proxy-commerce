"""Y7-N(오너 2026-10-10 22:1x) — 상세설명 칸에 들어온 **가게 UI 글자** 판정.

실측: BLACKHOLES 블랙홀 미니 벽등(타오바오 1077964821879) 상세설명 = 「沉默流浪汉 / 4.5 / 好评率84% / 平均2天内发货 /
客服满意度94%」 — 가게 이름·평점·호평률·발송·고객만족. 보강의 화면 읽기(빈 칸 채움)가 가게 카드를 본문으로 집었다.
원문 그대로는 마켓 규칙(한국어만)이 다 빼지만, 번역본에선 「침묵 방랑자 / 평균 2일 이내 발송」이 남아 **셀러 글**로 읽혀
상세 자동 초안이 막혔다.

판정(표 = `detail_ui_junk.json`):
  - 줄을 `\\n`과 `/`·`|`로 조각낸다(한 줄에 이어 붙은 가게 카드도 같은 답).
  - 조각마다 (a) 평점 패턴 (b) 토큰(zh·ko·en, 부분 일치) — 하나라도 걸리면 UI 조각.
  - (c) 조각이 `max_lines` 이하이고 전부 UI 조각이면 **본문 전체가 비어 있음**. 가게 이름처럼 토큰이 없는 짧은 조각
    (`name_line_max_chars`자 이하) 1개는 허용 — UI 조각이 2개 이상일 때만(상품 한 줄 + 평점 하나를 버리지 않게).
본문이 길거나 상품 문장이 하나라도 있으면 판정하지 않는다(줄 단위 정리는 S2 `detail_drop_lines`의 일).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

_PATH = Path(__file__).with_name("detail_ui_junk.json")
_SPLIT = re.compile(r"\s*(?:\n|/|\||｜)\s*")

REASON = "UI 글자라 버림"


@lru_cache(maxsize=1)
def table() -> Dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def _units(text: str) -> List[str]:
    return [u.strip() for u in _SPLIT.split(str(text or "").replace("\r", "")) if u.strip()]


def is_ui_unit(unit: str) -> bool:
    """조각 하나가 평점(a) 또는 가게 UI 토큰(b)인가."""
    t = table()
    s = str(unit or "").strip()
    if not s:
        return False
    if re.match(t.get("rating_re") or r"^$", s):
        return True
    low = s.lower()
    return any(tok.lower() in low for toks in (t.get("tokens") or {}).values() for tok in toks)


def judge(text: str) -> Dict:
    """`{junk, units, ui, name}` — `junk`=본문 전체를 비어 있음으로 볼지(c). `ui`=걸린 조각, `name`=허용한 이름 조각."""
    t = table()
    units = _units(text)
    out = {"junk": False, "units": units, "ui": [], "name": ""}
    if not units or len(units) > int(t.get("max_lines") or 5):
        return out
    ui = [u for u in units if is_ui_unit(u)]
    rest = [u for u in units if u not in ui]
    out["ui"] = ui
    if not rest:
        out["junk"] = True
    elif len(rest) == 1 and len(ui) >= 2 and len(rest[0]) <= int(t.get("name_line_max_chars") or 12) \
            and not re.search(r"\d", rest[0]):
        out["junk"], out["name"] = True, rest[0]
    return out


def is_junk(text: str) -> bool:
    return judge(text)["junk"]


def drop_shop_ui_lines(text: str) -> Dict:
    """Y13-B(BLACKHOLES 2호 런북 대조) — 섹션(「■ …」 머리로 나뉜 덩어리) 안의 가게 UI **줄**만 뺀다 → `{text, removed}`.

    실측: 상세 초안 「■ 원문 상세」 = 「沉默流浪汉 / 平均2天内发货」(가게 이름 + 발송 UI). 본문 전체 판정(`is_junk`)은 초안의
    다른 섹션 때문에 안 걸리고, 이름 조각 허용은 UI 조각 2개부터라 한 줄짜리 UI 옆 가게 이름이 살아 번역돼 나갔다
    (「침묵의 방랑자 / 평균 2일 이내 발송」 — 해외 배송인데 2일 발송 약속).
    규칙: 섹션 안 UI 조각 줄(`is_ui_unit`)은 뺀다 · 뺀 뒤 그 섹션에 남은 줄이 **이름 모양 한 줄**(≤12자·숫자 없음)뿐이면 그것도.
    우리가 쓴 줄(「·」 글머리 · 「■」 머리)은 건드리지 않는다 — 안내 문구 「…발송됩니다」를 UI로 읽지 않게."""
    t = table()
    cap = int(t.get("name_line_max_chars") or 12)
    lines = str(text or "").replace("\r", "").split("\n")
    sections: List[List[int]] = [[]]
    for i, ln in enumerate(lines):
        if ln.strip().startswith("■"):
            sections.append([])
        sections[-1].append(i)
    drop = set()
    for sec in sections:
        body = [i for i in sec if lines[i].strip() and not lines[i].strip().startswith(("■", "·"))]
        ui = [i for i in body if len(lines[i].strip()) <= 40 and is_ui_unit(lines[i])]
        if not ui:
            continue
        drop.update(ui)
        rest = [i for i in body if i not in ui]
        if len(rest) == 1 and len(lines[rest[0]].strip()) <= cap and not re.search(r"\d", lines[rest[0]]) \
                and not [i for i in sec if lines[i].strip().startswith("·")]:
            drop.add(rest[0])
    if not drop:
        return {"text": str(text or ""), "removed": 0}
    return {"text": "\n".join(ln for i, ln in enumerate(lines) if i not in drop), "removed": len(drop)}


def desc_is_junk(pd: Dict) -> bool:
    """상품 데이터의 상세설명(편집본·번역본) 중 실려 나갈 값이 UI 쓰레기인가 — 둘 중 비지 않은 것 전부가 쓰레기여야 참."""
    vals = [str(pd.get(k) or "").strip() for k in ("description", "description_ko")]
    if not any(vals) and str(pd.get("_desc_src") or "").strip():      # Y11-P: 나갈 글자 정리 뒤엔 정리 전 값으로 판정
        vals = [str(pd["_desc_src"]).strip()]
    vals = [v for v in vals if v]
    return bool(vals) and all(is_junk(v) for v in vals)


def note(pd: Dict) -> str:
    """카드 사유 한 줄 — 상세설명이 화면 읽기 UI 글자라 버렸으면."""
    pd = pd or {}
    if not (pd.get("desc_ui_dropped") or desc_is_junk(pd)):
        return ""
    return f"상세설명: 화면 읽기 → {REASON}(가게 이름·평점·발송·만족도) — 상세 자동 초안으로 채웁니다"


# ── Y11-P(오너 2026-10-15) — 페이지 탭 라벨 · 남의 글 블록(구매평·문답) ─────────────────────────────────
_COUNT_TAIL = r"\s*(?:[·・:：]?\s*[\d,.万+]+|[(（]\s*[\d,.万+]+\s*[)）])?\s*$"


@lru_cache(maxsize=1)
def _label_re():
    labs = sorted((str(x) for x in (table().get("tab_labels") or []) if str(x).strip()), key=len, reverse=True)
    if not labs:
        return None
    return re.compile(r"^\s*(?:" + "|".join(re.escape(x) for x in labs) + ")" + _COUNT_TAIL)


def is_tab_label(line: str) -> bool:
    """줄 전체가 페이지 탭 라벨(「用户评价」「用户评价·35」「累计评论(1200)」)인가."""
    rx = _label_re()
    return bool(rx and rx.match(str(line or "").strip()))


def strip_page_ui(text: str) -> Dict:
    """`{text, labels, blocks, removed}` — 탭 라벨 줄과 남의 글 블록(구매평·문답)을 뺀 본문.

    블록은 `blocks[].start` 줄에서 `end` 줄까지(끝 줄 포함). `max_block_lines` 안에 끝이 없으면 start 줄만 뺀다.
    본문 줄 순서는 그대로 — 줄 하나도 고쳐 쓰지 않는다(빼기만).
    """
    t = table()
    lines = str(text or "").replace("\r", "").split("\n")
    rules = [(re.compile(b["start"]), re.compile(b["end"])) for b in (t.get("blocks") or [])
             if isinstance(b, dict) and b.get("start") and b.get("end")]
    cap = int(t.get("max_block_lines") or 80)
    out: List[str] = []
    labels = blocks = removed = 0
    domestic: List[str] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        hit = next(((st, en) for st, en in rules if s and st.match(s)), None)
        if hit:
            end = next((j for j in range(i + 1, min(len(lines), i + 1 + cap)) if hit[1].match(lines[j].strip())), None)
            if end is not None:
                removed += end - i + 1
                blocks += 1
                i = end + 1
                continue
        if s and is_tab_label(s):
            labels += 1
            removed += 1
            i += 1
            continue
        out.append(lines[i])
        i += 1
    out, pairs, dropped = spec_pairs(out)
    removed += dropped
    domestic = [k for k, _v in pairs.get("dropped") or []]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return {"text": body, "labels": labels, "blocks": blocks, "removed": removed, "domestic": domestic,
            "spec_pairs": len(pairs.get("kept") or [])}


def is_spec_label(line: str) -> bool:
    """규격 **키** 줄인가 — 짧고(≤10자) `spec_keys`와 같거나 `spec_label_re`로 끝난다(값 「金属」「83cm」「复古怀旧」은 아니다)."""
    s = str(line or "").strip()
    if not s or len(s) > 10 or re.search(r"[\s:：,，]", s):
        return False
    t = table()
    if s in (t.get("spec_keys") or []) or s in (t.get("drop_keys") or []) or s in (t.get("domestic_keys") or []):
        return True
    pat = t.get("spec_label_re") or ""
    return bool(pat and re.search(pat, s))


def _drop_key(key: str) -> bool:
    t = table()
    return key in (t.get("drop_keys") or []) or any(k in key for k in (t.get("domestic_keys") or []))


def spec_pairs(lines: List[str]):
    """Y11-W 추가 — 「参数信息」 키·값 짝 맞추기 → `(줄들, {kept, dropped}, 뺀 줄 수)`.

    키 줄을 만나면: 바로 앞에 짝 없는 짧은 값 줄이 있으면 그것과(값 먼저 「金属/框架材质」), 아니면 바로 뒤 줄과(키 먼저 「总长/83cm」).
    짝은 「키: 값」 한 줄로. drop_keys·domestic_keys 키의 짝은 통째로 뺀다. 도시 목록 줄만 따로 있어도 뺀다.
    키가 하나도 없으면 줄을 그대로 돌려준다(일반 상세 글은 건드리지 않는다)."""
    keys = [i for i, ln in enumerate(lines) if is_spec_label(ln)]
    if len(keys) < 2:
        return [ln for ln in lines if not is_city_list(ln)], {"kept": [], "dropped": []}, sum(1 for ln in lines if is_city_list(ln))
    out: List[str] = []
    kept, dropped = [], []
    pending = None                                           # out 안의 위치 — 짝 없는 짧은 값 줄
    n_drop = 0
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            out.append(ln)
            pending = None
            i += 1
            continue
        if is_spec_label(s):
            val = None
            if pending is not None:
                val = out.pop(pending)
                pending = None
                i += 1
            elif i + 1 < len(lines) and lines[i + 1].strip() and not is_spec_label(lines[i + 1]):
                val = lines[i + 1].strip()
                i += 2
            else:
                i += 1
            v = (val or "").strip()
            if _drop_key(s) or is_city_list(v):
                dropped.append((s, v[:20]))
                n_drop += 2 if v else 1
                continue
            kept.append((s, v))
            out.append(f"{s}: {v}" if v else s)
            n_drop += 1 if v else 0                          # 두 줄 → 한 줄
            continue
        if is_city_list(s):
            dropped.append(("", s[:20]))
            n_drop += 1
            i += 1
            continue
        out.append(ln)
        # 짧은 값 줄만 다음 키의 「앞 값」 후보(긴 설명 문장은 짝이 아니다)
        pending = (len(out) - 1) if (len(s) <= 24 and i + 1 < len(lines) and is_spec_label(lines[i + 1])) else None
        i += 1
    return out, {"kept": kept, "dropped": dropped}, n_drop

_CITY = re.compile(r"[\u4e00-\u9fff]{1,4}市|全国|北京|上海|天津|重庆")


def is_domestic_key(line: str) -> bool:
    """Y11-W — 줄이 중국 내수 속성 키(`domestic_keys`)를 담나(부분 일치). 규격 키(`spec_keys`)가 같이 있으면 아니다."""
    s = str(line or "").strip()
    if not s or len(s) > 24:
        return False
    t = table()
    if any(k in s for k in (t.get("spec_keys") or [])):
        return False
    return any(k in s for k in (t.get("domestic_keys") or []))


def is_domestic_value(line: str) -> bool:
    s = str(line or "").strip()
    pat = table().get("domestic_values") or ""
    return bool(s) and (bool(pat and re.match(pat, s)) or is_city_list(s))


def is_city_list(line: str) -> bool:
    """도시 목록 줄(「佛山市 郑州市 … 全国」) — 도시 토막이 `city_list_min`개 이상이고 그 밖의 글자가 거의 없다."""
    toks = [x for x in re.split(r"[\s,，、/]+", str(line or "").strip()) if x]
    if len(toks) < int(table().get("city_list_min") or 3):
        return False
    hits = sum(1 for x in toks if _CITY.fullmatch(x) or x in ("其他", "全国"))
    return hits >= max(3, int(len(toks) * 0.8))
