"""src/pipeline/reject_watch.py — 등록 파이프 P4: 쿠팡 반려감시 서버화 (rej_watch·watch_* 이식).

Bluehost `rej_watch.py`(2h 크론) → 콘솔/크론 조회·분류·알림. **기존 반려 처리 표준 그대로**(새 분류 발명 0):
  - 반려 사유 = `/histories`의 **comment** (상태 문구 "담당자 검토 결과 반려"가 아님 — [[반려 사유 요약 오독 지뢰]]).
  - 반려 3유형 → 처방: 이미지 규격→**재등록** / 담당자검토=상표권→**삭제 권고** / 옵션값→**값 대체**.
  - 애플 카테고리 사전승인 반려(TORRAS 전례) → **iPhone 표기 보류 · 삼성/픽셀용 유효** 분류.
감시 = **조회·분류·알림까지**. 자동 재등록/삭제는 **배선하되 실행은 오너 승인 게이트 뒤**(비가역).
전부 주입 가능(history_fn/apply_fn)해 오프라인 계약 검증(쿠팡 자격·네트워크 없이).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── 반려 유형 · 처방 (기존 표준 — 새 체계 발명 금지) ──────────────────────────────
REJECTION_KINDS = {
    # ① 반려 1호 실데이터(2026-08-25 Fellow Stagg): "대표이미지는 최대 10M, 최소 500*500, 최대 5000*5000".
    #    처방 = 대형본 치환(_SS1600_) + 실치수 심사 후 **이미지 교체 재제출**(PUT 수정 → PUT approvals).
    "image_spec":     {"ko": "이미지 규격",            "rx": "reupload",
                       "rx_ko": "이미지 재수집·교체 후 재제출"},
    "trademark":      {"ko": "상표권(담당자 검토)",     "rx": "delete",         "rx_ko": "삭제 권고"},
    # P5 — '값 대체'는 뭉뚱그린 처방이었다. 실제 거부는 **단위**와 **허용값**이 갈린다:
    #   "유효하지 않은 구매 옵션 값 혹은 단위" — 쿠팡 문구 자체가 둘을 한 줄에 담는다.
    #   단위 계열은 메타 basicUnit 결합(#690 P2), 값 계열은 허용 목록 게이트(#690 P3)로 처방이 다르다.
    "option_unit":    {"ko": "옵션 단위",              "rx": "attach_unit",
                       "rx_ko": "메타 basicUnit 결합 후 재전송"},
    "option_value":   {"ko": "옵션값",                "rx": "replace_option", "rx_ko": "허용값으로 대체"},
    "apple_category": {"ko": "애플 카테고리 사전승인 반려", "rx": "hold_or_reissue",
                       "rx_ko": "iPhone 표기 보류 · 삼성/픽셀용 유효"},
    # F' — 임시저장인데 **승인요청이 안 걸린** 건. 여태 사유 텍스트가 없어 '미분류'에 섞였고,
    #   그러면 처방이 "오너 확인 필요"가 돼 방치된다. 실제로 필요한 건 재등록이 **아니라**
    #   승인요청 PUT 한 방이다 — 재등록하면 같은 상품이 두 건 뜬다([[동일상품 다중등록 정리]]).
    "saved_pending":  {"ko": "임시저장(승인요청 누락)", "rx": "request_approval",
                       "rx_ko": "승인 재요청(PUT approvals) — 재등록 아님"},
    "unknown":        {"ko": "미분류",                "rx": "manual",         "rx_ko": "오너 확인 필요"},
}

# ── Wing 계기판 상태 유형(오너 실측 2026-08-25: 반려 38 · 임시저장 60 · 브랜드수정 2,061 · 증빙 1) ──
#   감시 대상 스키마. 각 유형이 **무엇을 요구하는지**와 **자동 조치 가능 여부**를 명시한다.
#   ※ 브랜드수정 2,061은 오너 지시로 **분류·집계만**(조치 배선 0 — 별도 트랙).
WING_STATES = {
    "rejected":    {"ko": "반려", "actionable": True,
                    "desc": "심사 반려 — 사유(comment) 분류 후 수정·재승인"},
    "saved":       {"ko": "임시저장", "actionable": True,
                    "desc": "SAVED 상태 — 승인요청 미제출이거나 반려로 내려온 건"},
    "brand_fix":   {"ko": "브랜드 수정요청", "actionable": False,
                    "desc": "브랜드 정보 수정 요청 — 분류·집계만(조치는 별도 트랙)"},
    "doc_required": {"ko": "증빙 필요", "actionable": False,
                     "desc": "서류 증빙 요구 — 오너 제출 필요(자동 조치 불가)"},
    "approved":    {"ko": "승인", "actionable": False, "desc": "심사 통과"},
    # A1(오너 WING 실측 2026-09-07 '판매중'): 사전에 없어 **최신 상태를 읽을 눈이 없었다.**
    #   selling → approved 경로: 노출·판매 중이면 심사는 끝난 것이다(계기판에서 '판매중'이 종착).
    #   pending  → 미확정 경로: **제출은 결과가 아니다.** 승인요청/심사중은 아직 답이 안 온 상태라
    #     큐에 남아야 하고, 여기서 approved로 세면 [[등록 파이프 이식]]의 그 과탐이 재현된다
    #     ('승인'을 넓게 잡아 승인요청이 승인으로 둔갑 → 우선순위 신호가 통째로 죽었던 건).
    "selling":     {"ko": "판매중", "actionable": False, "desc": "노출·판매 중 — 심사 종료(승인 경로)"},
    "pending":     {"ko": "심사중", "actionable": False,
                    "desc": "승인요청 접수/심사중 — 아직 확정 아님(큐에 남는다)"},
    "unknown":     {"ko": "미상", "actionable": False, "desc": "상태 조회 실패/미확인"},
}

# comment 키워드 규칙(사유 텍스트 기준 — 상태 문구 아님). 우선순위: 애플>상표권>옵션>이미지.
_APPLE_RE = re.compile(r"애플|apple|아이폰|iphone|아이패드|ipad|맥북|macbook|에어팟|airpod|casetify|mfi|사전\s*승인", re.I)
_TRADEMARK_RE = re.compile(r"상표|브랜드\s*권|권리\s*침해|지식\s*재산|정품|위조|라이선스|licen[sc]e|가품|병행\s*수입\s*불가", re.I)
_OPTION_RE = re.compile(r"옵션\s*값|구매\s*옵션|옵션\s*정보|옵션\s*누락|사이즈\s*표기|색상\s*표기|단위\s*수량", re.I)
# P5 — 옵션 계열 안에서 **단위**를 따로 집는다. 처방이 다르기 때문이다(단위 결합 vs 허용값 대체).
#   쿠팡 실문구 "유효하지 않은 구매 옵션 값 **혹은 단위** 입니다."가 이 분기의 근거다.
_OPTION_UNIT_RE = re.compile(r"단위", re.I)
# F' — 임시저장. 사유 텍스트가 아니라 **상태**지만, 이 상태 자체가 처방을 정한다(승인요청 누락).
_SAVED_RE = re.compile(r"임시\s*저장|\bSAVED\b", re.I)
_IMAGE_RE = re.compile(r"이미지|사진|대표\s*이미지|화질|해상도|규격|누끼|워터마크|배경\s*처리|픽셀|"
                       r"\d{3,4}\s*\*\s*\d{3,4}|DETAIL", re.I)   # 실데이터: "최소 500*500 … 기타이미지(DETAIL)"

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
        # F' — 사유가 없어도 상태가 **임시저장**이면 처방이 정해진다: 승인요청이 안 걸린 것이다.
        #   (재등록이 아니라 승인요청 PUT — 재등록은 동일상품 다중등록을 낳는다.)
        ms = _SAVED_RE.search(f"{c} {title}")
        if ms:
            return _mk("saved_pending", matched=ms.group(0))
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
        # 사유에 '단위'가 있으면 단위 처방 — 없으면 값 처방(둘 다면 단위가 먼저·결합이 선행 조치).
        mu = _OPTION_UNIT_RE.search(text)
        if mu:
            return _mk("option_unit", matched=mu.group(0))
        return _mk("option_value", matched=m.group(0))
    m = _IMAGE_RE.search(text)
    if m:
        return _mk("image_spec", matched=m.group(0))
    ms = _SAVED_RE.search(text)
    if ms:
        # 구체 사유가 하나도 없고 상태만 임시저장 — 승인요청 누락(위 분기와 같은 처방).
        return _mk("saved_pending", matched=ms.group(0))
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


# ★ 순서가 규칙이다: 위에서부터 먼저 맞는 것이 이긴다.
#   `pending`이 `approved`보다 **위**에 있어야 '승인요청'이 '승인'으로 둔갑하지 않는다
#   ([[등록 파이프 이식]] 과탐 함정: 넓게 잡은 승인 신호 하나가 분류를 통째로 무너뜨렸다).
_WING_STATE_RE = (
    ("rejected", re.compile(r"반려|REJECT", re.I)),
    ("brand_fix", re.compile(r"브랜드.*(수정|변경|요청)|brand.*(fix|modif)", re.I)),
    ("doc_required", re.compile(r"증빙|서류|첨부.*요청|documents?\s*requir", re.I)),
    ("pending", re.compile(r"승인\s*요청|심사\s*중|검수\s*중|승인\s*대기|"
                           r"REQUEST(ED)?_?APPROV|IN_?REVIEW|PENDING", re.I)),
    ("selling", re.compile(r"판매\s*중|판매\s*재개|ON_?SALE|SELLING", re.I)),
    ("approved", re.compile(r"승인(완료)?$|APPROV", re.I)),
    ("saved", re.compile(r"임시\s*저장|SAVED", re.I)),
)

# 확정 상태 = 그 이상 안 바뀌는 결론. 미확정(pending/saved/unknown)은 큐에 남는다.
_SETTLED_STATES = ("rejected", "brand_fix", "doc_required", "selling", "approved")

# 시각 키 후보 — Wing 응답 키 이름이 실측으로 확정되지 않았다. **있는 것만 쓰고 없으면 안 쓴다**(발명 0).
_AT_KEYS = ("createdAt", "created_at", "changeDate", "changedAt", "regDate", "registeredAt",
            "updatedAt", "date", "createdDate", "statusDate")


def _row_at(row) -> str:
    """이력 행의 시각 문자열. **없으면 빈 문자열**(발명 0) — 키 이름이 실측 확정 전이라 후보를 훑는다."""
    for k in _AT_KEYS:
        v = (row or {}).get(k)
        if v:
            return str(v)
    return ""


def timeline(history, *, limit: int = 12) -> list:
    """이력 응답 → **사람이 읽는 줄글 재료** `[{at, status, comment}]`(6-h-3 N1).

    화면 접힘에 JSON 원문을 그대로 붓던 자리를 대체한다 — 셀러가 알고 싶은 건 응답 스키마가 아니라
    **쿠팡이 뭐라고 했는지**다. 그래서 이력에 **실제로 있는 것만** 옮긴다:
    시각·상태 문구·comment 원문. 없는 값은 빈 문자열이고, 지어내지 않는다.

    정렬은 `wing_state`와 같은 규칙 — 시각이 있으면 시각순, 없으면 응답 순서(가정 노출 0).
    """
    rows = _history_rows(history)
    out = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        st = str(r.get("statusName") or r.get("status") or r.get("changeStatus") or "").strip()
        cm = str(r.get("comment") or r.get("reason") or r.get("memo") or "").strip()
        if not st and not cm:
            continue                                   # 아무 말도 없는 행은 줄글에 쓸 게 없다
        out.append({"at": _row_at(r), "status": st, "comment": cm, "_i": i})
    if any(e["at"] for e in out):
        out.sort(key=lambda e: (e["at"] or "", e["_i"]))
    for e in out:
        e.pop("_i", None)
    return out[-max(1, int(limit)):] if out else []


def log_history_shape(sid, history, *, logger_=None) -> dict:
    """★ A1 계측 — 이력 응답의 **첫 행·끝 행 원문**(시각 포함)을 INFO로 한 줄 남긴다.

    정렬 방향(최신이 앞이냐 뒤냐)이 아직 실측된 적이 없다. 다음 크론 로그로 확정한 뒤
    그 근거를 계약에 명기한다 — 그때까지 판정은 시각 정렬로 가정을 피해 간다.
    개인정보·자격은 안 싣는다(상태 문구·시각·행 수만).
    """
    rows = _history_rows(history)
    def _brief(r):
        if not isinstance(r, dict):
            return {}
        return {"at": _row_at(r),
                "status": str(r.get("statusName") or r.get("status") or r.get("changeStatus") or "")[:40],
                "keys": sorted(r.keys())[:8]}
    shape = {"sid": sid, "n": len(rows),
             "first": _brief(rows[0]) if rows else {}, "last": _brief(rows[-1]) if rows else {}}
    # 접두어를 크론 결말 줄과 **같은 말**로 맞춘다 — 오너가 「반려감시 상태」 하나로 검색하면
    #   그 회전의 결말과 이 원문이 **같은 검색 결과에** 나온다(회수 검색어 통일, 오너 2026-09-07).
    (logger_ or logger).info("반려감시 상태·이력 원문(sid=%s): 행 %s · 첫 %s · 끝 %s",
                             shape["sid"], shape["n"], shape["first"], shape["last"])
    return shape


def wing_state(history) -> str:
    """`/histories` 최신 행 → Wing 계기판 상태 유형. 판정 불가면 'unknown'(가짜 확정 0).

    오너 실측 계기판 분류(반려·임시저장·브랜드수정·증빙)를 그대로 쓴다 — 새 체계 발명 0.
    반려가 섞여 있으면 반려 우선(조치 대상이라 놓치면 안 된다).
    """
    body = history
    if isinstance(history, (tuple, list)) and len(history) == 2 and not isinstance(history[0], dict):
        body = history[1]
    if isinstance(body, dict):
        rows = body.get("data") or body.get("histories") or body.get("content") or []
    elif isinstance(body, (list, tuple)):
        rows = list(body)
    else:
        rows = []
    picked = []                              # [(정렬키, 원래 index, 상태)]
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        st = str(r.get("statusName") or r.get("status") or r.get("changeStatus") or "")
        for key, rx in _WING_STATE_RE:
            if rx.search(st):
                picked.append((_row_at(r), i, key))
                break
    if not picked:
        return "unknown"
    # ★ A1: **정렬 가정을 없앤다.** 예전엔 `states[-1]`로 "마지막 = 최신"을 가정했는데
    #   응답이 최신 우선이면 그건 가장 오래된 행이다(가정은 실측된 적이 없었다).
    #   시각이 있으면 **시각으로 정렬**하고, 시각이 하나도 없을 때만 순서를 쓴다(그 사실도 로그가 남긴다).
    if any(at for at, _i, _k in picked):
        picked.sort(key=lambda t: (t[0] or "", t[1]))
    latest = picked[-1][2]
    # ★ A1: `rejected` 절대우선 폐지. 과거 반려 한 줄이 **최신 확정 상태를 영원히 덮고 있었다**
    #   (재제출로 판매중이 돼도 우리 눈엔 계속 반려 — 오너 WING 실측 2026-09-07이 그걸 잡았다).
    #   최신이 확정이면 최신을 믿는다. 최신이 미확정(pending/saved)이면, 그 앞의 **확정**을 본다 —
    #   심사중이라고 해서 직전 반려 사실이 사라지는 건 아니기 때문이다.
    if latest in _SETTLED_STATES:
        return latest
    for _at, _i, key in reversed(picked):
        if key in _SETTLED_STATES:
            return key
    return latest


# 판매 상태 문구 — '판매중/승인'이 반려보다 **앞선 이력**에 있으면 사후 재심사로 내려온 건이다.
# ⚠ **넓게 잡으면 안 된다**: 바 '승인'은 `승인요청`(제출)에도 걸려 신규 반려가 전부 '판매중→반려'로
#   둔갑한다(실측으로 잡음). 판매/승인 **완료**를 뜻하는 문구만 인정한다.
_SELLING_RE = re.compile(r"판매\s*중|판매\s*재개|승인\s*완료|PARTIAL_APPROVED|\bAPPROVED\b|ON_?SALE", re.I)
_REJECT_ROW_RE = re.compile(r"반려|REJECT", re.I)


def _history_rows(history) -> list:
    """`/histories` 응답(튜플·딕트·리스트) → 행 리스트. 세 형태 모두 안전([[ship_real get 튜플 반환]])."""
    body = history
    if isinstance(history, (tuple, list)) and len(history) == 2 and not isinstance(history[0], dict):
        body = history[1]
    if isinstance(body, dict):
        rows = body.get("data") or body.get("histories") or body.get("content") or []
    elif isinstance(body, (list, tuple)):
        rows = list(body)
    else:
        rows = []
    return [r for r in rows if isinstance(r, dict)]


def was_selling(history) -> bool:
    """**판매중이던 상품이 반려로 내려왔는가**(사후 재심사). 판정 불가면 False(가짜 확정 0).

    미분류 1호(16359486080)가 이 계열이다 — 신규 등록 반려와 성질이 다르다:
    이미 노출·판매되던 상품이 내려간 것이라 **매출이 즉시 멈춘다**. 우선순위가 높다.

    판정: 최신 반려 행보다 **앞선** 행에 판매중/승인 문구가 있으면 True.
    이력은 시간 오름차순 가정(쿠팡 `/histories` 관례) — 반려가 없으면 전환도 아니다.
    """
    rows = _history_rows(history)
    last_reject = -1
    for i, r in enumerate(rows):
        st = str(r.get("statusName") or r.get("status") or r.get("changeStatus") or "")
        if _REJECT_ROW_RE.search(st):
            last_reject = i
    if last_reject <= 0:
        return False                                  # 반려 없음, 또는 첫 행부터 반려(=신규 반려)
    for r in rows[:last_reject]:
        st = str(r.get("statusName") or r.get("status") or r.get("changeStatus") or "")
        if _REJECT_ROW_RE.search(st):
            continue                                  # 반려 행은 판매 상태가 아니다
        if _SELLING_RE.search(st):
            return True
    return False


def state_summary(rows) -> dict:
    """상태 유형별 집계 — Wing 계기판과 같은 축으로 본다. 조치 가능/불가를 나눠 표기(정직)."""
    by_state, actionable, info_only = {}, 0, 0
    for r in (rows or []):
        s = (r or {}).get("wing_state") or "unknown"
        by_state[s] = by_state.get(s, 0) + 1
        if WING_STATES.get(s, {}).get("actionable"):
            actionable += 1
        else:
            info_only += 1
    return {"by_state": by_state, "actionable": actionable, "info_only": info_only,
            "labels": {k: v["ko"] for k, v in WING_STATES.items()}}


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
            hist = history_fn(sid, account)
            if not rows:                       # A1 계측 — 회전당 **한 줄만**(50건이면 50줄이 된다)
                try:
                    log_history_shape(sid, hist)
                except Exception:              # 계측이 감시를 죽이지 않는다
                    pass
            comment = latest_rejection_comment(hist)
            state = wing_state(hist)
            selling_before = was_selling(hist)
        except Exception as exc:                           # 조회 실패 = 정직(미분류·사유에 기록), 다음 계속
            cl = classify_rejection("", title=title)
            rows.append({"sid": sid, "title": title, "account": account, "comment": "",
                         "wing_state": "unknown", "wing_state_ko": WING_STATES["unknown"]["ko"],
                         "error": f"histories 조회 실패: {exc}", **cl})
            by_kind["unknown"] = by_kind.get("unknown", 0) + 1
            continue
        cl = classify_fn(comment, title=title)
        row = {"sid": sid, "title": title, "account": account, "comment": comment,
               # N1: 접힘에 넣을 **쿠팡이 한 말**(시각·상태·원문). JSON 원문 대체 재료다.
               "timeline": timeline(hist),
               "wing_state": state, "wing_state_ko": WING_STATES.get(state, {}).get("ko", state),
               "actionable": bool(WING_STATES.get(state, {}).get("actionable")),
               # 사후 재심사 — 팔리던 상품이 내려간 건(매출 즉시 중단). 신규 반려와 구분해 표기한다.
               "was_selling": selling_before, "priority": "high" if selling_before else "normal", **cl}
        rows.append(row)
        by_kind[cl["kind"]] = by_kind.get(cl["kind"], 0) + 1
        by_rx[cl["prescription"]] = by_rx.get(cl["prescription"], 0) + 1
    # 같은 유형(오너 지목 확장): 집계도 kind(comment) 기준이라 **확정 상태를 안 봤다.**
    #   그래서 판매중이 된 건이 "반려 3건 … 임시저장 1"에 섞여 들어갔다(오너 실측 캡처).
    #   심사가 끝난 건은 반려 수에서 빼고 따로 센다 — 숫자가 거짓이면 화면 전체가 거짓이 된다.
    settled_ok = [r for r in rows if r.get("wing_state") in ("approved", "selling")]
    open_rows = [r for r in rows if r.get("wing_state") not in ("approved", "selling")]
    # 상태가 이미 분류인 건(브랜드수정·증빙)은 **'미분류'가 아니다.** 화면 뱃지와 같은 규칙을 요약에도
    #   건다 — 안 그러면 "미분류 1 · 미분류 1건(오너 확인)"처럼 같은 행을 두 번 다르게 부른다(실측).
    _state_named = ("brand_fix", "doc_required")
    needs_manual = [r for r in open_rows
                    if r["kind"] == "unknown" and r.get("wing_state") not in _state_named]
    resale = [r for r in open_rows if r.get("was_selling")]
    open_kinds = {}
    for r in open_rows:
        st = r.get("wing_state")
        label = WING_STATES[st]["ko"] if st in _state_named else REJECTION_KINDS[r["kind"]]["ko"]
        open_kinds[label] = open_kinds.get(label, 0) + 1
    parts = [f"{k} {n}" for k, n in sorted(open_kinds.items(), key=lambda x: -x[1])]
    alert = f"반려 {len(open_rows)}건 — " + (" · ".join(parts) if parts else "없음")
    if settled_ok:
        # 끝난 건은 **좋은 소식**이라 앞에 세운다(숨기면 "왜 안 보이지"가 된다).
        _ko = WING_STATES.get(settled_ok[0].get("wing_state"), {}).get("ko", "승인")
        alert = f"{_ko} {len(settled_ok)}건 · " + alert
    if resale:
        # 팔리던 상품이 내려간 건은 **맨 앞에** 세운다(매출이 즉시 멈추므로 우선순위가 높다).
        alert = f"⚠ 판매중→반려 {len(resale)}건(우선) · " + alert
    if needs_manual:
        alert += f" · 미분류 {len(needs_manual)}건(오너 확인)"
    return {"rows": rows, "by_kind": by_kind, "by_prescription": by_rx,
            "alert": alert, "needs_manual": len(needs_manual), "scanned": len(rows),
            "resale_rejections": len(resale), **state_summary(rows)}


# W5 — 폴링 큐 졸업 대상. **대장 행은 유지하고 재조회만 중단**한다(기록 삭제 아님).
#   `unknown`도 actionable=False지만 여기 없다 — '미상'은 아직 아무것도 확정 안 된 상태라
#   큐에 남아야 한다. 졸업은 "확정됐다"는 뜻이지 "조치 안 한다"는 뜻이 아니다.
# A1: `selling`(판매중) 추가 — 노출·판매 중이면 심사는 끝났다. 확정인데 큐에 남겨 두면
#   2시간마다 영원히 다시 물어보게 된다(그게 이 트랙이 없애려던 낭비다).
GRADUATING_STATES = ("approved", "selling", "brand_fix", "doc_required")


# 감시 큐에 **남아야 하는** Wing 상태 — 아직 확정이 아닌 것들.
#   `saved`(임시저장)는 조치 대상이지 확정이 아니다: 승인요청을 다시 걸면 결과가 또 나온다.
#   `unknown`(미상)은 아무것도 확인 못 한 상태다.
#   둘 다 큐에 남아야 다음 회전이 결과를 본다.
UNSETTLED_STATES = ("saved", "unknown")


def _next_status(row) -> str:
    """감시 결과 → 대장에 쓸 상태. **dry-run과 실행이 같은 함수를 쓴다** —
    세는 쪽과 쓰는 쪽이 갈리면 미리 본 숫자가 거짓이 된다.

    ★ 폴백 수리(2026-09-05): 전에는 `comment` 유무만 보고 `rejected`를 앉혔다.
      `latest_rejection_comment`에는 '조용한 누락 방지' 폴백이 있어 **반려 표기가 없어도
      마지막 메모를 돌려준다.** 그래서 심사중 메모 한 줄이 상품을 `rejected`로 만들고
      감시 큐 밖으로 밀어냈다([[임시저장 comment가 반려로 앉는다]]).

      **`wing_state`가 확정값이면 그걸 믿는다.** comment는 *무엇이 문제인가*(kind)를
      정하는 재료지 *확정인가*(status)를 정하는 근거가 아니다 —
      '사유가 있다'와 '반려다'는 다른 명제다.
    """
    state = str((row or {}).get("wing_state") or "")
    if (row or {}).get("error"):
        return ""            # 조회 실패는 상태를 안 바꾼다 — 확인 실패를 '확인함'으로 만들지 않는다
    if state in GRADUATING_STATES:
        return state         # approved·brand_fix·doc_required — 확정이라 큐를 떠난다
    if state == "rejected":
        return "rejected"    # Wing이 반려라고 말했을 때만 반려다
    if state in UNSETTLED_STATES:
        return state if state == "unknown" else "saved"   # 미확정 — 큐에 남는다
    # 여기 오는 건 WING_STATES에 없는 새 상태. 확정으로 단정하지 않는다(가짜 확정 0).
    return "unknown"


def watch_registered(*, queue_fn, history_fn, classify_fn=None, record_fn=None,
                     notify_fn=None, limit: int = 50, time_budget_sec: float = 0,
                     monotonic_fn=None, dry_run: bool = False) -> dict:
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

    # W5 dry-run — 무엇이 얼마나 바뀌는지 **쓰기 전에** 센다(2천 건 일괄 변경 앞이라 필수).
    would = {}
    for r in scan["rows"]:
        st = _next_status(r)
        if st:
            would[st] = would.get(st, 0) + 1
    scan["would_change"] = would
    scan["would_graduate"] = sum(n for s, n in would.items() if s in GRADUATING_STATES)
    if dry_run:
        return {**scan, "ok": True, "dry_run": True, "recorded": 0, "notified": False,
                "budget_exhausted": budget_exhausted,
                "remaining_hint": max(0, len(items) - len(done)),
                "elapsed_sec": round(clock() - start, 2)}

    recorded = 0
    wrote: dict = {}                          # 실제로 쓴 상태 분포 — 로그가 졸업/잔류를 말하게
    if record_fn:
        for r in scan["rows"]:
            status = _next_status(r)          # dry-run이 센 것과 **같은 판정**(둘이 갈리면 예고가 거짓)
            if status:
                wrote[status] = wrote.get(status, 0) + 1
            try:
                if record_fn(r["sid"], status=status, reject_kind=r.get("kind", ""),
                             reject_comment=r.get("comment", ""),
                             prescription=r.get("prescription", "")):
                    recorded += 1
            except Exception:
                pass                                       # 기록 실패는 감시 자체를 죽이지 않음(집계에 미포함)

    notified, notify_error = False, ""
    # 졸업하는 건의 옛 comment는 **지금 문제가 아니다** — 판매중이 된 건을 두고
    #   "반려 1건"을 덧붙이면 해결된 일을 미해결로 읽히게 만든다(가짜 경보 0).
    has_rejection = any(r.get("comment") and not r.get("error")
                       and r.get("wing_state") not in ("selling", "approved")
                       for r in scan["rows"])
    # A1: **승인 방향 전환도 알린다.** 지금까지는 반려가 있을 때만 알려서, 문제가 풀린 소식은
    #   영영 오지 않았다(감시의 절반만 쓰고 있었다). 졸업하는 건이라 **한 번만** 뜬다 —
    #   다음 회전엔 큐에 없어서 다시 알릴 수도 없다(잡음 0은 그대로).
    became = [r for r in scan["rows"] if r.get("wing_state") in ("selling", "approved")]
    alert = scan["alert"]
    if became:
        _ko = WING_STATES.get(became[0].get("wing_state"), {}).get("ko", "승인")
        # 남은 반려 수는 **졸업분을 빼고** 센다. `scan["alert"]`를 그대로 이어 붙이면
        #   방금 판매중이 된 건까지 '반려 N건'에 포함돼 숫자가 거짓이 된다(가짜 수치 0).
        _left = [r for r in scan["rows"]
                 if r.get("comment") and not r.get("error")
                 and r.get("wing_state") not in ("selling", "approved")]
        alert = (f"✅ {_ko} 전환 {len(became)}건 — "
                 + " · ".join(str(r.get("sid")) for r in became[:5])
                 + (f" 외 {len(became) - 5}건" if len(became) > 5 else "")
                 + (f" · 남은 반려 {len(_left)}건" if _left else ""))
    if notify_fn and (has_rejection or became):
        try:
            notify_fn(alert, scan["rows"])
            notified = True
        except Exception as exc:
            notify_error = f"알림 발송 실패: {exc}"        # 감시는 성공, 알림만 실패(정직 분리)
    from src.db.market_registrations_pg import _WATCH_STATUSES as _WS
    return {**scan, "ok": True, "recorded": recorded, "notified": notified,
            "wrote": wrote,
            "stayed": sum(n for st, n in wrote.items() if st in _WS),
            "graduated": sum(n for st, n in wrote.items() if st not in _WS),
            "notify_error": notify_error, "budget_exhausted": budget_exhausted,
            "remaining_hint": max(0, len(items) - len(done)),
            "elapsed_sec": round(clock() - start, 2)}


def _rearm(sid, rearm_fn, out: dict) -> dict:
    """재무장 — **다시 요청했으면 결과는 다시 미확정이다.**

    ★ R2 부검(2026-09-05): 처방을 실행해도 대장 status가 그대로라 감시 사슬이 끊겼다.
      승인요청은 `{success:true}`만 돌려주고 대장을 안 건드린다. 그래서 이미 큐를 떠난 행
      (예: `rejected`)에 처방을 걸면 **다시 요청해 놓고도 아무도 결과를 안 본다** —
      실행할수록 블랙박스가 되는 구조였다.

    성공했을 때만 `submitted`로 되돌린다. 실패는 상태를 건드리지 않는다
    (실패를 '다시 심사 중'으로 만들면 그거야말로 가짜 수치다).
    """
    if not rearm_fn:
        return out
    try:
        out["rearmed"] = bool(rearm_fn(sid))
    except Exception as exc:                          # 재무장 실패가 처방 성공을 덮지 않는다
        out["rearmed"] = False
        out["rearm_error"] = str(exc)
    return out


def apply_prescription(row, *, reupload_fn=None, delete_fn=None, reissue_fn=None,
                       resubmit_fn=None, approve_fn=None, rearm_fn=None,
                       approved: bool = False) -> dict:
    """처방 실행 — **배선하되 오너 승인 게이트 뒤**(비가역). approved=False면 실행 0(보류 사유).

    - image_spec→reupload_fn(sid) · trademark→delete_fn(sid) · option_value→reupload_fn(sid,대체값)
    - saved_pending→approve_fn(sid): **승인요청 PUT 한 방**. 재등록이 아니다 — 상품을 다시 만들면
      같은 상품이 두 건 뜬다([[동일상품 다중등록 정리]]). 수정할 값이 없으니 PUT approvals만 건다.
    - apple_category: apple_target=android면 reissue_fn(재등록 가능), apple/unknown이면 **보류**(실행 안 함).
    - unknown→항상 보류(오너 확인). 실행 결과는 정직 반환(가짜 성공 0).
    """
    sid = str((row or {}).get("sid") or "")
    kind = (row or {}).get("kind") or "unknown"
    rx = REJECTION_KINDS.get(kind, REJECTION_KINDS["unknown"])
    base = {"sid": sid, "kind": kind, "prescription": rx["rx"], "prescription_ko": rx["rx_ko"]}
    if not approved:
        return {**base, "applied": False, "reason": "오너 승인 게이트 — 실행 보류(비가역)"}
    # Wing 상태가 **자동 조치 불가 유형**(브랜드 수정요청·증빙 필요)이면 실행하지 않는다(오너 지시).
    state = (row or {}).get("wing_state")
    if state and not WING_STATES.get(state, {}).get("actionable", False) and state != "unknown":
        return {**base, "applied": False, "wing_state": state,
                "reason": (f"{WING_STATES[state]['ko']} — 자동 조치 대상 아님"
                           f"({WING_STATES[state]['desc']})")}
    # 애플: 삼성/픽셀용만 재등록, iPhone/미상은 보류.
    if kind == "apple_category":
        if (row or {}).get("apple_target") != "android":
            return {**base, "applied": False, "reason": "iPhone/애플 대상 — 표기 보류(재등록 안 함)"}
        if not reissue_fn:
            return {**base, "applied": False, "reason": "재등록 핸들러 미주입"}
        try:
            res = reissue_fn(sid)
            return _rearm(sid, rearm_fn, {**base, "applied": True, "action": "reissue", "result": res})
        except Exception as exc:
            return {**base, "applied": False, "reason": f"재등록 실패: {exc}"}
    if kind == "image_spec" or kind == "option_value":
        # 재승인 경로(정본): **수정(PUT) → 승인요청(PUT approvals)**. resubmit_fn이 두 단계를 담당.
        #   수정할 값이 없으면(row.updates 없음) 승인요청만 — 쿠팡 반려분은 SAVED로 내려오므로 재심사 진입이 필요.
        if resubmit_fn:
            try:
                # 분류를 함께 넘긴다 — 이미지 규격 반려는 **이미지 교체 없이 재제출 금지**(반려 2호 교훈).
                _upd = dict((row or {}).get("updates") or {})
                _upd["_kind"] = kind
                res = resubmit_fn(sid, _upd)
                ok = bool((res or {}).get("success")) if isinstance(res, dict) else bool(res)
                out = {**base, "applied": ok, "action": "resubmit", "result": res,
                       **({} if ok else {"reason": (res or {}).get("error", "재승인 실패")})}
                return _rearm(sid, rearm_fn, out) if ok else out
            except Exception as exc:
                return {**base, "applied": False, "reason": f"재승인 실패: {exc}"}
        if not reupload_fn:
            return {**base, "applied": False, "reason": "재등록/재승인 핸들러 미주입"}
        try:
            res = reupload_fn(sid, row)
            return _rearm(sid, rearm_fn, {**base, "applied": True, "action": "reupload", "result": res})
        except Exception as exc:
            return {**base, "applied": False, "reason": f"재등록 실패: {exc}"}
    if kind == "saved_pending":
        # F' — 승인요청만 다시 건다. 상품 수정도 재생성도 하지 않는다(비가역 최소 표면).
        if not approve_fn:
            return {**base, "applied": False, "reason": "승인요청 핸들러 미주입"}
        try:
            res = approve_fn(sid)
            ok = bool((res or {}).get("success")) if isinstance(res, dict) else bool(res)
            out = {**base, "applied": ok, "action": "request_approval", "result": res,
                   **({} if ok else {"reason": (res or {}).get("error", "승인요청 실패")})}
            return _rearm(sid, rearm_fn, out) if ok else out
        except Exception as exc:
            return {**base, "applied": False, "reason": f"승인요청 실패: {exc}"}
    if kind == "trademark":
        if not delete_fn:
            return {**base, "applied": False, "reason": "삭제 핸들러 미주입"}
        try:
            res = delete_fn(sid)
            return {**base, "applied": True, "action": "delete", "result": res}
        except Exception as exc:
            return {**base, "applied": False, "reason": f"삭제 실패: {exc}"}
    return {**base, "applied": False, "reason": "미분류 — 오너 확인(자동 실행 금지)"}
