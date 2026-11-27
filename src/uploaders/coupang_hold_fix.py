"""오너 11-26 저녁 ③ — 쿠팡 사전검증 보류를 **폰 카드 안에서** 고치게.

쿠팡 판정(`CoupangUploader.precheck`)은 보류를 사람 말 한 줄씩(`holds`)으로만 준다 → 카드는 「다시 사전검증」밖에 못 냈다.
여기서 그 한 줄을 읽어 **고치는 길**(fix 코드)과 **입력칸**(fields)으로 바꾼다. 판정 문구를 지어내지 않는다 — 아는 꼴만 읽고,
모르는 줄은 그대로(fix 없음 → 카드는 「다시 사전검증」).

fix 코드(카드 `holdFixHtml`이 버튼·입력으로 바꾼다):
  cp_attr      필수 옵션 값 입력(「필수 옵션: 용량」·「필수 옵션(택1): A 또는 B」·「「용량」 단위…」)
  cp_value     옵션 값 한국어 입력(「옵션 값 미해석: X」·「옵션 값 n개를 한국어로 옮기지 못했습니다 …: a, b」)
  cp_origin    원산지 입력(「고시정보 실값 미확인(원산지 …)」)
  cp_outbound  출고지 — 계정 설정(마켓 연동 › 쿠팡). 상품 카드에서 못 채운다(링크).
  cp_invoice   구매대행 인보이스 주소 — 오너 결정(설정). 상품 카드에서 못 채운다(안내).
  cp_category  카테고리 예측 실패 — 임의 카테고리 금지. 상품명을 고치면 다시 예측(상품명 고치기).
  edit-option  한 옵션에 값이 여러 개(SKU별 가격 필요) · 옵션 값이 같아짐
  edit-title   외국어가 남은 칸
  price        SKU 판매가 미확정(원가 넣기)
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

_REQ_RE = re.compile(r"^필수 옵션:\s*(.+)$")
_ONE_RE = re.compile(r"^필수 옵션\(택1\):\s*(.+?)(?:\s+—\s+.*)?$")
_UNIT_RE = re.compile(r"^「([^」]{1,40})」\s+(?!값이 \d+개)(.+)$")
_MULTI_RE = re.compile(r"^「([^」]{1,40})」\s+값이 \d+개입니다")
_UNRES_RE = re.compile(r"^옵션 값 미해석:\s*(.+?)\s+—\s+")
_UNMAPPED_RE = re.compile(r"^옵션 값 \d+개를 한국어로 옮기지 못했습니다 — .*?:\s*(.+)$")


def parse(holds: List[str]) -> Tuple[List[str], List[Dict]]:
    """보류 줄 → `(fixes, fields)`. fields = `[{kind: attr|attr_one|value|origin, name|names|orig, line}]`."""
    fixes: List[str] = []
    fields: List[Dict] = []
    seen = set()

    def fix(c):
        if c not in fixes:
            fixes.append(c)

    def add(f):
        key = (f["kind"], f.get("name") or tuple(f.get("names") or ()) or f.get("orig") or "")
        if key not in seen:
            seen.add(key)
            fields.append(f)

    for raw in holds or []:
        line = str(raw or "").strip()
        if not line:
            continue
        m = _ONE_RE.match(line)
        if m:
            names = [n.strip() for n in m.group(1).split(" 또는 ") if n.strip()]
            if names:
                fix("cp_attr")
                add({"kind": "attr_one", "names": names[:6], "line": line})
            continue
        m = _REQ_RE.match(line)
        if m:
            fix("cp_attr")
            for n in [x.strip() for x in m.group(1).split(",") if x.strip()][:8]:
                add({"kind": "attr", "name": n, "line": line})
            continue
        if _MULTI_RE.match(line):
            fix("edit-option")
            continue
        m = _UNRES_RE.match(line)
        if m:
            fix("cp_value")
            add({"kind": "value", "orig": m.group(1).strip()[:60], "line": line})
            continue
        m = _UNMAPPED_RE.match(line)
        if m:
            fix("cp_value")
            for v in [x.strip() for x in m.group(1).split(",") if x.strip()][:12]:
                add({"kind": "value", "orig": v[:60], "line": line})
            continue
        if line.startswith("고시정보 실값 미확인") and "원산지" in line:
            fix("cp_origin")
            add({"kind": "origin", "line": line})
            continue
        if "인보이스" in line:
            fix("cp_invoice")
            continue
        if "출고지" in line:
            fix("cp_outbound")
            continue
        if line.startswith("쿠팡 카테고리 예측 실패"):
            fix("cp_category")
            continue
        if line.startswith("원문(외국어)이 남은 칸"):
            fix("edit-title")
            continue
        if line.startswith("SKU 판매가 미확정"):
            fix("price")
            continue
        if line.startswith("옵션 값이 같아집니다"):
            fix("edit-option")
            continue
        m = _UNIT_RE.match(line)                       # 「용량」 단위/숫자 문제 — 마지막(위 꼴이 아닐 때만)
        if m:
            fix("cp_attr")
            add({"kind": "attr", "name": m.group(1).strip(), "line": line})
    return fixes, fields
