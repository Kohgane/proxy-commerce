"""src/services/image_bench_axes.py — 텐센트가 어디까지인지 **숫자로** 남긴다 (F33).

## 축 다섯 — 오너 PC 서랍 실측(2026-09-18) 대조표에서 뽑았다

| 축 | 뜻 | 0점 |
|---|---|---|
| **A 브랜드 보존** | 로고·워드마크(SPORTLINK) | 번역·변형되면 0 |
| **B 관용 표현** | `三合一` → `3-in-1` | 직역(`삼합일`)이면 0 |
| **C 박스 맞춤** | 번역문이 원 배경 도형 밖으로 | 넘치면 0 |
| **D 영문 UI 보존** | 제품 화면 속 영문(`Monday 1`·`Alarm 6:45AM`) | 건드리면 0 |
| **E 타이포 일치** | 폰트 굵기·정렬 | 원본과 다르면 0 |

## 무엇을 자동으로 재고, 무엇을 못 재나

**A·B·D는 `TransDetails`의 `SourceLineText`/`TargetLineText`로 잰다** — 글자 대 글자다.

**C·E는 자동으로 못 잰다.** 그리고 그 이유가 중요하다:

  SDK 모델을 읽어 보니 `TransDetail`엔 `BoundingBox(X·Y·Width·Height)`·`LineHeight`·
  `LinesCount`가 **실제로 있다**(추측이 아니라 `tencentcloud.tmt.v20180321.models` 원문).
  반례가 말한 조건은 충족된다 — 그런데도 C를 자동화하지 않는다.

  그 박스는 주석이 **「段落文本框位置」 = 원문 문단의 자리**다. **번역문이 그려진 자리가
  아니다.** 그래서 「번역문이 배경 도형 밖으로 넘쳤나」를 그걸로 판정하면,
  재지 않은 것을 잰 척하는 것이 된다 — 그건 측정이 아니라 추정이다.

  대신 **참고 수치**로 올린다(원문 박스 폭·줄높이·글자수 비). 점수가 아니라 **사람이 빨리
  찍게 돕는 재료**다. 화면이 그렇게 이름 붙인다.

> ★ **있는 필드로 잴 수 있는 것과, 그 필드가 뜻하는 것은 다르다.**

## 발명 금지

- 브랜드 사전은 **상품명에서 뽑는다**(영문 대문자 토큰). 손으로 적지 않는다.
- 관용구 표는 **실측된 것만**. 표에 없는 줄은 `0`도 `1`도 아니고 **「측정 불가」 + 그 줄 원문**이다.
  다음 사람이 그 원문을 보고 표를 늘린다.
"""
from __future__ import annotations

import re

# 사람이 찍는 축과 자동으로 재는 축 — 화면·저장·계약이 **같은 목록**을 쓴다.
AXES = (
    ("A", "브랜드 보존", "auto", "로고·워드마크가 번역/변형되면 0"),
    ("B", "관용 표현", "auto", "三合一→3-in-1 류. 직역이면 0"),
    ("C", "박스 맞춤", "human", "번역문이 원 배경 도형 밖으로 넘치면 0"),
    ("D", "영문 UI 보존", "auto", "제품 화면 속 영문을 건드리면 0"),
    ("E", "타이포 일치", "human", "폰트 굵기·정렬이 원본과 다르면 0"),
    # D3-5 ② — 오너 브리프 2026-09-25. 판정기는 `image_text_render.background_score`.
    ("F", "배경 복원", "auto", "지운 자리와 주변 16px 링의 색·결 차이가 임계 이하면 1"),
)
AUTO_AXES = tuple(k for k, _l, kind, _h in AXES if kind == "auto")
HUMAN_AXES = tuple(k for k, _l, kind, _h in AXES if kind == "human")

#: F축은 **지운 결과**(글자를 얹기 전)에서 잰다. 텐센트는 그 중간본을 주지 않는다.
F_UNMEASURABLE_TENCENT = "텐센트는 지운 중간본을 주지 않습니다 — F는 D3끼리만 잽니다"


# ─────────────────────────────────────────────────────────────────────────────
# D3-5 ③ 장별 자동 선택 — 「전부 D3」가 아니라 **장마다 최선**
# ─────────────────────────────────────────────────────────────────────────────
#
# 후보: 텐센트 렌더 · D3(telea) · D3(gen_remove). 자동축(A·B·D·F) 합이 가장 높은 것을 제안한다.
#
# ## ★ 합은 **모든 후보가 잰 축만** 더한다
#
# 텐센트는 F를 잴 수 없다(위). 잰 축만 더하면 D3는 4축, 텐센트는 3축 — **D3가 공짜로 1점**을
# 먹는다. 그건 비교가 아니라 편들기다. 그래서 **공통으로 잰 축**만 합한다.
#
# ## 동점일 때
#
# 1. **F**: 통과 > 못 잼 > 실패 — 복원을 잰 쪽이 좋으면 이기고, 나쁘면 진다.
#    (「못 잼」을 0점이나 1점으로 바꾸지 않는다 — 순서로만 쓴다.)
# 2. **돈**: 텐센트(이미 냈다) → D3·telea(공짜) → D3·gen_remove(크레딧) 순으로 앞선다.
#
# 사람이 뒤집을 수 있다 — 제안은 제안이다(`pick:<장>` 칸).
CANDIDATES = (
    ("tencent", "텐센트 렌더"),
    ("d3", "D3·telea"),
    ("d3g", "D3·gen_remove"),
)
_COST_RANK = {"tencent": 0, "d3": 1, "d3g": 2}
_F_RANK = {1: 2, None: 1, 0: 0}


def pick_best(cands: dict) -> dict:
    """`{name: axes_dict}` → `{pick, scores, common, reason}`.

    `cands`에는 **이미지를 실제로 낸** 후보만 넣는다(실패한 렌더는 후보가 아니다).
    """
    names = [n for n, _l in CANDIDATES if n in (cands or {})]
    if not names:
        return {"pick": "", "scores": {}, "common": [], "reason": "고를 후보가 없습니다"}
    common = [k for k in AUTO_AXES
              if all(((cands[n] or {}).get(k) or {}).get("score") in (0, 1) for n in names)]
    scores = {n: sum(int(cands[n][k]["score"]) for k in common) for n in names}

    def _f(n):
        v = ((cands[n] or {}).get("F") or {}).get("score")
        return v if v in (0, 1) else None

    ranked = sorted(names, key=lambda n: (-scores[n], -_F_RANK[_f(n)], _COST_RANK[n]))
    best = ranked[0]
    label = dict(CANDIDATES)[best]
    if len(names) == 1:
        reason = f"후보가 하나뿐입니다 — {label}"
    else:
        top = [n for n in names if scores[n] == scores[best]]
        if common:
            reason = f"공통 자동축({'·'.join(common)}) 합 {scores[best]}"
            if len(top) > 1:
                reason += " 동점"
        else:
            # ★ 흔한 경우다 — 브랜드·관용구·영문 UI가 없는 장은 A·B·D가 전부 측정 불가다.
            #   그땐 **F와 돈만으로** 고른 것이고, 화면이 그렇게 말해야 한다(합 0을 점수처럼 보이지 않게).
            reason = "모든 후보가 함께 잰 자동축이 없습니다"
        if len(top) > 1:
            fs = [_f(n) for n in top]
            reason += " → F로 갈랐습니다" if len(set(fs)) > 1 else " → 돈이 덜 드는 쪽"
        reason += f" — {label}"
    return {"pick": best, "scores": scores, "common": common, "reason": reason}

# 상품명에서 브랜드로 볼 토큰 — **영문 대문자** 2자 이상.
_BRAND_TOKEN = re.compile(r"\b[A-Z][A-Z0-9]{1,}\b")
# 흔한 대문자 약어는 브랜드가 아니다(단위·규격). 실측으로 늘린다.
_NOT_BRAND = {"XL", "XXL", "USB", "LED", "PVC", "ABS", "TPU", "EVA", "CM", "MM",
              "ML", "KG", "AM", "PM", "DIY", "PU", "3D", "2D", "OK", "NEW"}

# 원문 줄이 **영문+숫자+기호만**이면 제품 화면 속 UI다 — 건드리면 안 된다.
_EN_UI = re.compile(r"^[\x20-\x7E]+$")

#: 관용구 — **실측된 것만** 적는다. 표에 없으면 판정하지 않는다(「측정 불가」).
#:   오너 실측(2026-09-18): `三合一`이 `삼합일`로 직역돼 나왔다.
#:
#: `ko`가 있으면 그건 **오너가 확정한 정본 한국어**다(D3-4 ④, 실측 오역 반영 2026-09-21).
#: 2단계가 그 줄을 만나면 번역기를 부르지 않고 이 문장을 쓴다 —
#: **생성과 판정이 같은 표를 본다**(이 파일 머리말 ★★).
#:
#: ⚠️ `bad`를 비워 둔 것은 **발명을 피한 것**이다. 오너는 「오역이었다」고 알려 줬지
#: 틀린 문장을 그대로 주지 않았다. 없는 문장을 지어 `bad`에 넣으면, 그 문장이 안 나오는
#: 다른 오역을 **정답으로 통과**시킨다. 그래서 정본만 적고, 그 밖의 형태는 **「측정 불가」**다.
IDIOMS = (
    {"source": "三合一",
     "good": ("3-in-1", "3 in 1", "3in1", "3IN1", "삼 in 1"),
     "bad": ("삼합일",),
     "note": "수사+합일 = 기능 개수 표현"},
    {"source": "一放秒充",
     "good": ("올려놓기만 하면 충전",),
     "bad": (),
     "ko": "올려놓기만 하면 충전",
     "note": "무선 충전 카피 — 오너 실측 오역(2026-09-21), 정본 지정"},
    {"source": "拒绝凌乱",
     "good": ("지저분함은 이제 그만",),
     "bad": (),
     "ko": "지저분함은 이제 그만",
     "note": "정리 카피 — 오너 실측 오역(2026-09-21), 정본 지정"},
    {"source": "轻松收纳",
     "good": ("간편 수납",),
     "bad": (),
     "ko": "간편 수납",
     "note": "정리 카피 — 오너 실측 오역(2026-09-21), 정본 지정"},
    # F48-b — 쿠팡 **색상 속성값**도 이 표를 쓴다(오너: 「색상 매핑은 D3 용어집 재사용」).
    #   오너가 준 예시 하나만 넣는다. 다른 한자 색상은 **표에 없으면 보류** — 늘릴 때는 한 줄씩.
    #   `블랙`은 옛 정본(5,691건 등록)이 실제로 보낸 값이라 쿠팡이 받는 값이다.
    {"source": "黑色",
     "good": ("블랙",),
     "bad": (),
     "ko": "블랙",
     "note": "쿠팡 색상 속성 — 오너 지정(F48-b, 2026-09-25)"},
)


def brand_tokens(title: str) -> list:
    """상품명에서 **브랜드 후보**를 뽑는다. 손으로 적지 않는다 — 없으면 빈 목록."""
    seen, out = set(), []
    for tok in _BRAND_TOKEN.findall(str(title or "")):
        if tok in _NOT_BRAND or tok in seen or tok.isdigit():
            continue
        seen.add(tok)
        out.append(tok)
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).upper()


def judge_brand(lines, tokens) -> dict:
    """A — 원문 줄에 브랜드가 있으면 번역문에도 **그대로** 있어야 한다.

    `{score, reason, hits}` — 브랜드가 한 줄도 안 나오면 `score=None`(해당 없음).
    """
    toks = [t for t in (tokens or []) if t]
    if not toks:
        return {"score": None, "reason": "상품명에서 브랜드 토큰을 못 뽑았습니다", "hits": []}
    hits, lost = [], []
    for ln in (lines or []):
        src, tgt = str(ln.get("source") or ""), str(ln.get("target") or "")
        for t in toks:
            if t in src.upper():
                kept = t in tgt.upper()
                hits.append({"token": t, "source": src, "target": tgt, "kept": kept})
                if not kept:
                    lost.append(t)
    if not hits:
        return {"score": None, "reason": "이 장에 브랜드가 나오지 않습니다", "hits": []}
    if lost:
        return {"score": 0, "reason": "브랜드가 번역/삭제됨: " + ", ".join(sorted(set(lost))),
                "hits": hits}
    return {"score": 1, "reason": "브랜드 원형 유지", "hits": hits}


def judge_idiom(lines) -> dict:
    """B — 표에 있는 관용구만 판정한다. 표에 없으면 **측정 불가**(0이 아니다)."""
    found = []
    for ln in (lines or []):
        src, tgt = str(ln.get("source") or ""), str(ln.get("target") or "")
        for idi in IDIOMS:
            if idi["source"] in src:
                n = _norm(tgt)
                if any(_norm(g) in n for g in idi["good"]):
                    found.append({"idiom": idi["source"], "score": 1,
                                  "source": src, "target": tgt})
                elif any(_norm(b) in n for b in idi["bad"]):
                    found.append({"idiom": idi["source"], "score": 0,
                                  "source": src, "target": tgt})
                else:
                    # **모르는 형태** — 0으로 찍으면 없는 실패를 만든다. 원문을 올려 표를 늘리게.
                    found.append({"idiom": idi["source"], "score": None,
                                  "source": src, "target": tgt})
    if not found:
        return {"score": None, "reason": "표에 있는 관용구가 이 장에 없습니다", "hits": []}
    if any(f["score"] == 0 for f in found):
        return {"score": 0, "reason": "직역됨", "hits": found}
    if any(f["score"] is None for f in found):
        return {"score": None,
                "reason": "표에 없는 번역 형태 — 원문을 보고 표를 늘려 주세요", "hits": found}
    return {"score": 1, "reason": "관용 표현으로 옮김", "hits": found}


def judge_en_ui(lines) -> dict:
    """D — 원문 줄이 **영문+숫자만**이면 제품 화면 속 UI다. 손대면 0."""
    hits, touched = [], []
    for ln in (lines or []):
        src, tgt = str(ln.get("source") or "").strip(), str(ln.get("target") or "").strip()
        if not src or not _EN_UI.match(src):
            continue
        same = _norm(src) == _norm(tgt)
        hits.append({"source": src, "target": tgt, "kept": same})
        if not same:
            touched.append(src)
    if not hits:
        return {"score": None, "reason": "이 장에 영문 UI 줄이 없습니다", "hits": []}
    if touched:
        return {"score": 0, "reason": "영문 UI를 건드림: " + " · ".join(touched[:3]),
                "hits": hits}
    return {"score": 1, "reason": "영문 UI 원형 유지", "hits": hits}


def box_hints(lines) -> list:
    """C를 사람이 빨리 찍게 돕는 **참고 수치**(점수 아님).

    박스는 **원문 문단**의 자리다(`段落文本框位置`) — 번역문이 그려진 자리가 아니다.
    그래서 「넘쳤다」를 여기서 판정하지 않는다. 길이비가 크면 **볼 만한 장**이라는 힌트일 뿐.
    """
    out = []
    for ln in (lines or []):
        box = ln.get("box") or {}
        src, tgt = str(ln.get("source") or ""), str(ln.get("target") or "")
        ratio = (len(tgt) / len(src)) if src else None
        out.append({
            "source": src, "target": tgt,
            "box_w": box.get("w"), "box_h": box.get("h"),
            "line_height": ln.get("line_height"),
            "len_ratio": round(ratio, 2) if ratio is not None else None,
        })
    return out


def auto_scores(lines, tokens) -> dict:
    """한 장의 자동 축 셋. `{A: {...}, B: {...}, D: {...}}`."""
    return {"A": judge_brand(lines, tokens),
            "B": judge_idiom(lines),
            "D": judge_en_ui(lines)}


def cell_state(score) -> str:
    """표 한 칸의 상태 — `1` / `0` / `측정 불가`. **빈칸을 만들지 않는다.**"""
    if score == 1:
        return "1"
    if score == 0:
        return "0"
    return "측정 불가"


def summarize(pages) -> dict:
    """모드 합계 — 축마다 `{scored, ones, unmeasured}`.

    **분모는 잰 것만**이다. 「측정 불가」를 0으로 세면 공급사를 없는 실패로 깎는다.
    """
    out = {}
    for key, _label, _kind, _hint in AXES:
        ones = scored = unmeasured = 0
        for p in (pages or []):
            s = (p.get("axes") or {}).get(key)
            v = s.get("score") if isinstance(s, dict) else s
            if v == 1:
                ones += 1
                scored += 1
            elif v == 0:
                scored += 1
            else:
                unmeasured += 1
        out[key] = {"ones": ones, "scored": scored, "unmeasured": unmeasured}
    return out
