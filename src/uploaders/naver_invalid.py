"""Y7-F(오너 2026-10-09) — 네이버 400 `invalidInputs` → 필드별 사람 말·고치러 갈 곳. **한 매퍼**.

등록(`naver_uploader.upload_product`)·사전검증(네이버 필수 칸 사전 점검)·화면(폰 카드·폰 모달·데스크톱 결과)이
모두 이 표를 쓴다 — 자리마다 문구를 따로 두면 한 곳만 고쳐진다(이 세션 4례).

13:32 KST 실측: 400 본문에 `invalidInputs`가 2개(상세 본문·최소구매수량)라 약 430자 — 업로더가 본문을
300자에서 잘라 JSON을 못 읽었고, 매핑이 빈손이 되어 화면은 「잠시 뒤 다시 시도」(api_error)였다.
→ 본문은 자르지 않고 받고, 그래도 잘렸으면 정규식으로 이름·메시지를 건진다.
400은 다시 해도 같은 답이다 — **재시도 안내를 붙이지 않는다**(Y7-B 결정).
"""
from __future__ import annotations

import json
import re
from typing import Dict, List

#: 필드 이름 → (화면 한 줄, 고치러 갈 곳 종류). 종류는 아래 `ACTIONS`의 키.
#: 표에 없는 칸은 「칸 — 값 확인(네이버 메시지)」 — 네이버가 준 메시지(예: 「최소 10원」)가 그대로 쓸모 있다.
#: `minPurchaseQuantity`는 표에 없다 — 이제 보내지 않으므로(Y7-F 2번) 나올 일이 없다(나오면 원문 그대로 보인다).
FIELDS: Dict[str, tuple] = {
    "originProduct.leafCategoryId": ("카테고리를 다시 지정하세요(카테고리 지정 →)", "category"),
    "originProduct.detailContent": ("상세 본문 비어 있음 — 상세페이지 꾸미기에서 채우기", "detail"),
}

#: 고치러 갈 곳 — (버튼 글자, 주소 틀). `{iid}` = 수집 행 번호. 우리 앱 경로만.
ACTIONS: Dict[str, tuple] = {
    "category": ("카테고리 지정 →", "/seller/collect/{iid}/naver-category"),
    "detail": ("상세페이지 꾸미기 →", "/seller/collect/preview/{iid}?tab=detail"),
    "thumb": ("썸네일 탭 →", "/seller/collect/preview/{iid}?tab=thumb"),
    "price": ("가격 탭 →", "/seller/collect/preview/{iid}?tab=price"),
}

_ITEM_RE = re.compile(r'\{[^{}]*?"name"\s*:\s*"([^"]+)"[^{}]*?(?:"message"\s*:\s*"([^"]*)")?[^{}]*?\}')


def parse(body: str) -> List[Dict[str, str]]:
    """400 본문 → `[{name, type, message}]`. JSON이 깨졌으면(잘림 등) 정규식으로 건진다. 없으면 빈 목록."""
    text = str(body or "")
    try:
        data = json.loads(text)
        items = (data or {}).get("invalidInputs") if isinstance(data, dict) else None
        if isinstance(items, list):
            return [{"name": str(i.get("name") or "").strip(), "type": str(i.get("type") or "").strip(),
                     "message": str(i.get("message") or "").strip()} for i in items if isinstance(i, dict)]
    except (TypeError, ValueError):
        pass
    if "invalidInputs" not in text:
        return []
    seg = text[text.index("invalidInputs"):]
    out = []
    for m in _ITEM_RE.finditer(seg):
        out.append({"name": m.group(1).strip(), "type": "", "message": (m.group(2) or "").strip()})
    if not out:                                     # 객체가 끝나기 전에 잘린 마지막 항목 — 이름만이라도
        for nm in re.findall(r'"name"\s*:\s*"([^"]+)"', seg):
            out.append({"name": nm.strip(), "type": "", "message": ""})
    return out


def action_for(kind: str, item_id: str = "") -> Dict[str, str]:
    label, tpl = ACTIONS.get(kind, ("", ""))
    if not label or not item_id:
        return {"label": "", "url": ""}
    return {"label": label, "url": tpl.format(iid=item_id)}


def row(name: str, message: str = "", item_id: str = "") -> Dict[str, str]:
    """필드 하나 → `{name, line, action_label, action_url}`. 표에 없는 이름은 「필드 — 값 확인(네이버 메시지)」."""
    line, kind = FIELDS.get(name, ("", ""))
    if not line:
        line = f"{name or '(필드 이름 없음)'} — 값 확인" + (f"({message})" if message else "")
    act = action_for(kind, item_id)
    return {"name": name, "line": line, "action_label": act["label"], "action_url": act["url"]}


def rows(body: str, item_id: str = "") -> List[Dict[str, str]]:
    return [row(i["name"], i["message"], item_id) for i in parse(body)]


def first_action(rs: List[Dict[str, str]]) -> Dict[str, str]:
    """화면에 버튼은 하나 — 고칠 곳이 있는 첫 줄."""
    for r in rs:
        if r.get("action_url"):
            return {"label": r["action_label"], "url": r["action_url"]}
    return {"label": "", "url": ""}
