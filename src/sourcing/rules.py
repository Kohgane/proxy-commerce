"""src/sourcing/rules.py — 소싱 원칙(F24). **콘솔 검수표와 봇이 같이 읽는 한 곳.**

## 원칙은 사람이 정하고 봇은 재서 말한다 — 판정은 사장님

지금까지 기준은 **코드 상수**였다: `DEFAULT_MARGIN_RATE = 27.4`, 배송비 `0.35 * 원가`.
오너가 기준을 바꾸려면 코드를 고쳐 배포해야 했다. 원칙은 사람이 정하는 것인데
사람이 못 바꾸는 자리에 있었다. 그래서 **값만** 밖으로 뺐다 — 판정 로직은 그대로다.

## 두 벌 금지

콘솔 검수표(`build_source_review_row`)와 텔레그램 봇이 **이 표 하나**를 읽는다.
비어 있으면 옛 상수가 기본값으로 선다(무회귀) — 이 표는 「덮어쓰기」이지 「이관」이 아니다.

## 키가 (봇, user_id)인 이유

한 사람이 봇 둘로 사업 둘(고가네·우주대행)을 굴린다. **원가 하한도 마진도 사업마다 다르다.**
`bot_slug=""`는 콘솔이 읽는 기본 행이다.

## 잴 수 없는 것은 규칙으로 두되 자동 판정하지 않는다

국내 갭·국내 수요는 **우리에게 자동 실측 수단이 없다.** 그래서 값은 보관하되 판정은
「수동 확인」으로 낸다(`src/sourcing/verdict.py`). 있는 척하면 그 숫자로 결정이 내려진다.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 부피무게 제수 — 항공 국제표준(가로×세로×높이cm ÷ 5000 = kg).
VOLUMETRIC_DIVISOR = 5000


def _default_margin() -> float:
    """옛 상수를 **그대로** 기본값으로 승계한다(발명 0)."""
    try:
        from src.pipeline.coupang_replicate import DEFAULT_MARGIN_RATE
        return float(DEFAULT_MARGIN_RATE)
    except Exception:
        return 27.4


# 트렌드 봇 6원칙을 그대로 코드화. `key`는 저장용, `ko`는 사람이 부르는 이름(그게 명령어가 된다).
FIELDS: Tuple[dict, ...] = (
    {"key": "cost_min_usd", "ko": "원가", "unit": "$", "kind": "num",
     "aliases": ("원가", "원가최소", "최소원가", "cost"),
     "desc": "이보다 싼 물건은 배송비·수수료가 마진을 다 먹는다"},
    {"key": "domestic_gap_max", "ko": "국내갭", "unit": "건", "kind": "num",
     "aliases": ("국내갭", "갭", "경쟁", "gap"),
     "desc": "국내 판매처가 이보다 많으면 가격 싸움이 된다 — 자동 실측 수단 없음(수동 확인)"},
    {"key": "niche_brand_required", "ko": "니치브랜드", "unit": "", "kind": "flag",
     "aliases": ("니치브랜드", "니치", "브랜드", "niche"),
     "desc": "무명·니치 브랜드만 담을지"},
    {"key": "domestic_demand_required", "ko": "국내수요", "unit": "", "kind": "flag",
     "aliases": ("국내수요", "수요", "demand"),
     "desc": "국내 수요가 확인된 것만 담을지 — 자동 실측 수단 없음(수동 확인)"},
    {"key": "trademark_block", "ko": "상표권", "unit": "", "kind": "flag",
     "aliases": ("상표권", "총판", "trademark"),
     "desc": "국내 총판이 있으면 반려"},
    {"key": "ship_cost_max_pct", "ko": "배송비율", "unit": "%", "kind": "num",
     "aliases": ("배송비율", "배송비", "배송", "ship"),
     "desc": f"배송비가 원가의 이 비율을 넘으면 위반(부피무게 = 가로×세로×높이÷{VOLUMETRIC_DIVISOR})"},
    {"key": "target_margin_pct", "ko": "마진", "unit": "%", "kind": "num",
     "aliases": ("마진", "마진율", "목표마진", "margin"),
     "desc": "목표 마진율 — 판매가 자동 규칙이 이 값으로 값을 매긴다"},
)

_BY_KEY = {f["key"]: f for f in FIELDS}

# 켜짐/꺼짐을 부르는 말 — 사람이 쓰는 말을 받는다(「예/아니오」도 말이다).
_ON = {"on", "예", "네", "켜", "켜기", "필수", "true", "1", "y", "yes"}
_OFF = {"off", "아니오", "아니요", "끄기", "꺼", "선택", "false", "0", "n", "no"}

_MEM: Dict[Tuple[str, str], dict] = {}


def defaults() -> dict:
    """기본 원칙 — **옛 코드 상수를 그대로** 승계한다.

    새 숫자를 여기서 지어내지 않는다. 오너가 정한 적 없는 값이 기본값으로 서면,
    그건 우리가 정한 원칙이 된다.
    """
    return {
        "cost_min_usd": None,              # 오너가 정한 적 없다 → 판정 안 함
        "domestic_gap_max": None,
        "niche_brand_required": False,
        "domestic_demand_required": False,
        "trademark_block": True,           # 기존 검수표가 이미 IPR 경고를 낸다
        "ship_cost_max_pct": 35.0,         # register_pipe의 `0.35 * cost_krw`
        "target_margin_pct": _default_margin(),
    }


def _enabled() -> bool:
    try:
        from src.db import pg
        return bool(pg.pg_enabled())
    except Exception:
        return False


def reset_for_tests() -> None:
    _MEM.clear()


def get(user_id: str, *, bot_slug: str = "") -> dict:
    """이 (봇, 사람)의 원칙. 저장된 값이 기본값을 **덮어쓴다**(없는 키는 기본값)."""
    base = defaults()
    key = (str(bot_slug or ""), str(user_id or ""))
    stored: Optional[dict] = None
    if _enabled():
        try:
            from src.db import pg
            with pg.query() as cur:
                cur.execute("SELECT rules FROM sourcing_rules "
                            "WHERE bot_slug = %s AND user_id = %s AND deleted_at IS NULL",
                            key)
                row = cur.fetchone()
            if row:
                stored = row[0] if isinstance(row[0], dict) else None
        except Exception as exc:
            logger.warning("[소싱원칙] 조회 실패(기본값 사용): %s", exc)
    else:
        stored = _MEM.get(key)
    if isinstance(stored, dict):
        for k, v in stored.items():
            if k in base:
                base[k] = v
    return base


def set_one(user_id: str, field_key: str, value, *, bot_slug: str = "") -> bool:
    """원칙 한 줄을 바꾼다. **한 번에 하나** — 여러 개를 한 줄에 받으면 되묻기가 애매해진다."""
    if field_key not in _BY_KEY:
        return False
    key = (str(bot_slug or ""), str(user_id or ""))
    cur_rules = {k: v for k, v in get(user_id, bot_slug=bot_slug).items()}
    cur_rules[field_key] = value
    if not _enabled():
        _MEM[key] = cur_rules
        return True
    import json
    try:
        from src.db import pg
        with pg.tx() as cur:
            cur.execute(
                "INSERT INTO sourcing_rules (bot_slug, user_id, rules) VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (bot_slug, user_id) WHERE deleted_at IS NULL "
                "DO UPDATE SET rules = EXCLUDED.rules",
                (key[0], key[1], json.dumps(cur_rules, ensure_ascii=False)))
        return True
    except Exception as exc:
        logger.warning("[소싱원칙] 저장 실패: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 사람이 쓴 한 줄 → 바꿀 항목과 값
# ---------------------------------------------------------------------------

def parse_command(arg: str):
    """`원가 50` · `배송비율 35` · `마진 25` · `니치브랜드 예` → `(field, value)`.

    못 알아들으면 `(None, 이유)` — **짐작해서 바꾸지 않는다.** 원칙을 잘못 바꾸면
    그 뒤 모든 판정이 조용히 틀린다. 되묻는 편이 싸다.
    """
    txt = re.sub(r"\s+", " ", str(arg or "")).strip()
    if not txt:
        return None, "empty"
    parts = txt.split(" ")
    if len(parts) < 2:
        return None, "no_value"
    name = parts[0].strip().lower().replace("_", "")
    raw = " ".join(parts[1:]).strip()

    fld = None
    for f in FIELDS:
        if name in {a.lower() for a in f["aliases"]} or name == f["key"]:
            fld = f
            break
    if fld is None:
        return None, "unknown_field"

    if fld["kind"] == "flag":
        low = raw.lower()
        if low in _ON:
            return fld["key"], True
        if low in _OFF:
            return fld["key"], False
        return None, "bad_flag"

    m = re.search(r"-?\d+(?:\.\d+)?", raw.replace(",", ""))
    if not m:
        return None, "bad_number"
    val = float(m.group(0))
    if val < 0:
        return None, "bad_number"
    if fld["key"].endswith("_pct") and val > 100:
        return None, "bad_percent"
    # 건수는 정수로 — 「국내갭 3.5건」은 뜻이 없다.
    if fld["key"] == "domestic_gap_max":
        val = int(round(val))
    return fld["key"], val


def format_value(field_key: str, value) -> str:
    """값 하나를 사람이 읽는 꼴로. **정한 적 없으면 그렇게 쓴다**(0으로 채우지 않는다)."""
    fld = _BY_KEY.get(field_key)
    if fld is None:
        return str(value)
    if value is None:
        return "정한 적 없음"
    if fld["kind"] == "flag":
        return "필수" if value else "선택"
    num = int(value) if float(value) == int(float(value)) else value
    unit = fld["unit"]
    return f"{unit}{num}" if unit == "$" else f"{num}{unit}"


def as_table(rules: dict) -> list:
    """`[(ko, 값문자열, 설명)]` — 화면·답장이 같은 순서로 쓴다."""
    return [(f["ko"], format_value(f["key"], rules.get(f["key"])), f["desc"]) for f in FIELDS]


def volumetric_kg(cm_l, cm_w, cm_h) -> Optional[float]:
    """부피무게(kg) = 가로×세로×높이 ÷ 5000. 치수가 하나라도 없으면 **None**(미측정)."""
    try:
        vals = [float(x) for x in (cm_l, cm_w, cm_h)]
    except (TypeError, ValueError):
        return None
    if any(v <= 0 for v in vals):
        return None
    return round(vals[0] * vals[1] * vals[2] / VOLUMETRIC_DIVISOR, 2)
