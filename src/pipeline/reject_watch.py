"""src/pipeline/reject_watch.py — 등록 파이프 P4: 쿠팡 반려감시 서버화 (rej_watch·watch_* 이식).

Bluehost `rej_watch.py`(2h 크론) → 콘솔/크론 조회·분류·알림. **기존 반려 처리 표준 그대로**(새 분류 발명 0):
  - 반려 사유 = `/histories`의 **comment** (상태 문구 "담당자 검토 결과 반려"가 아님 — [[반려 사유 요약 오독 지뢰]]).
  - 반려 3유형 → 처방: 이미지 규격→**재등록** / 담당자검토=상표권→**삭제 권고** / 옵션값→**값 대체**.
  - 애플 카테고리 사전승인 반려(TORRAS 전례) → **iPhone 표기 보류 · 삼성/픽셀용 유효** 분류.
감시 = **조회·분류·알림까지**. 자동 재등록/삭제는 **배선하되 실행은 오너 승인 게이트 뒤**(비가역).
전부 주입 가능(history_fn/apply_fn)해 오프라인 계약 검증(쿠팡 자격·네트워크 없이).
"""
from __future__ import annotations

import re
from typing import Optional

# ── 반려 유형 · 처방 (기존 표준 — 새 체계 발명 금지) ──────────────────────────────
REJECTION_KINDS = {
    "image_spec":     {"ko": "이미지 규격",            "rx": "reupload",       "rx_ko": "재등록"},
    "trademark":      {"ko": "상표권(담당자 검토)",     "rx": "delete",         "rx_ko": "삭제 권고"},
    "option_value":   {"ko": "옵션값",                "rx": "replace_option", "rx_ko": "값 대체"},
    "apple_category": {"ko": "애플 카테고리 사전승인 반려", "rx": "hold_or_reissue",
                       "rx_ko": "iPhone 표기 보류 · 삼성/픽셀용 유효"},
    "unknown":        {"ko": "미분류",                "rx": "manual",         "rx_ko": "오너 확인 필요"},
}

# comment 키워드 규칙(사유 텍스트 기준 — 상태 문구 아님). 우선순위: 애플>상표권>옵션>이미지.
_APPLE_RE = re.compile(r"애플|apple|아이폰|iphone|아이패드|ipad|맥북|macbook|에어팟|airpod|casetify|mfi|사전\s*승인", re.I)
_TRADEMARK_RE = re.compile(r"상표|브랜드\s*권|권리\s*침해|지식\s*재산|정품|위조|라이선스|licen[sc]e|가품|병행\s*수입\s*불가", re.I)
_OPTION_RE = re.compile(r"옵션\s*값|구매\s*옵션|옵션\s*정보|옵션\s*누락|사이즈\s*표기|색상\s*표기|단위\s*수량", re.I)
_IMAGE_RE = re.compile(r"이미지|사진|대표\s*이미지|화질|해상도|규격|누끼|워터마크|배경\s*처리|픽셀", re.I)

# 애플 세부 — 대상 기기로 처방 분기(오너 지시). **기기 모델 토큰만**(바 '애플/apple' 카테고리어는 제외 —
#   comment의 '애플 카테고리'가 대상 기기로 오분류되지 않게). 대상 판정은 title+comment의 기기 토큰으로.
_IPHONE_TARGET_RE = re.compile(r"아이폰|iphone|아이패드|ipad|맥북|macbook|에어팟|airpod", re.I)
_ANDROID_TARGET_RE = re.compile(r"삼성|samsung|갤럭시|galaxy|픽셀|pixel", re.I)

_STATUS_PHRASE_RE = re.compile(
    r"(담당자\s*)?검토\s*결과\s*반려(되었습니다|되었음|됐습니다|됨)?\.?")


def classify_rejection(comment: str, *, title: str = "") -> dict:
    """반려 comment → 유형·처방. **comment(사유)로만 판정**(상태 문구는 사유 아님 — 오독 지뢰).

    반환 {kind, kind_ko, prescription, prescription_ko, apple_target?, matched, comment_is_status_only}.
    comment가 상태 문구뿐(사유 미상)이면 kind=unknown + comment_is_status_only=True(오너 확인 — 자동판정 금지).
    """
    c = str(comment or "").strip()
    text = f"{c} {title}"
    status_only = bool(c) and bool(_STATUS_PHRASE_RE.search(c)) and len(_STATUS_PHRASE_RE.sub("", c).strip()) < 4

    def _mk(kind, matched="", **extra):
        meta = REJECTION_KINDS[kind]
        return {"kind": kind, "kind_ko": meta["ko"], "prescription": meta["rx"],
                "prescription_ko": meta["rx_ko"], "matched": matched,
                "comment_is_status_only": status_only, **extra}

    if not c or status_only:
        # 사유 없음 / 상태 문구만 → 자동 판정 금지(오너 확인). [[반려 사유 요약 오독 지뢰]]
        return _mk("unknown", matched="")
    m = _APPLE_RE.search(text)
    if m:
        # 애플 카테고리 사전승인 반려 — **대상 기기 토큰(title+comment)**으로 분기.
        # (바 '애플 카테고리'는 사유지 대상 기기가 아니다 — 기기 모델 토큰만으로 판정해 오분류 방지.)
        tgt = f"{title or ''} {c}"
        if _ANDROID_TARGET_RE.search(tgt) and not _IPHONE_TARGET_RE.search(tgt):
            target = "android"      # 삼성/픽셀용 → 유효(재등록 가능)
        elif _IPHONE_TARGET_RE.search(tgt):
            target = "apple"        # iPhone/애플용 → 표기 보류
        else:
            target = "unknown"
        return _mk("apple_category", matched=m.group(0), apple_target=target)
    m = _TRADEMARK_RE.search(text)
    if m:
        return _mk("trademark", matched=m.group(0))
    m = _OPTION_RE.search(text)
    if m:
        return _mk("option_value", matched=m.group(0))
    m = _IMAGE_RE.search(text)
    if m:
        return _mk("image_spec", matched=m.group(0))
    return _mk("unknown", matched="")


def latest_rejection_comment(history) -> str:
    """`/histories` 응답 → 가장 최근 반려 comment. **튜플/딕트/리스트 안전**([[ship_real get 튜플 반환]]).

    history: (status, body) 튜플 · {"data":[...]} 딕트 · [...] 리스트 모두 허용. 반려행의 comment만.
    반려행 판정: statusName/status에 '반려'/'REJECT' 포함. 없으면 마지막 comment 폴백(빈 문자열 가능).
    """
    body = history
    if isinstance(history, (tuple, list)) and len(history) == 2 and not isinstance(history[0], dict):
        body = history[1]                                  # (status, body) 언패킹
    if isinstance(body, dict):
        rows = body.get("data") or body.get("histories") or body.get("content") or []
    elif isinstance(body, (list, tuple)):
        rows = list(body)
    else:
        rows = []
    rej = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        st = str(r.get("statusName") or r.get("status") or r.get("changeStatus") or "")
        cm = str(r.get("comment") or r.get("reason") or r.get("memo") or "").strip()
        if ("반려" in st or "REJECT" in st.upper()) and cm:
            rej.append(cm)
    if rej:
        return rej[-1]
    # 폴백: 마지막 comment(반려 표기 없어도) — 조용한 누락 방지.
    for r in reversed(rows):
        if isinstance(r, dict):
            cm = str(r.get("comment") or r.get("reason") or "").strip()
            if cm:
                return cm
    return ""


def scan_rejections(items, *, history_fn, classify_fn=None) -> dict:
    """반려/SAVED 상품 목록 → 조회·분류 큐. **등록/삭제 안 함**(감시=조회·분류·알림).

    items = [{sid, title, account, status?}]. history_fn(sid, account)→ `/histories` 응답(주입).
    반환 {rows[], by_kind{}, by_prescription{}, alert, needs_manual, scanned}.
    """
    classify_fn = classify_fn or classify_rejection
    rows, by_kind, by_rx = [], {}, {}
    for it in (items or []):
        sid = str((it or {}).get("sid") or "").strip()
        if not sid:
            continue
        title = str((it or {}).get("title") or "")
        account = (it or {}).get("account")
        comment = ""
        try:
            comment = latest_rejection_comment(history_fn(sid, account))
        except Exception as exc:                           # 조회 실패 = 정직(미분류·사유에 기록), 다음 계속
            cl = classify_rejection("", title=title)
            rows.append({"sid": sid, "title": title, "account": account, "comment": "",
                         "error": f"histories 조회 실패: {exc}", **cl})
            by_kind["unknown"] = by_kind.get("unknown", 0) + 1
            continue
        cl = classify_fn(comment, title=title)
        row = {"sid": sid, "title": title, "account": account, "comment": comment, **cl}
        rows.append(row)
        by_kind[cl["kind"]] = by_kind.get(cl["kind"], 0) + 1
        by_rx[cl["prescription"]] = by_rx.get(cl["prescription"], 0) + 1
    needs_manual = [r for r in rows if r["kind"] == "unknown"]
    parts = [f"{REJECTION_KINDS[k]['ko']} {n}" for k, n in sorted(by_kind.items(), key=lambda x: -x[1])]
    alert = f"반려 {len(rows)}건 — " + (" · ".join(parts) if parts else "없음")
    if needs_manual:
        alert += f" · 미분류 {len(needs_manual)}건(오너 확인)"
    return {"rows": rows, "by_kind": by_kind, "by_prescription": by_rx,
            "alert": alert, "needs_manual": len(needs_manual), "scanned": len(rows)}


def watch_registered(*, queue_fn, history_fn, classify_fn=None, record_fn=None,
                     notify_fn=None, limit: int = 50, time_budget_sec: float = 0,
                     monotonic_fn=None) -> dict:
    """**자동 감시 1회전** — 등록 대장에서 감시 대상을 꺼내 조회·분류하고 결과를 되쓴다.

    등록 파이프 관통 후의 P4 몫: 오너가 sid를 손으로 넣지 않아도 서버가 **무엇을 등록했는지 알고**
    스스로 감시한다. 여기서도 **실행은 0**(조회·분류·기록·알림까지) — 처방 실행은 승인 게이트 뒤.

    - queue_fn(limit)→[{sid,title,account}] (등록 대장) · history_fn(sid, account)→`/histories`
    - record_fn(sid, **fields) → 결과 되쓰기(상태·분류·처방·조회시각). 없으면 기록 생략.
    - notify_fn(alert:str, rows:list) → 알림 1건(반려가 **있을 때만**). 실패해도 감시는 성공(정직 표기).
    - time_budget_sec > 0이면 항목마다 경과를 확인해 초과 시 중단([[동기 대량 라우트 타임아웃 지뢰]]).
    반환 = scan 결과 + {recorded, notified, budget_exhausted, remaining_hint}.
    """
    import time as _t
    clock = monotonic_fn or _t.monotonic
    start = clock()
    try:
        items = list(queue_fn(limit) or [])
    except Exception as exc:                               # 큐 조회 실패 = '대상 없음'과 구분(정직)
        return {"ok": False, "error": f"감시 큐 조회 실패: {exc}", "scanned": 0,
                "rows": [], "by_kind": {}, "by_prescription": {}, "recorded": 0, "notified": False}
    if not items:
        # '없음 확인' ≠ '조회 실패' — 정상 종료를 그렇게 표기한다.
        return {"ok": True, "scanned": 0, "rows": [], "by_kind": {}, "by_prescription": {},
                "alert": "감시 대상 없음(등록 대장에 미확정 건 없음)", "needs_manual": 0,
                "recorded": 0, "notified": False, "budget_exhausted": False}

    budget_exhausted, done = False, []
    for it in items:
        if time_budget_sec and (clock() - start) >= float(time_budget_sec):
            budget_exhausted = True
            break
        done.append(it)
    scan = scan_rejections(done, history_fn=history_fn, classify_fn=classify_fn)

    recorded = 0
    if record_fn:
        for r in scan["rows"]:
            # 조회 실패 행은 상태를 바꾸지 않는다(미상 유지) — 확인 실패를 '확인함'으로 만들지 않는다.
            status = "" if r.get("error") else ("rejected" if r.get("comment") else "unknown")
            try:
                if record_fn(r["sid"], status=status, reject_kind=r.get("kind", ""),
                             reject_comment=r.get("comment", ""),
                             prescription=r.get("prescription", "")):
                    recorded += 1
            except Exception:
                pass                                       # 기록 실패는 감시 자체를 죽이지 않음(집계에 미포함)

    notified, notify_error = False, ""
    has_rejection = any(r.get("comment") and not r.get("error") for r in scan["rows"])
    if notify_fn and has_rejection:                        # 반려가 있을 때만 알린다(잡음 0)
        try:
            notify_fn(scan["alert"], scan["rows"])
            notified = True
        except Exception as exc:
            notify_error = f"알림 발송 실패: {exc}"        # 감시는 성공, 알림만 실패(정직 분리)
    return {**scan, "ok": True, "recorded": recorded, "notified": notified,
            "notify_error": notify_error, "budget_exhausted": budget_exhausted,
            "remaining_hint": max(0, len(items) - len(done)),
            "elapsed_sec": round(clock() - start, 2)}


def apply_prescription(row, *, reupload_fn=None, delete_fn=None, reissue_fn=None,
                       approved: bool = False) -> dict:
    """처방 실행 — **배선하되 오너 승인 게이트 뒤**(비가역). approved=False면 실행 0(보류 사유).

    - image_spec→reupload_fn(sid) · trademark→delete_fn(sid) · option_value→reupload_fn(sid,대체값)
    - apple_category: apple_target=android면 reissue_fn(재등록 가능), apple/unknown이면 **보류**(실행 안 함).
    - unknown→항상 보류(오너 확인). 실행 결과는 정직 반환(가짜 성공 0).
    """
    sid = str((row or {}).get("sid") or "")
    kind = (row or {}).get("kind") or "unknown"
    rx = REJECTION_KINDS.get(kind, REJECTION_KINDS["unknown"])
    base = {"sid": sid, "kind": kind, "prescription": rx["rx"], "prescription_ko": rx["rx_ko"]}
    if not approved:
        return {**base, "applied": False, "reason": "오너 승인 게이트 — 실행 보류(비가역)"}
    # 애플: 삼성/픽셀용만 재등록, iPhone/미상은 보류.
    if kind == "apple_category":
        if (row or {}).get("apple_target") != "android":
            return {**base, "applied": False, "reason": "iPhone/애플 대상 — 표기 보류(재등록 안 함)"}
        if not reissue_fn:
            return {**base, "applied": False, "reason": "재등록 핸들러 미주입"}
        try:
            res = reissue_fn(sid)
            return {**base, "applied": True, "action": "reissue", "result": res}
        except Exception as exc:
            return {**base, "applied": False, "reason": f"재등록 실패: {exc}"}
    if kind == "image_spec" or kind == "option_value":
        if not reupload_fn:
            return {**base, "applied": False, "reason": "재등록 핸들러 미주입"}
        try:
            res = reupload_fn(sid, row)
            return {**base, "applied": True, "action": "reupload", "result": res}
        except Exception as exc:
            return {**base, "applied": False, "reason": f"재등록 실패: {exc}"}
    if kind == "trademark":
        if not delete_fn:
            return {**base, "applied": False, "reason": "삭제 핸들러 미주입"}
        try:
            res = delete_fn(sid)
            return {**base, "applied": True, "action": "delete", "result": res}
        except Exception as exc:
            return {**base, "applied": False, "reason": f"삭제 실패: {exc}"}
    return {**base, "applied": False, "reason": "미분류 — 오너 확인(자동 실행 금지)"}
