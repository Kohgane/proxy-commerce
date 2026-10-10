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


def desc_is_junk(pd: Dict) -> bool:
    """상품 데이터의 상세설명(편집본·번역본) 중 실려 나갈 값이 UI 쓰레기인가 — 둘 중 비지 않은 것 전부가 쓰레기여야 참."""
    vals = [str(pd.get(k) or "").strip() for k in ("description", "description_ko")]
    vals = [v for v in vals if v]
    return bool(vals) and all(is_junk(v) for v in vals)


def note(pd: Dict) -> str:
    """카드 사유 한 줄 — 상세설명이 화면 읽기 UI 글자라 버렸으면."""
    pd = pd or {}
    if not (pd.get("desc_ui_dropped") or desc_is_junk(pd)):
        return ""
    return f"상세설명: 화면 읽기 → {REASON}(가게 이름·평점·발송·만족도) — 상세 자동 초안으로 채웁니다"
