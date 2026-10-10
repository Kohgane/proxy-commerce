"""Y7-M(오너 2026-10-10) — 세트 상품명 vs 조각별 옵션 불일치 가드. **마켓 공통** — 등록 페이로드 조립 한 자리에서 쓴다.

실측 21:11 KST 고코스모스 채널 13803531537(플리츠 세트): 옵션 값 「블랙 상의 / 블랙 스커트 / 블루 상의 …」 8개
= 색상 4 × 조각 2 → 조각마다 따로 팔리는데, 상품명·본문은 「투피스 세트」, 노출 가격은 가장 싼 조각 값이었다.

- `judge(options)` — 옵션 값에 **서로 다른 조각**(`piece_tokens.json`의 label)이 2종 이상이면 piecewise.
  색상만 다르고 조각이 1종(또는 0)이면 아니다.
- `notice_line(pieces)` — 본문 「옵션·상세」 맨 앞에 박을 한 줄(검출된 조각 이름 그대로).
- `apply(payload)` — 나갈 본문(`description_html` 또는 `description`)에 그 줄을 넣는다(이미 있으면 다시 넣지 않음).
  네이버 「본문 다시 보내기」도 같은 조립(`_payload_for_market`)을 지나므로 기존 등록 상품에 그대로 반영된다.
- `caution(pd)` — 사전검증 카드의 「주의」 칩 한 줄. 상품명에 세트 낱말(`set_words`)이 있을 때만. **보류 아님**.

상품명은 고치지 않는다 — 「세트」를 빼면 검색어를 잃는다(오너 판단).
"""
from __future__ import annotations

import html as _html
import json
import os
import re
from functools import lru_cache
from typing import Any, Dict, List

_TOKENS_PATH = os.path.join(os.path.dirname(__file__), "piece_tokens.json")
_HANGUL = "가-힣"
_OPT_HEAD = "■ 옵션·상세"


@lru_cache(maxsize=1)
def _table() -> Dict[str, Any]:
    with open(_TOKENS_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    pieces = []
    for p in data.get("pieces") or []:
        label = str(p.get("label") or "").strip()
        toks = [str(t).strip() for t in (p.get("tokens") or []) if str(t).strip()]
        if label and toks:
            pieces.append((label, [_pattern(t) for t in toks]))
    return {"pieces": pieces, "set_words": [str(w) for w in data.get("set_words") or [] if str(w).strip()]}


def _pattern(tok: str):
    if re.search(f"[{_HANGUL}]", tok):
        # 한글: 낱말 한가운데(앞뒤 모두 한글)만 아니면 — 「블랙 상의」·「블랙상의」는 잡고, 「…X상의Y…」 같은 중간 조각은 뺀다
        return re.compile(f"(?<![{_HANGUL}]){re.escape(tok)}|{re.escape(tok)}(?![{_HANGUL}])", re.I)
    return re.compile(rf"(?<![A-Za-z]){re.escape(tok)}(?![A-Za-z])", re.I)


def _values(options) -> List[str]:
    """옵션 값(한국어 우선 — 마켓에 나가는 글자). 한국어 값이 없는 축은 원문 값."""
    out: List[str] = []
    for o in options or []:
        if not isinstance(o, dict):
            continue
        vals = o.get("values_ko") or o.get("values") or []
        for v in vals:
            s = str((v.get("ko") or v.get("src")) if isinstance(v, dict) else v or "").strip()
            if s:
                out.append(s)
    return out


def judge(options) -> Dict[str, Any]:
    """`{piecewise, pieces}` — pieces는 검출된 조각 label(옵션 값에 처음 나온 순서)."""
    found: List[str] = []
    for v in _values(options):
        for label, pats in _table()["pieces"]:
            if label not in found and any(p.search(v) for p in pats):
                found.append(label)
    return {"piecewise": len(found) >= 2, "pieces": found}


def _final(word: str) -> bool:
    ch = str(word or "")[-1:]
    return bool(ch) and "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0


_COUNT = {2: "두", 3: "세", 4: "네", 5: "다섯"}


def notice_line(pieces: List[str]) -> str:
    """「상의와 스커트는 각각 따로 판매돼요. 세트로 받으시려면 두 가지를 각각 담아 주세요.」 — 조각 이름은 검출된 그대로."""
    ps = [p for p in pieces or [] if p]
    if len(ps) < 2:
        return ""
    if len(ps) == 2:
        a, b = ps
        names = f"{a}{'과' if _final(a) else '와'} {b}"
    else:
        names = ", ".join(ps)
    last = ps[-1]
    n = _COUNT.get(len(ps), str(len(ps)))
    return (f"{names}{'은' if _final(last) else '는'} 각각 따로 판매돼요. "
            f"세트로 받으시려면 {n} 가지를 각각 담아 주세요.")


def set_word(title: str) -> str:
    """상품명에 든 세트 낱말(첫 번째) — 없으면 ''."""
    t = str(title or "")
    for w in _table()["set_words"]:
        if w.lower() in t.lower():
            return w
    return ""


def caution(pd: Dict[str, Any]) -> str:
    """사전검증 「주의」 칩 한 줄 — 조각별 판매 + 상품명이 세트라고 말할 때만. 등록은 막지 않는다."""
    pd = pd or {}
    j = judge(pd.get("options"))
    if not j["piecewise"]:
        return ""
    word = ""
    for k in ("coupang_name", "title_ko", "title"):
        word = set_word(pd.get(k) or "")
        if word:
            break
    if not word:
        return ""
    return (f"옵션이 {'/'.join(j['pieces'])} 개별 판매 — 상품명에 '{word}' 포함. 가격은 조각 하나 기준")


def _inject_text(text: str, line: str) -> str:
    """평문 — 「■ 옵션·상세」 제목 바로 아래, 제목이 없으면 맨 앞 문단."""
    lines = str(text or "").split("\n")
    for i, ln in enumerate(lines):
        if ln.strip() == _OPT_HEAD:
            return "\n".join(lines[: i + 1] + [line] + lines[i + 1:])
    return line + ("\n\n" + text if str(text or "").strip() else "")


_P = '<p style="margin:0 0 12px;white-space:pre-wrap">'


def _inject_html(body: str, line: str) -> str:
    """HTML — 「■ 옵션·상세」 제목 줄 바로 뒤(네이버 조립은 문단 안에 줄바꿈), 없으면 글 묶음 맨 앞, 그것도 없으면 본문 맨 앞."""
    esc = _html.escape(line, quote=False)
    m = re.search(re.escape(_OPT_HEAD) + r"(\s*(?:<br\s*/?>|\n))", body)
    if m:
        return body[: m.end()] + esc + m.group(1) + body[m.end():]
    if '<div style="margin-top:24px">' in body:                     # naver_detail.build 의 글 묶음
        return body.replace('<div style="margin-top:24px">', '<div style="margin-top:24px">' + _P + esc + "</p>", 1)
    if body.startswith('<div style="max-width:860px;margin:0 auto">'):   # 사진만 있는 네이버 본문 — 사진 위
        head = '<div style="max-width:860px;margin:0 auto">'
        return head + _P + esc + "</p>" + body[len(head):]
    return _P + esc + "</p>" + body


def apply(payload: Dict[str, Any]) -> Dict[str, Any]:
    """조각별 판매면 나갈 본문에 안내 한 줄. 아니면 그대로. 이미 들어 있으면 다시 넣지 않는다."""
    j = judge(payload.get("options"))
    if not j["piecewise"]:
        return payload
    line = notice_line(j["pieces"])
    out = dict(payload)
    html_body = str(out.get("description_html") or "")
    if html_body.strip():
        if line not in _html.unescape(html_body):
            out["description_html"] = _inject_html(html_body, line)
    else:
        txt = str(out.get("description") or "")
        if line not in txt:
            out["description"] = _inject_text(txt, line)
    return out
