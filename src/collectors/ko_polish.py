"""T1 ko_polish — 번역 공통 후처리(오너 2026-09-30-H): 중국식 워딩·판촉 문구 제거 + 옵션 값 해석.

## 실측(코드·운영 데이터)

- 옵션 값 번역(`translate_options`)은 **「한국어 번역」 버튼 경로에서만** 불렸다 — 수집·백그라운드 번역 워커는
  부르지 않았다. 운영 최근 48건: 옵션 39개·값 438개 중 `values_ko`가 붙은 옵션 **0개**.
- 번역기는 원문을 그대로 옮긴다 — `现货`→「재고 있음」, `海外特供`→「해외 특공」, 판촉 이미지의
  `国庆狂欢`→「국경절 축제」가 그대로 남는다(VRSUK 의자, 캡처).

## 무엇을 하나

- `preclean_cn` — 번역 **전** 원문에서 판촉어(`delete_cn`)·가격 문구를 지우고, 소재·부속 용어(`replace`)와
  색상(`colors`)을 한국어로 먼저 박는다(번역기가 「반피」 같은 직역을 못 하게).
- `polish_ko` — 번역 **후** 한국어에서 판촉어(`delete_ko`)·가격 문구를 지우고 기호를 정리한다.
- `option_value` — 복합 값 `색상[소재]부속 접미사`를 조각별로 치환해 「브라운레드 / 오일왁스 반가죽 / 발받침 포함」.
  한자가 남으면 남은 것을 돌려준다(값 단위 — 한 값이 막혀도 다른 값은 간다).
- `shorten` — 쿠팡 옵션 값 28자(정본 `attr_safe`) 초과 시 **소재 조각부터** 줄인다(핵심 가죽 종류는 남김).
- `ban_hits` — 표시광고 위험(할인율·기간·쿠폰 금액·「1위」「최저가」) → 등록 보류 사유.

표는 `ko_polish_rules.json`(기본) + `app_state` `ko_polish:rules`(관리자 덮어쓰기 — 재배포 없이).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Dict, List

_RULES_FILE = Path(__file__).with_name("ko_polish_rules.json")
_STATE_KEY = "ko_polish:rules"
_HAN = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")   # 이스케이프로 — 호환 한자를 글자로 적으면 정규화돼 범위가 한글까지 먹는다
_FW = str.maketrans({"（": "(", "）": ")", "，": ",", "、": ",", "／": "/", "＋": "+", "　": " ", "｜": "|",
                     "：": ":", "【": "[", "】": "]", "〔": "[", "〕": "]", "《": "[", "》": "]", "｛": "{", "｝": "}"})
_TTL = 60.0
_cache: dict = {"at": 0.0, "rules": None}
_lock = threading.Lock()

# 쿠팡 옵션 값 한도 — 쿠팡 문서 「max length: 30 characters」(오너 실측 10-01, 브리프 U3 2026-10-02). 글자 단위.
#   예전 28은 정본 `attr_safe`의 `str(av)[:28]` 안전 여유였다 — 문서 한도로 맞추고, 자르지 않는다(넘으면 미해석).
MAX_OPTION_VALUE = 30
# 쿠팡 옵션 **이름**(attributeTypeName) 한도 — 문서 「max length: 25 characters」(오너 실측 2026-10-01).
#   이름은 카테고리 메타의 속성명이 그대로 가므로 넘는 일이 드물다. 넘으면 **자르지 않고** 보류(「미해석」).
MAX_OPTION_NAME = 25
# 줄일 때 **남길** 소재 낱말(값끼리 구분하는 핵심) — 나머지 소재 조각은 버린다.
_KEY_MATERIAL = ("오일왁스", "풀가죽", "반가죽", "소가죽", "에코 가죽", "천연 가죽", "아닐린 가죽", "세미아닐린 가죽",
                 "스크래치 방지 가죽", "리치 가죽", "실리콘 가죽", "셔닐", "스노우 벨벳", "테크 패브릭", "양털")


def _default_rules() -> dict:
    return json.loads(_RULES_FILE.read_text(encoding="utf-8"))


def rules() -> dict:
    """표 — 관리자 덮어쓰기(app_state)가 있으면 그것, 없으면 기본 JSON. 60초 캐시."""
    now = time.monotonic()
    with _lock:
        if _cache["rules"] is not None and now - _cache["at"] < _TTL:
            return _cache["rules"]
    r = _default_rules()
    try:
        from src.db import image_translate_queue_pg as st
        over = (st.state_get(_STATE_KEY) or {}).get("rules")
        if isinstance(over, dict) and over:
            r = dict(r, **over)
    except Exception:
        pass
    with _lock:
        _cache.update(at=now, rules=r)
    return r


def rules_hash(r: dict | None = None) -> str:
    raw = json.dumps(r or rules(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def save_rules_override(r: dict | None) -> None:
    """관리자 덮어쓰기(빈 값이면 기본으로). 모양이 틀리면 ValueError."""
    if r:
        for k in ("delete_cn", "delete_ko", "price_re", "ban_ko", "ban_cn", "promo_img"):
            if k in r and not all(isinstance(x, str) for x in r[k]):
                raise ValueError(f"{k}는 문자열 목록이어야 합니다")
        for k in ("replace", "colors", "replace_ko"):
            if k in r and not all(isinstance(x, list) and len(x) == 2 for x in r[k]):
                raise ValueError(f"{k}는 [원문, 한국어] 쌍 목록이어야 합니다")
        for row in r.get("title_fix_ko") or []:
            if not (isinstance(row, list) and len(row) == 3 and isinstance(row[0], str)
                    and isinstance(row[1], list) and isinstance(row[2], str)):
                raise ValueError("title_fix_ko는 [원문, [오역 표기들], 바른 말] 목록이어야 합니다")
        for k in ("price_re", "ban_ko", "ban_cn", "promo_img", "detail_drop_lines", "strip_symbols", "delete_re"):
            for p in r.get(k) or []:
                try:
                    re.compile(p)
                except re.error as exc:
                    raise ValueError(f"{k}의 정규식 {p!r}이 틀렸습니다({exc})") from exc
    from src.db import image_translate_queue_pg as st
    st.state_set(_STATE_KEY, {"rules": r or {}})
    with _lock:
        _cache.update(at=0.0, rules=None)


def reset_cache() -> None:
    with _lock:
        _cache.update(at=0.0, rules=None)


def has_han(text) -> bool:
    return bool(_HAN.search(str(text or "")))


def _drop_unmatched(s: str) -> str:
    """지운 자리에 남은 **짝 없는 괄호**(「티몰 인기 상품】너무 예쁜…」 → 「】너무…」)를 뗀다."""
    out, depth = [], {"]": 0, ")": 0, "}": 0}
    pair = {"[": "]", "(": ")", "{": "}"}
    for ch in s:
        if ch in pair:
            depth[pair[ch]] += 1
        elif ch in depth:
            if depth[ch] == 0:
                out.append(" ")
                continue
            depth[ch] -= 1
        out.append(ch)
    return "".join(out)


def _tidy(s: str) -> str:
    s = _drop_unmatched(s)
    s = re.sub(r"\[\s*\]|\(\s*\)|\{\s*\}", " ", s)
    s = re.sub(r"\s+([,)\]}])", r"\1", s)                      # 지운 자리 뒤 「 ,」
    s = re.sub(r"([(\[{])\s+", r"\1", s)
    s = re.sub(r",\s*,+", ",", s)
    s = re.sub(r"\s*([,|/+·])\s*(?=[,|/+·]|$)", " ", s)          # 지운 자리에 남은 연속 구분자
    s = re.sub(r"^[\s,|/+·\-]+|[\s,|/+·\-]+$", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def _strip_common(s: str, r: dict, hits: dict | None) -> str:
    """T1(오너 2026-10-02) — 이모지·장식 기호(✅⚡🌟⭐ꔛ…)와 정규식 삭제표(`delete_re` — 판촉·보증·주장 꼬리)."""
    for p in r.get("strip_symbols") or []:
        # 장식 기호는 원문에서 **조각 경계**로 쓰였다(「✅弹簧线ꔛPD65W快充✅…」) — 공백이 아니라 「·」로 둬 축약이 조각을 안다.
        s, n = re.subn(p, " · ", s)
        if n and hits is not None:
            hits.setdefault("delete", []).append(f"기호×{n}")
    for p in r.get("delete_re") or []:
        s, n = re.subn(p, " ", s)
        if n and hits is not None:
            hits.setdefault("delete", []).append(p)
    return s


def preclean_cn(text: str, *, hits: dict | None = None) -> str:
    """번역 **전** 원문 정리 — 판촉어·가격 삭제, 용어·색상은 한국어로 먼저."""
    r = rules()
    s = _strip_common(str(text or "").translate(_FW), r, hits)
    # T1: 원문 정규식 치환(「44cm高棕色」 → 「높이 44cm 棕色」 — 높이와 색을 가른다). 번역 전 규칙 경로에만.
    for pat, rep_ in r.get("sub_cn") or []:
        s, n = re.subn(pat, rep_, s)
        if n and hits is not None:
            hits.setdefault("replace", []).append(f"{pat}→{rep_}")
    for w in sorted(r.get("delete_cn") or [], key=len, reverse=True):
        if w and w in s:
            s = s.replace(w, " ")
            if hits is not None:
                hits.setdefault("delete", []).append(w)
    for p in r.get("price_re") or []:
        s, n = re.subn(p, " ", s)
        if n and hits is not None:
            hits.setdefault("delete", []).append(f"가격문구×{n}")
    table = list(r.get("replace") or []) + list(r.get("colors") or [])
    for src, ko in sorted(table, key=lambda x: len(x[0]), reverse=True):
        if src and src in s:
            s = s.replace(src, f" {ko} " if ko else " ")
            if hits is not None:
                hits.setdefault("replace", []).append(f"{src}→{ko or '(삭제)'}")
    return _tidy(s)


def strip_cn(text: str, *, hits: dict | None = None) -> str:
    """번역기에 보낼 원문 — **지우기만**(판촉어·가격). 한국어를 끼워 넣지 않는다:
    섞인 글은 언어 판별이 「한국어」로 봐서 번역기가 손대지 않고 돌려준다(실측)."""
    r = rules()
    s = _strip_common(str(text or "").translate(_FW), r, hits)
    for w in sorted(r.get("delete_cn") or [], key=len, reverse=True):
        if w and w in s:
            s = s.replace(w, " ")
            if hits is not None:
                hits.setdefault("delete", []).append(w)
    for p in r.get("price_re") or []:
        s = re.sub(p, " ", s)
    # Y6: 영화·게임·애니 IP명은 번역기에 **보내지 않는다** — 星际穿越가 「스타트렉」으로 옮겨졌다(실측). 등록은 사전검증이 보류.
    s = _drop_ip(s, hits)
    return _tidy(s)


def title_fix(text: str, src: str, *, hits: dict | None = None) -> str:
    """Y6(오너 2026-10-04) — 원문에 그 한자가 **있을 때만** 번역문의 오역 표기를 바른 말로(`title_fix_ko`).

    실측: 【BLACKHOLES】黑洞小夜灯星际穿越电影周边摆件装饰模型手办宇宙 → 「블랙홀 미니 벽등」·「스타트렉」·「주변」.
    원문을 보고 고치니 다른 상품의 「벽등」(진짜 벽등)은 건드리지 않는다. 긴 표기부터."""
    s, src = str(text or ""), str(src or "")
    if not src:
        return s
    for cn, wrongs, right in rules().get("title_fix_ko") or []:
        if not cn or cn not in src or not right:
            continue
        for w in sorted([x for x in wrongs or [] if x and x != right], key=len, reverse=True):
            if w in s and not (right in w):
                s = s.replace(w, right)
                if hits is not None:
                    hits.setdefault("replace", []).append(f"{w}→{right}")
    # 같은 바른 말이 두 번 생기면(「무드등 … 무드등」) 첫 번째만
    for _cn, _w, right in rules().get("title_fix_ko") or []:
        if right and re.search("[가-힣]", right) and s.count(right) > 1:
            first = s.index(right) + len(right)
            s = s[:first] + s[first:].replace(right, " ")
    return s


def polish_ko(text: str, *, hits: dict | None = None, src: str = "") -> str:
    """번역 **후** 한국어 정리 — 판촉어·가격 문구 삭제, 빈 괄호·겹친 구분자 정리.

    `src`(원문 제목)를 주면 Y6 오역 사전(`title_fix_ko`)도 적용하고, 원문에 IP명이 있었으면 그 자리의
    꾸밈말(「영화 굿즈」)도 지운다(번역기에 IP명을 안 보내도 「영화 굿즈」는 남는다)."""
    r = rules()
    s = _strip_common(str(text or "").translate(_FW), r, hits)
    for w in sorted(r.get("delete_ko") or [], key=len, reverse=True):
        if w and w in s:
            s = s.replace(w, " ")
            if hits is not None:
                hits.setdefault("delete", []).append(w)
    for p in r.get("price_re") or []:
        s, n = re.subn(p, " ", s)
        if n and hits is not None:
            hits.setdefault("delete", []).append(f"가격문구×{n}")
    # 번역기 직역 바로잡기(懒人沙发 → 「게으른 사람 소파」 → 빈백 소파) — 긴 것부터
    _targets = set()
    for wrong, ko in sorted(r.get("replace_ko") or [], key=lambda x: len(x[0]), reverse=True):
        if wrong and wrong in s:
            s = s.replace(wrong, ko)
            _targets.add(ko)
            if hits is not None:
                hits.setdefault("replace", []).append(f"{wrong}→{ko}")
    # T2: 바로잡은 말이 한 제목에 두 번 생기면(「빈백 소파 … 빈백 소파 의자」) 첫 번째만 남긴다.
    for ko in _targets:
        # 한글로 바로잡은 말만(영문 브랜드 「SPORTLINK(SPORTLINK)는」의 괄호 표기는 쿠팡명 규칙이 읽는다 — 건드리지 않음)
        if ko and re.search("[가-힣]", ko) and s.count(ko) > 1:
            first = s.index(ko) + len(ko)
            s = s[:first] + s[first:].replace(ko, " ")
    # Q(2026-10-01): 문장형 꼬리 — 번역기가 제목을 문장으로 끝낸다(「…스탠드에 적합합니다」). 상품명은 명사로 끝난다.
    #   끝에서만 뗀다(가운데 「합니다」는 손대지 않음). 다 떼고 남는 게 없으면 원래 값.
    for p in r.get("tail_ko") or []:
        t = re.sub(p, "", s)
        if t != s and t.strip():
            s = t
            if hits is not None:
                hits.setdefault("delete", []).append("문장 꼬리")
    if src:
        s = title_fix(s, src, hits=hits)
    # T3: 상표 — 호환 표기만(맥세이프 호환…) · 레플리카 상표는 지운다(등록은 사전검증이 「상표 위험」으로 보류)
    #   Y6: IP명(mode=ip)도 지우고, 원문이나 이 글에 IP가 있었으면 IP 꾸밈말(`ip_context_ko`)까지.
    had_ip = bool(ip_hits(s) or (src and ip_hits(src)))
    s = trademark_fix(s)
    if had_ip:
        s = _drop_ip_context(s, hits)
    return _tidy(s)


def drop_detail_lines(text: str) -> tuple:
    """S2(오너 2026-10-02) — 상세 본문에서 **가게 통계·운영 줄**을 뺀다 → `(남은 글, 뺀 조각들)`.

    실측: 병기본에 「褶衣折扣店/4.8/88VIP好评率98%/平均12小时发货/客服平均10秒回复」가 번역돼 그대로 실렸다 —
    상품이 아니라 **가게** 이야기다. 표는 `detail_drop_lines`(원격 JSON). 한 줄이 `/`·`|`로 이어져 있으면
    **걸린 조각만** 빼고 나머지 조각은 남긴다(상품 문장을 통째로 잃지 않게). 다 빠진 줄은 줄째 지운다.
    """
    pats = [re.compile(p) for p in (rules().get("detail_drop_lines") or [])]
    if not pats:
        return str(text or ""), []
    dropped: List[str] = []
    out_lines = []
    for line in str(text or "").split("\n"):
        if not any(p.search(line) for p in pats):
            out_lines.append(line)
            continue
        segs = re.split(r"\s*[/|｜]\s*", line)
        keep = []
        for seg in segs:
            if seg.strip() and any(p.search(seg) for p in pats):
                dropped.append(seg.strip())
            elif seg.strip():
                keep.append(seg.strip())
        if keep:
            out_lines.append(" / ".join(keep))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip(), dropped


# ── T3(오너 2026-10-02): 위험 플래그 — 번역이 아니라 **차단·표기**의 일 ───────────────────────────────

def _tm_names(entry) -> List[str]:
    return sorted([str(n) for n in (entry.get("names") or []) if str(n or "").strip()], key=len, reverse=True)


def trademark_fix(text: str) -> str:
    """상표 — `compat`은 「○○ 호환」으로만 둔다(맥세이프 호환·애플워치 호환), `replica`(가구 레플리카)는 **지운다**.
    같은 「○○ 호환」이 두 번 생기면 하나만. 표는 `trademarks`(원격 JSON)."""
    s = str(text or "")
    for e in rules().get("trademarks") or []:
        label, mode = str(e.get("label") or ""), str(e.get("mode") or "")
        names = _tm_names(e)
        if not names:
            continue
        pat = "|".join(re.escape(n) for n in names)
        if mode in ("replica", "drop", "ip"):
            # replica = 지우고 사전검증 보류(가구 레플리카) · drop = 지우기만(「迪奥棕 → 디올 브라운」 같은 색 이름 속 상표)
            # ip = 영화·게임·애니 IP(Y6) — 지우고 사전검증 「상표 확인 보류」(라이선스 확인 전 등록 0)
            s = re.sub(pat, " ", s)
        elif mode == "compat" and label:
            s = re.sub(rf"(?:{pat})(?:\s*호환)?", f"{label} 호환", s)
            want = f"{label} 호환"
            if s.count(want) > 1:
                first = s.index(want) + len(want)
                s = s[:first] + s[first:].replace(want, " ")
    return _tidy(s) if s != str(text or "") else s


def replica_hits(text: str) -> List[str]:
    """가구 레플리카 상표(임스·허먼밀러·바르셀로나…)가 들어 있나 — 라벨 목록."""
    s = str(text or "")
    out = []
    for e in rules().get("trademarks") or []:
        if e.get("mode") == "replica" and any(n in s for n in _tm_names(e)):
            out.append(str(e.get("label") or ""))
    return out


def fix_by_source(text: str, src: str) -> str:
    """Y6 — 원문을 보고 하는 것**만**: 오역 사전(`title_fix_ko`) + IP명·IP 꾸밈말 삭제. 판촉 정리·호환 표기 같은
    나머지 `polish_ko`는 안 한다(쿠팡명 규칙이 「애플 워치」를 따로 붙인다 — 「애플워치 호환」으로 바꾸면 안 됨)."""
    s = str(text or "")
    if not s or not src:
        return s
    t = title_fix(s, src)
    if ip_hits(src) or ip_hits(t):
        t = _drop_ip_context(_drop_ip(t))
    return _tidy(t) if t != s else s


def ip_hits(text: str) -> List[str]:
    """Y6 — 영화·게임·애니 IP명(`trademarks` mode=ip: 星际穿越·漫威·迪士尼·宝可梦…)이 들어 있나 — 라벨 목록."""
    s = str(text or "")
    out = []
    for e in rules().get("trademarks") or []:
        if e.get("mode") == "ip" and any(n in s for n in _tm_names(e)):
            lab = str(e.get("label") or "")
            if lab and lab not in out:
                out.append(lab)
    return out


def _drop_ip(s: str, hits: dict | None = None) -> str:
    for e in rules().get("trademarks") or []:
        if e.get("mode") != "ip":
            continue
        for n in _tm_names(e):
            if n in s:
                s = s.replace(n, " ")
                if hits is not None:
                    hits.setdefault("delete", []).append(f"IP:{e.get('label')}")
    return s


def _drop_ip_context(s: str, hits: dict | None = None) -> str:
    for w in sorted(rules().get("ip_context_ko") or [], key=len, reverse=True):
        if w and w in s:
            s = re.sub(rf"(?<![가-힣]){re.escape(w)}(?![가-힣])", " ", s)
            if hits is not None:
                hits.setdefault("delete", []).append(f"IP 꾸밈말:{w}")
    return s


# ── F(오너 2026-10-06): 옵션 값·규격표 값의 상표 게이트 ─────────────────────────────────────────────
# 운영 실측: 쿠팡 고가네 16401838524 옵션 「디올 블루 미디 스커트」가 통과됐다 — 상표 게이트가 상품명만 봤다.
# 옵션 값·규격표 값에 걸리면 **상품은 보류하지 않고** 그 값만 바꿀 말을 제안한다(검수 카드에 표시 · 오너가 누르면 적용).
# 브랜드 색 이름 치환표(코드 상수 — 원격 JSON 아님). 원문(중문)도 같은 표. 바꿀 말 ""는 삭제.
BRAND_COLOR_SUBS = (
    ("디올 블루", "딥 블루"), ("迪奥蓝", "딥 블루"), ("Dior Blue", "딥 블루"),
    ("티파니 블루", "민트 블루"), ("蒂芙尼蓝", "민트 블루"), ("Tiffany Blue", "민트 블루"),
    ("에르메스 오렌지", "브라이트 오렌지"), ("爱马仕橙", "브라이트 오렌지"), ("Hermes Orange", "브라이트 오렌지"),
    ("샤넬 블랙", "블랙"), ("香奈儿黑", "블랙"), ("Chanel Black", "블랙"),
    ("구찌 그린", "딥 그린"), ("古驰绿", "딥 그린"), ("Gucci Green", "딥 그린"),
    ("팬톤", ""), ("潘通", ""), ("Pantone", ""),
)
_BRAND_SUB_RX: list = []


def _brand_sub_rx() -> list:
    if not _BRAND_SUB_RX:
        for key, rep in BRAND_COLOR_SUBS:
            pat = r"\s*".join(re.escape(w) for w in key.split())          # 「디올블루」·「디올  블루」도
            if _HAN.search(key):
                pat += "色?"                                            # 迪奥蓝色 → 딥 블루
            _BRAND_SUB_RX.append((re.compile(pat, re.I), rep, key))
    return _BRAND_SUB_RX


def brand_value_fix(value: str) -> Dict:
    """값 하나 → `{value, suggest, hits}`. 브랜드 색 이름은 표대로 바꾸고, 그 밖의 상표명(`trademarks` drop·ip·replica —
    디올·샤넬·디즈니…)은 빼서 제안한다. 걸린 게 없으면 `hits=[]`·`suggest==value`. 다 빼면 `suggest=""`(직접 입력)."""
    s = str(value or "")
    hits: List[str] = []
    for rx, rep, key in _brand_sub_rx():
        if rx.search(s):
            s = rx.sub(f" {rep} " if rep else " ", s)
            hits.append(key)
    for e in rules().get("trademarks") or []:
        if e.get("mode") not in ("drop", "ip", "replica"):
            continue
        for n in _tm_names(e):
            if n in s:
                s = s.replace(n, " ")
                lab = str(e.get("label") or n)
                if lab not in hits:
                    hits.append(lab)
    return {"value": str(value or ""), "suggest": _tidy(s) if hits else str(value or ""), "hits": hits}


def brand_value_suggestions(values) -> List[Dict]:
    """[(어디, 값)…] → 걸린 값만 `{where, value, suggest, hits, applicable, why}`. 같은 값은 한 번.
    `applicable`=False면(다 지워짐·한자 남음·30자 초과) 「값을 직접 넣어 주세요」."""
    out: List[Dict] = []
    seen = set()
    for where, v in values or []:
        v = str(v or "").strip()
        if not v or v in seen:
            continue
        seen.add(v)
        r = brand_value_fix(v)
        if not r["hits"]:
            continue
        sug = r["suggest"]
        why = ""
        if not sug:
            why = "상표 이름을 빼면 남는 말이 없어요 — 값을 직접 넣어 주세요"
        elif _HAN.search(sug):
            why = "한자가 남아요 — 한국어 값을 직접 넣어 주세요"
        elif len(sug) > MAX_OPTION_VALUE:
            why = f"{MAX_OPTION_VALUE}자를 넘어요 — 값을 직접 넣어 주세요"
        out.append({"where": str(where or ""), "value": v, "suggest": sug, "hits": r["hits"],
                    "applicable": not why, "why": why})
    return out


def expiry_hits(text: str) -> List[str]:
    """유통기한 임박·떨이 소싱 어휘(临期·过期·清仓·尾货…) — 찾은 낱말."""
    s = str(text or "")
    return [w for w in (rules().get("expiry_block") or []) if w and w in s]


def cn_plug_hits(text: str) -> List[str]:
    """Y8(오너 2026-10-04): 중국 표준 콘센트(五孔·国标插座) — 국내 콘센트와 규격이 달라 쓸 수 없고 전기용품 KC 대상 → 소싱 제외."""
    s = str(text or "")
    return [w for w in (rules().get("cn_plug_block") or []) if w and w in s]


def invented_names(src: str, ko: str) -> List[str]:
    """번역 결과에 **원문에 없는** 고유명이 생겼나(「三宅艺创」 → 「미야케 아키라」). `invented_names` 표:
    [만들어진 이름, 원문에 있으면 괜찮은 표기들]."""
    s, k = str(src or ""), str(ko or "")
    out = []
    for name, markers in rules().get("invented_names") or []:
        if name and name in k and not any(m and m in s for m in markers or []):
            out.append(name)
    return out


def promo_left(text: str) -> List[str]:
    """T2 — 「판촉 직역 남음」 판정. **삭제표 그 자체**로 잰다(polish_ko가 지울 것 = 남은 판촉).
    예전 카운터는 `delete_ko` 낱말만 봐서(4건) 화면에 보이는 것보다 적게 셌다."""
    hits: dict = {}
    polish_ko(text, hits=hits)
    return [h for h in hits.get("delete") or [] if h != "문장 꼬리"]


def ban_hits(text: str) -> List[str]:
    """표시광고 위험 문구(등록 보류 사유) — 찾은 조각 그대로."""
    r = rules()
    s = str(text or "")
    out: List[str] = []
    for p in list(r.get("ban_ko") or []) + list(r.get("ban_cn") or []):
        for m in re.finditer(p, s):
            frag = m.group(0).strip()
            if frag and frag not in out:
                out.append(frag)
    return out


def promo_hits(text: str) -> List[str]:
    """T3: 이미지 OCR 글(원문·번역문)의 판촉 어휘 — 찾은 조각 그대로(프로모션 의심 판정)."""
    r = rules()
    s = str(text or "")
    out: List[str] = []
    for p in r.get("promo_img") or []:
        for m in re.finditer(p, s):
            frag = m.group(0).strip()
            if frag and frag not in out:
                out.append(frag)
    return out


def option_value(value: str) -> Dict:
    """복합 옵션 값 → `{value, left, hits}`. `left`가 비어야 한국어로 다 옮긴 것이다.

    `色[소재]부속 접미사` 모양은 괄호를 조각 경계(` / `)로 바꿔 조각별로 치환한다.
    """
    hits: dict = {}
    s = str(value or "").translate(_FW)
    s = re.sub(r"\s*[\[{]\s*", " / ", s)
    s = re.sub(r"\s*[\]}]\s*", " / ", s)
    s = re.sub(r"\s*[|丨]\s*", " / ", s)
    parts = [preclean_cn(p, hits=hits) for p in s.split(" / ")]
    parts = [polish_ko(p, hits=hits) for p in parts]
    parts = [p for p in parts if p]
    out = " / ".join(parts)
    left = "".join(_HAN.findall(out))
    return {"value": out if not left else "", "draft": out, "left": left, "hits": hits}


def shorten(value: str, limit: int = MAX_OPTION_VALUE) -> str:
    """쿠팡 옵션 값 길이 맞춤 — **자르지 않는다**(T1, 오너 2026-10-02). 넘으면 원래 값 그대로 돌려주고,
    호출부가 「미해석」으로 둔다(`fits`).

    줄이는 순서: ① 판촉·주장(이미 정리 규칙이 지웠다) → ② **용도 꼬리**(현관용·식탁용… `usage_tail_ko`) →
    ③ 소재 조각(핵심 가죽·원단 종류는 색상 조각에 붙여 남김 — T1-H) → ③-b 괄호 부속(U3: 「(내장 충전기)」 → 「충전기 내장」 접두)
    → ③-c 구분자 공백 · 핵심 명사 축약표(U3 `abbrev_ko`) → ④ **기능 나열 뒤부터**(`+`·`,`·` / ` 조각).
    한도는 쿠팡 문서 30자(U3) — 글자 단위.
    """
    v = re.sub(r"\s{2,}", " ", str(value or "")).strip()
    if len(v) <= limit:
        return v
    # ② 용도 꼬리
    for t in sorted(rules().get("usage_tail_ko") or [], key=len, reverse=True):
        if t and t in v:
            cand = _tidy(v.replace(t, " "))
            if cand:
                v = cand
                if len(v) <= limit:
                    return v
    # ③ 소재 조각(옛 규칙 그대로) — U5 실측: 「분리 세탁 / 원목색 / … 커피 브라운 / 쿠션」이 「분리 세탁 테크 패브릭 / 쿠션」이 됐다.
    #   **색상이 빠지는 줄임은 쓰지 않는다**(SKU를 가르는 값 — 빠지면 같은 값이 된다). 색이 다 남는 후보만.
    _cols = [c for c in sorted({ko for _s, ko in (rules().get("colors") or []) if ko}, key=len, reverse=True) if c in v]
    def _keeps_colors(c):
        return all(col in c for col in _cols)
    parts = [p.strip() for p in re.split(r"\s*/\s*", v) if p.strip()]
    if len(parts) >= 3:
        head, mats, tail = parts[0], parts[1:-1], parts[-1]
        keys = [k for k in _KEY_MATERIAL if any(k in m for m in mats) and k not in head]
        keys = [k for k in keys if not any(k != o and k in o for o in keys)]
        cand = " / ".join(x for x in (" ".join([head] + keys[:2]).strip(), tail) if x)
        if len(cand) <= limit and _keeps_colors(cand):
            return cand
        cand = " / ".join(x for x in (head, tail) if x)
        if len(cand) <= limit and _keeps_colors(cand):
            return cand
    r = rules()
    # ③-b U3(오너 2026-10-02): 괄호 부속 — 「(내장 충전기)」는 「충전기 내장」 접두로(표 `paren_prefix_ko`), 그 밖의 괄호
    #    부속은 뗀다(「(쿠션 포함)」은 축약표가 「+쿠션」으로 먼저 바꾼다). 색상이 든 괄호는 남긴다(SKU를 가르는 값).
    _colors = {ko for _s, ko in (r.get("colors") or []) if ko}
    for ab_src, ab_ko in r.get("abbrev_ko") or []:
        if ab_src.startswith("(") and ab_src in v:
            v = v.replace(ab_src, ab_ko)
    for m in list(re.finditer(r"\(([^()]*)\)", v)):
        inner = m.group(1).strip()
        pre = next((ko for src, ko in (r.get("paren_prefix_ko") or []) if src == inner), None)
        if pre:
            v = _tidy(f"{pre} " + v.replace(m.group(0), " "))
        elif inner and not any(c in inner for c in _colors) and len(v) > limit:
            v = _tidy(v.replace(m.group(0), " "))
    if len(v) <= limit:
        return v
    # ③-c 구분자 둘레 공백 · 핵심 명사 축약표(`abbrev_ko` — 「3-in-1 휴대폰 이어폰 거치대」 → 「3in1 거치대」)
    v = re.sub(r"\s*([+/·])\s*", r"\1", v)
    if len(v) <= limit:
        return v
    for ab_src, ab_ko in sorted(r.get("abbrev_ko") or [], key=lambda x: len(x[0]), reverse=True):
        if ab_src and ab_src in v:
            v = _tidy(v.replace(ab_src, ab_ko))
            if len(v) <= limit:
                return v
    # ④ 기능 나열 — **뒤 조각부터** 하나씩 뺀다. 색상이 든 조각은 남긴다(SKU를 가르는 값 — 빼면 뜻이 바뀐다).
    segs = [x.strip() for x in re.split(r"\s*(?:/|\+|,|·)\s*", v) if x.strip()]
    colors_ko = {ko for _src, ko in (rules().get("colors") or []) if ko}
    def _has_color(seg):
        return any(c and c in seg for c in colors_ko)
    while len(segs) > 1:
        drop = next((i for i in range(len(segs) - 1, 0, -1) if not _has_color(segs[i])), None)
        if drop is None:
            drop = next((i for i in range(len(segs)) if not _has_color(segs[i])), None)
        if drop is None:
            break
        segs.pop(drop)
        cand = _tidy(" · ".join(segs))
        if len(cand) <= limit:
            return cand
    return v                      # 그래도 넘으면 **자르지 않는다** — 호출부가 「미해석」


def fits(value: str, limit: int = MAX_OPTION_VALUE) -> bool:
    return len(str(value or "")) <= limit


# ── U(오너 2026-10-02): 옵션이 아닌 값 · 검색어 정리 · 전송 칸 외국어 ─────────────────────────────

_KANA = re.compile("[\u3040-\u30ff\u31f0-\u31ff]")


def has_foreign(text) -> bool:
    """한국 마켓에 나가면 안 되는 글자(한자·가나)가 있나."""
    s = str(text or "")
    return bool(_HAN.search(s) or _KANA.search(s))


def non_option(value: str) -> List[str]:
    """U4 — 옵션이 아니라 **보증·서비스·안내·화면 문구**인 값(「售后品质保障丨购买无忧」「【超长3年质保】」「加入购物车」)이면
    걸린 조각들. 이런 SKU는 등록에서 빼고 번역기에도 보내지 않는다(표 `non_option_re`, 원격 JSON)."""
    s = str(value or "")
    out: List[str] = []
    for p in rules().get("non_option_re") or []:
        m = re.search(p, s)
        if m and m.group(0) not in out:
            out.append(m.group(0))
    return out


_TOKEN = re.compile(r"[가-힣A-Za-z0-9]+")


def clean_tags(tags, title_ko: str = "", limit: int = 20) -> List[str]:
    """U1 — 검색어(쿠팡 `searchTags`) 정리. 실측: 16401838524에 「미야케·아키라의·감각이」가 실렸다 —
    검색어가 **옛 번역 제목을 낱말로 자른 것**이라, 제목을 고쳐도(T3) 검색어엔 지어낸 이름이 남았다.

    규칙: ① **지금 상품명에 낱말로 있는 것만**(상품명이 정본 — 옛 번역의 흔적은 빠진다) ② 지어낸 이름·상표(`invented_names`·
    `trademarks`) 낱말 빼기 ③ 조사 꼬리(「상의와」「돋보이는」 — `tag_drop_re`) 빼기 ④ 같은 말 하나만. 상품명이 비면 ①은 건너뛴다.
    """
    r = rules()
    have = {t.lower() for t in _TOKEN.findall(str(title_ko or ""))}
    bad_names = {str(n).lower() for n, _m in (r.get("invented_names") or [])}
    for e in r.get("trademarks") or []:
        bad_names |= {str(n).lower() for n in _tm_names(e)} | {str(e.get("label") or "").lower()}
    drops = [re.compile(p) for p in r.get("tag_drop_re") or []]
    out: List[str] = []
    for t in tags or []:
        t = str(t or "").strip()
        if not t or has_foreign(t):
            continue
        low = t.lower()
        if have and low not in have:
            continue
        if low in bad_names or any(b and len(b) > 1 and b in low for b in bad_names):
            continue
        if any(p.search(t) for p in drops):
            continue
        if low not in {x.lower() for x in out}:
            out.append(t[:limit])
    return out


# ── J0(오너 2026-09-30-J): 브랜드 한자 → 병음 대문자 ─────────────────────────────
# 오너 규칙: 상품명 **맨 앞**이 한자 2~4자이고 그 글자가 소싱처의 브랜드·가게 필드와 **일치**하면 브랜드로 보고
# 번역하지 않는다(懒小姐 → 「게으른 아가씨」 직역 금지) → 병음 대문자(LANXIAOJIE) + 「브랜드 표기 — 확인」 배지.
# 일치하지 않으면 평소대로 번역. 필드가 비어 있으면 **판정하지 않는다**(제목만 보고 브랜드라 짐작하지 않음).
BRAND_FIELDS = ("brand", "shop_name", "shop", "seller_nick")
_SHOP_SUFFIX = re.compile(r"(官方旗舰店|旗舰店|专营店|专卖店|官方店|企业店|工厂店|品牌店|直营店|官方|店)$")
_HAN_ONLY = re.compile("^[㐀-䶿一-鿿]+$")


def romanize(han: str) -> str:
    """한자 → 병음 대문자 붙여쓰기(성조 없음). 라이브러리가 없거나 못 옮긴 글자가 있으면 빈 문자열(정직)."""
    try:
        from pypinyin import lazy_pinyin
    except Exception:
        return ""
    parts = lazy_pinyin(str(han or ""))
    out = "".join(parts).upper()
    return out if out and re.fullmatch(r"[A-Z]+", out) else ""


def _brand_core(field: str, value: str) -> str:
    v = str(value or "").strip().translate(_FW)
    if field != "brand":
        v = _SHOP_SUFFIX.sub("", v)
    v = re.split(r"[/(（\s]", v, maxsplit=1)[0].strip()       # 「懒小姐/LANXIAOJIE」 같은 병기는 앞쪽만
    return v


def brand_prefix(title: str, extra: dict | None) -> Dict | None:
    """`{han, latin, field, rest}` 또는 None. 제목 맨 앞 한자 2~4자 == 브랜드·가게 필드(접미 「旗舰店」 등 뗌)."""
    t = str(title or "").strip().translate(_FW)
    ex = extra or {}
    # K(오너 역질문안 2026-10-01): 브랜드 필드가 **있으면 그것만** 본다. 가게 이름은 브랜드가 비었을 때만 —
    #   접미(旗舰店·专卖店·官方…)를 떼고, 뗀 뒤 2자 미만이면 브랜드 없음(「XX旗舰店」이 병음으로 박히는 사고 방지).
    fields = ("brand",) if str(ex.get("brand") or "").strip() else BRAND_FIELDS[1:]
    for f in fields:
        core = _brand_core(f, ex.get(f) or "")
        if not (2 <= len(core) <= 4 and _HAN_ONLY.match(core) and t.startswith(core)):
            continue
        latin = romanize(core)
        if not latin:
            return None
        return {"han": core, "latin": latin, "field": f, "rest": t[len(core):].strip()}
    return None


def title_for_translator(title: str, extra: dict | None) -> tuple:
    """번역기에 보낼 제목 + 브랜드 판정. 브랜드면 그 글자를 떼고 보낸다(번역기가 직역하지 못하게)."""
    info = brand_prefix(title, extra)
    src = info["rest"] if info else str(title or "")
    return (strip_cn(src) or src), info


def attach_brand(title_ko: str, info: Dict | None) -> str:
    """번역된 제목 앞에 병음 브랜드를 붙인다(이미 붙어 있으면 그대로)."""
    s = str(title_ko or "").strip()
    if not info:
        return s
    if s.upper().startswith(info["latin"]):
        return s
    return f"{info['latin']} {s}".strip()
