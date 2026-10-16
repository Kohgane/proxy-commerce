"""src/services/image_translate_auto.py — D3-8: 수집 시 이미지 번역 **자동**(퍼센티 방식).

흐름: 중국 소싱처(타오바오·티몰·1688) 초안의 **상세 보강이 끝나면**(`/enrich`) 갤러리+상세 이미지를
장 단위로 큐에 넣는다 → 워커가 한 장씩 벤치 최신 파이프라인으로 번역 → 장별로 저장.

파이프라인 = 벤치 D3 최신: Tencent **박스+원문**(렌더본은 버림) → 용어집(옵션 값·관용구·브랜드 보존)
→ D3-5/6/7 렌더(telea) + gen_remove 한 번 더 → **F축(지운 자리 vs 주변 링)이 나은 쪽 자동 선택**.
글자가 없는 장은 원본을 쓴다(skipped — 실패 아님).

비용 가드(오너 2026-09-27):
  - 공급사 초당 1회 — `tc.translate_image`가 서버 전역 차례표(`rate_slot`)를 지난다(워커 여럿이어도 1).
  - **일일 상한** `IMAGE_TRANSLATE_DAILY_CAP`(기본 200) = **번역을 시작한 장 수**(실패·재시도 포함),
    **KST 자정**에 새로 센다. 닿으면 큐는 대기(보내지 않은 장은 queued로 되돌림) · 화면 「번역 대기 N장」.
  - **실패 누적 20장**(마지막 재개 이후)이면 큐 자동 일시정지 + 화면 경고 — 오너가 「재개」를 눌러야 계속.
  - Cloudinary gen_remove 크레딧 추정치는 장마다 로그(렌더가 내는 `cloud_credits` 그대로 — 지어내지 않음).
설정: 소싱처별 토글(기본 켬) — `app_state` 키 `imgko_auto:<user_id>`.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

ENV_CAP = "IMAGE_TRANSLATE_DAILY_CAP"
# Z3-2(오너 2026-10-04): 건당 상한 = 대표 1 + 갤러리 5(갤러리 0~5번) + 상세 10. 넘는 장은 원본 유지.
# Y9(오너 2026-10-13): 상세는 수집 즉시 전 장(「상세 사진 번역 중 n/28」) — 상한 `IMAGE_TRANSLATE_DETAIL_CAP`(기본 30).
#   주소만 봐도 뺄 장(스페이서·작은 아이콘)은 보내지 않는다(`detail_image_plan.url_exclusion`).
PER_ITEM_CAP = {"gallery": 6, "detail": 30, "sku": 30}   # Y11-U: 옵션(SKU) 사진 — 상품당 30장(일 상한에 포함)


def per_item_cap(kind: str) -> int:
    if kind == "detail":
        try:
            return max(0, int(os.getenv("IMAGE_TRANSLATE_DETAIL_CAP", str(PER_ITEM_CAP["detail"]))))
        except (TypeError, ValueError):
            return PER_ITEM_CAP["detail"]
    return PER_ITEM_CAP.get(kind, 6)


def d3_enabled() -> bool:
    """Y9: D3(박스+원문 → 우리가 지우고 그리기)는 `IMAGE_TRANSLATE_D3=1`일 때만. 기본은 텐센트 본선(갤러리와 같은 결과물)."""
    return os.getenv("IMAGE_TRANSLATE_D3", "0") == "1"
DEFAULT_CAP = 200
FAIL_PAUSE_AT = 20
SOURCES = ("taobao", "tmall", "1688")
_KST = timezone(timedelta(hours=9))
_STATE_KEY = "imgko_auto:global"
_CN_RE = re.compile(r"(^|\.)(taobao|tmall|1688)\.com$")

_WORKER = {"thread": None, "lock": threading.Lock()}


# ── 규칙 ──────────────────────────────────────────────────────────────────────

def daily_cap() -> int:
    try:
        return max(0, int(os.getenv(ENV_CAP, str(DEFAULT_CAP))))
    except (TypeError, ValueError):
        return DEFAULT_CAP


def kst_day(now=None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(_KST).strftime("%Y-%m-%d")


def _day_key(now=None) -> str:
    return "imgko_auto:day:" + kst_day(now)


def source_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        h = (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return ""
    m = _CN_RE.search(h)
    return m.group(2) if m else ""


def _q():
    from src.db import image_translate_queue_pg as q
    return q


def settings(user_id: str) -> dict:
    v = _q().state_get(f"imgko_auto:{user_id}")
    return {s: (v.get(s) is not False) for s in SOURCES}          # 기본 켬


def save_settings(user_id: str, toggles: dict) -> dict:
    cur = settings(user_id)
    for s in SOURCES:
        if s in (toggles or {}):
            cur[s] = bool(toggles[s])
    _q().state_set(f"imgko_auto:{user_id}", cur)
    return cur


def pause_state() -> dict:
    return _q().state_get(_STATE_KEY)


def _since_resume():
    st = pause_state()
    ts = st.get("resumed_at") or ""
    try:
        return datetime.fromisoformat(ts) if ts else datetime(1970, 1, 1, tzinfo=timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def pause(reason: str) -> None:
    st = pause_state()
    st.update({"paused": True, "reason": reason, "paused_at": datetime.now(timezone.utc).isoformat()})
    _q().state_set(_STATE_KEY, st)
    logger.warning("[이미지번역·자동] 큐 일시정지 — %s", reason)


def heal_breaker() -> dict:
    """Y4: 차단기가 「번역 실패 N장」으로 멈췄는데, 글자 없는 사진을 뺀 **진짜 실패**가 상한 아래면 풀고 다시 돈다.
    사람이 멈춘 것(다른 사유)은 건드리지 않는다. → `{healed, real_failed, reason}`"""
    st = pause_state()
    if not st.get("paused") or not str(st.get("reason") or "").startswith("번역 실패"):
        return {"healed": False, "real_failed": None, "reason": "멈춤 아님 또는 사람이 멈춘 것"}
    n = _q().failed_since(_since_resume())
    if n >= FAIL_PAUSE_AT:
        return {"healed": False, "real_failed": n, "reason": f"진짜 실패 {n}장 — 상한 {FAIL_PAUSE_AT} 이상이라 그대로"}
    resume()
    logger.warning("[이미지번역·자동] 차단기 해제 — 글자 없는 사진을 실패에서 빼니 진짜 실패 %s장(상한 %s)", n, FAIL_PAUSE_AT)
    return {"healed": True, "real_failed": n, "reason": f"진짜 실패 {n}장 < {FAIL_PAUSE_AT}"}


def resume() -> dict:
    st = {"paused": False, "reason": "", "resumed_at": datetime.now(timezone.utc).isoformat()}
    _q().state_set(_STATE_KEY, st)
    kick()
    return st


def status(item_id: str = "") -> dict:
    """화면(드로어·설정)용 — 오늘 N/상한 · 대기 · 일시정지 · 실패 누적."""
    q = _q()
    st = pause_state()
    today = q.day_count(_day_key())
    cap = daily_cap()
    all_c = q.counts()
    item_c = q.counts(item_id) if item_id else None
    waiting_cap = bool(all_c.get("queued")) and today >= cap
    return {"ok": True, "today": today, "cap": cap, "day": kst_day(), "env": ENV_CAP,
            "paused": bool(st.get("paused")), "pause_reason": st.get("reason") or "",
            "failed_since_resume": q.failed_since(_since_resume()), "fail_pause_at": FAIL_PAUSE_AT,
            "queued": all_c.get("queued", 0), "running": all_c.get("running", 0),
            "waiting_cap": waiting_cap, "item": item_c}


def item_failure(item_id: str, extra: dict) -> dict:
    """M5 후속(오너 2026-10-07, 실사용 1호): 이 상품의 이미지 번역이 **왜 안 됐나** — 카드 배지 재료. 없으면 {}.

    실측: 텐센트 계정이 연체로 정지돼 상세 사진 0장 번역 — 장마다 실패가 적혀 있었는데 카드엔 아무것도 안 보였다.
    순서: 장별 실패(공급사 원문) → 큐 차단기(실패 누적으로 멈춤) → 오늘 상한. 성공·「그릴 글자 없음」은 실패가 아니다.
    `{code, label, raw, failed, queued, today, cap, paused}`
    """
    from src.services import image_translate_tencent as tc
    failed = []
    for key in ("images_ko", "detail_images_ko", "sku_images_ko"):
        for e in (extra.get(key) or []):
            if isinstance(e, dict) and e.get("status") == "failed" and e.get("error_class") != "DailyCapReached" and not _q().is_no_text(
                    " ".join(str(e.get(k) or "") for k in ("error_code", "error_message", "reason"))):
                failed.append(e)                                 # Y11: 옛 「글자 없는 사진」(PictureWithoutText) 장은 실패 아님
    try:
        st = status(item_id)
    except Exception:                                            # noqa: BLE001 — 상태를 못 읽어도 장별 실패는 말한다
        st = {}
    ic = st.get("item") or {}
    queued = int(ic.get("queued") or 0) + int(ic.get("running") or 0)
    base = {"failed": len(failed), "queued": queued, "today": st.get("today"), "cap": st.get("cap"),
            "paused": bool(st.get("paused"))}
    if failed:
        last = max(failed, key=lambda e: str(e.get("at") or ""))
        code = tc.failure_code(last.get("error_class"), last.get("error_code"), last.get("error_message"))
        raw = " · ".join(x for x in (str(last.get("error_code") or last.get("error_class") or ""),
                                     str(last.get("error_message") or "")[:160]) if x)
        return dict(base, code=code, label=tc.FAILURE_LABELS[code], raw=raw)
    if queued and st.get("paused"):
        return dict(base, code="breaker_open", label=tc.FAILURE_LABELS["breaker_open"], raw=str(st.get("pause_reason") or ""))
    # Y11-D(오너 10-14 17:27 캡처): 오늘 상한은 **실패가 아니다** — 빨간 「이미지 번역 실패: 오늘 321/320장 — IMAGE_TRANSLATE_DAILY_CAP」
    #   (환경변수 이름까지 사용자에게 노출)이 떴다. 상한은 대기 줄(`queue_line`)이 「대기 중 n장 (오늘 상한 도달 — 내일 0시 KST 이후 처리)」로 말한다.
    return {}


def queue_line(item_id: str) -> dict:
    """「쿠팡 노출」 이미지 번역 줄 재료 — `{today, cap, in_line, cap_full}`. 상한·대기는 여기서만 말한다(실패 배지 아님)."""
    st = status(item_id)
    ic = st.get("item") or {}
    today, cap = int(st.get("today") or 0), int(st.get("cap") or 0)
    from src.services import image_polish as _ip                 # Y11-I: 다듬기(haiku) 하루 카운터 — 텐센트 호출 옆에
    return {"today": today, "cap": cap, "in_line": int(ic.get("queued") or 0) + int(ic.get("running") or 0),
            "cap_full": cap > 0 and today >= cap, "polish_today": _ip.today_count(), "polish_cap": _ip.daily_cap()}


#: Y11-C 건너뛴 사유(사람 말) — 접수·건너뜀 응답과 테스트가 같은 표를 쓴다.
SKIP_LABEL = {"spacer": "스페이서", "icon": "아이콘", "dup": "중복", "cap": "건당 상한", "done": "이미 번역", "prop": "소품 글자뿐",
              "upside": "거꾸로 번역"}
#: Y11-H(오너 2026-10-14): 텐센트가 사진을 180°로 오인해 한국어를 거꾸로 그린 장 — 원본으로 두고 「글자 고치기」로 고친다.
#   ImageTranslateLLM 요청에는 회전 각도를 정하는 칸이 없다(SDK 요청 모델: Data·Target·Url·Mode뿐) — 다시 보내도 같은 결과(과금만).
UPSIDE_REASON = "거꾸로 번역(텐센트가 사진을 180°로 오인) — 원본 그대로 · 머리글은 「글자 고치기」로"


def _is_pwt(e: dict) -> bool:
    """Y11-C(오너 2026-10-14): 「글자 없는 사진」은 텐센트 `PictureWithoutText`일 때만. D3 「그릴 줄 없음」·OCR 「한자 0」·
    `Data` 오류 같은 다른 실패는 글자 없음이 아니다(「번역 실패 — 원문」)."""
    if not isinstance(e, dict):
        return False
    if e.get("vendor") == "tencent" and str(e.get("reason") or "").startswith("글자 없는 사진 — 원본 그대로"):
        return True                                   # #898 이전 PWT 기록 — 사유에 코드가 안 적혔다(그 문구는 PWT 경로만 썼다)
    return _q().is_no_text(" ".join(str(e.get(k) or "") for k in ("error_code", "error_message", "reason")))


def translate_plan(extra: dict, *, retry: bool = False) -> dict:
    """Y11-C — 이 상품에서 번역 줄에 넣을 장 · 건너뛸 장(사유) · 글자 없는 장. **한 곳에서 정한다**(자동 접수·「다시 번역」 공용).

    실측 10-14 16:07 VRSUK: 「등록에서 빠질 8장(스페이서·아이콘·판촉 배너) 안 보냄」 — 판촉 배너·상표 위험 장은 번역 → 글자 상자 →
    **사용자 편집 대상**이다(등록 제외 여부는 편집 뒤 Y10 결정). 그래서 빼는 것은 **스페이서(1px)·아이콘(작은 그림)·중복**뿐이다
    (+ 오너 Z3-2 건당 상한). 판촉·스토어 배너로 읽혔다는 이유로는 빼지 않는다.

    `retry`(「다시 번역」)면 글자 상자가 없는 옛 번역본(#896 이전)·OCR 「한자 0」으로 건너뛴 장도 다시 보낸다 — 편집에 상자가 필요하다.
    반환 `{send:[(kind, idx, why)], skip:{사유: [(kind, idx)]}, no_text:[(kind, idx)]}`.
    """
    from src.services import detail_image_plan as _dip
    from src.services import prop_text as _pt
    prop_off = _pt.exempt(extra)                                  # 책·포스터 상품이면 소품 규칙 끔(다시 보낸다)
    send, skip, no_text = [], {k: [] for k in SKIP_LABEL}, []
    from src.services import image_translate_store as _its
    for kind in _its.KINDS:                                       # Y11-U: 갤러리 · 상세 · 옵션(SKU) 사진
        ko_key = _its.keys_of(kind)[1]
        ents = {int(e.get("idx", -1)): e for e in (extra.get(ko_key) or []) if isinstance(e, dict)}
        cap, seen = per_item_cap(kind), set()
        for i, u in enumerate(_its.originals_of(extra, kind)):
            fu = _dip.fix_url(u)
            ux = _dip.url_exclusion(fu)
            if ux:
                skip["spacer" if "스페이서" in ux else "icon"].append((kind, i))
                continue
            if fu in seen:
                skip["dup"].append((kind, i))
                continue
            seen.add(fu)
            if i >= cap:
                skip["cap"].append((kind, i))                    # Z3-2: 건당 상한 넘는 장은 원본 유지(보내지 않는다)
                continue
            e = ents.get(i) or {}
            st = e.get("status")
            if st == "excluded" and e.get("vendor") == "rule":     # 받아 보니 작은 그림·스페이서(크기 규칙) — 보내지 않았다
                skip["spacer" if "스페이서" in str(e.get("exclude") or e.get("reason") or "") else "icon"].append((kind, i))
                continue
            if _is_pwt(e):
                no_text.append((kind, i))                        # 텐센트가 「글자 없음」이라 답한 장 — 다시 보내도 같은 답
                continue
            if e.get("upside_down"):
                skip["upside"].append((kind, i))                 # Y11-H: 다시 보내도 또 거꾸로 — 「글자 고치기」로
                continue
            if e.get("prop_only") and not prop_off:
                skip["prop"].append((kind, i))                   # Y11-G: 소품 글자뿐 — 다시 보내도 원본(과금만 남는다)
                continue
            if e.get("vendor") == "d3" and not d3_enabled():
                send.append((kind, i, "d3"))                     # Y9: 옛 D3 결과(글자만 지움 · 「그릴 줄 없음」 포함) → 텐센트 본선
            elif st == "done":
                from src.services.image_translate_store import has_boxes
                if has_boxes(e):                                 # Y11-F: 상자 있는 번역본은 다시 안 보낸다(빈 상자 목록은 「없음」)
                    skip["done"].append((kind, i))
                elif retry:
                    send.append((kind, i, "no_boxes"))           # 상자 없는 옛 번역본 — 편집하려면 상자가 있어야 한다
                else:
                    skip["done"].append((kind, i))
            elif st in ("skipped", "excluded") and not retry:
                skip["done"].append((kind, i))
            elif st in ("queued", "running"):
                send.append((kind, i, "waiting"))
            else:
                send.append((kind, i, "failed" if st == "failed" else ("ocr_skip" if st == "skipped" else "new")))
    return {"send": send, "skip": skip, "no_text": no_text}


def plan_line(plan: dict, accepted: int, waiting: int = 0, in_line: Optional[int] = None, cap_full: bool = False) -> str:
    """「접수 30장 · 건너뜀 2장(스페이서 1 · 아이콘 1) · 건당 상한 n장 · 글자 없음 n장 · 대기 중 n장 (10분 내 처리)」 — 실제 수만.
    Y11-C2(오너): 상한에 걸린 장은 따로 센다(어느 장이 잘렸는지 보이게) · 「대기 중」은 이 상품이 지금 줄에 선 장(누르자마자 「오늘 0」이라도
    처리 전인 것이 보이게 — 큐는 바로 돌고, 늦어도 10분 크론이 비운다)."""
    sk = [(SKIP_LABEL[k], len(v)) for k, v in plan["skip"].items() if v and k not in ("cap", "upside")]
    n_skip = sum(n for _l, n in sk)
    parts = [f"접수 {accepted}장"]
    if waiting:
        parts.append(f"이미 대기 중 {waiting}장")
    if n_skip:
        parts.append(f"건너뜀 {n_skip}장(" + " · ".join(f"{l} {n}" for l, n in sk) + ")")
    if plan["skip"].get("cap"):
        parts.append(f"건당 상한 {len(plan['skip']['cap'])}장")
    parts.append(f"글자 없음 {len(plan['no_text'])}장")
    if plan["skip"].get("upside"):
        parts.append(f"거꾸로 번역 {len(plan['skip']['upside'])}장 — 글자 고치기로")
    if in_line:
        # 오늘 상한이 찼으면 10분 안에 돌지 않는다 — 그렇게 말한다(「10분 내」 거짓 금지)
        parts.append(f"대기 중 {in_line}장 (오늘 상한 도달 — 내일 0시 KST 이후 처리)" if cap_full
                     else f"대기 중 {in_line}장 (10분 내 처리)")
    return " · ".join(parts)


def retry_item(user_id: str, item_id: str, url: str, extra: dict, *, may_resume: bool) -> dict:
    """「다시 번역」 — `translate_plan(retry=True)`이 고른 장만 줄에 넣는다(새 줄 + 끝난 줄 다시 대기). 차단기가 멈춰 있으면 공유 사용자만 재개.

    Y11-C: 예전엔 큐의 「실패」 줄을 통째로 되살려(`retry_failed`) 이미 번역된 장(갤러리 1~3)까지 다시 돌려 덮어썼고,
    화면은 그 줄 수(「26장을 다시 넣었어요」)를 말했다 — 실제 접수(4장)와 달랐다. 이제 계획과 접수 수만 말한다."""
    plan = translate_plan(extra, retry=True)
    q = _q()
    pages = [(k, i) for k, i, _w in plan["send"]]
    new = q.enqueue(user_id, item_id, pages) if pages else 0
    again = q.requeue_pages(item_id, pages) if pages else 0
    accepted = new + again
    waiting = max(0, len(pages) - accepted)                  # 이미 대기·진행 중인 장(같은 장을 두 번 보내지 않는다)
    st = pause_state()
    resumed = False
    if st.get("paused") and may_resume:
        resume()
        resumed = True
    elif accepted:
        kick()
    s2 = status(item_id)
    ic = s2.get("item") or {}
    in_line = int(ic.get("queued") or 0) + int(ic.get("running") or 0)
    cap_full = int(s2.get("today") or 0) >= int(s2.get("cap") or 0) > 0
    line = plan_line(plan, accepted, waiting, in_line, cap_full)
    logger.info("[이미지번역·다시] item=%s %s", item_id, line)
    return {"ok": True, "requeued": accepted, "accepted": accepted, "waiting": waiting, "resumed": resumed,
            "paused": bool(s2.get("paused")) and not resumed, "pause_reason": s2.get("pause_reason") or "",
            "today": s2.get("today"), "cap": s2.get("cap"), "line": line, "in_line": in_line,
            "pages": [{"kind": k, "idx": i, "why": w} for k, i, w in plan["send"]],
            "skipped": {k: [{"kind": a, "idx": b} for a, b in v] for k, v in plan["skip"].items() if v},
            "no_text": [{"kind": a, "idx": b} for a, b in plan["no_text"]]}


# ── 접수 ──────────────────────────────────────────────────────────────────────

def enqueue_after_enrich(user_id: str, item_id: str, url: str, extra: dict) -> int:
    """보강 완료된 중국 소싱처 초안 → 갤러리+상세를 장 단위로 큐에(`translate_plan`). 이미 번역된 장·큐에 있는 장은 건너뛴다.
    Y11-C: 판촉·스토어 배너로 읽힌 장도 **보낸다**(편집 대상) — 빼는 건 스페이서·아이콘·중복(+건당 상한)뿐."""
    src = source_of(url)
    if not src or not settings(user_id).get(src):
        return 0
    try:
        from src.services import image_translate_tencent as tc
        if not tc.is_configured():
            # 공급사 키가 없으면 넣지 않는다 — 넣으면 장마다 「미연결」로 실패해 20장 뒤 큐가 멈춘다(의미 없는 경고).
            logger.info("[이미지번역·자동] 공급사 미연결 — 접수 안 함 item=%s", item_id)
            return 0
    except Exception:
        return 0
    plan = translate_plan(extra)
    pages = [(k, i) for k, i, _w in plan["send"]]
    n = _q().enqueue(user_id, item_id, pages) if pages else 0
    redo = [(k, i) for k, i, w in plan["send"] if w == "d3"]
    if redo:
        n += _q().requeue_pages(item_id, redo)              # Y9: 옛 D3 결과 → 텐센트 본선으로 다시
    if n:
        logger.info("[이미지번역·자동] item=%s %s", item_id, plan_line(plan, n))
        kick()
    return n


# ── 처리 ──────────────────────────────────────────────────────────────────────

def kick() -> None:
    """워커가 없으면 띄운다(프로세스당 하나 · 공급사 한도는 rate_slot이 전역으로 지킨다)."""
    if os.getenv("IMAGE_TRANSLATE_AUTO_SYNC") == "1":      # 테스트: 같은 스레드에서 끝까지
        run_until_idle()
        return
    from src.services import workers as _w
    if not _w.workers_enabled():                      # W2: 워커는 WORKERS_ENABLED 서비스에서만 — 여기선 접수만(큐에 남는다)
        logger.info("[이미지번역·자동] 이 서비스(%s)는 워커 꺼짐(%s) — 접수만", _w.service_name(), _w.gate_text())
        return
    with _WORKER["lock"]:
        th = _WORKER["thread"]
        if th and th.is_alive():
            return
        th = threading.Thread(target=run_until_idle, daemon=True, name="imgko-auto")
        _WORKER["thread"] = th
        th.start()


def run_until_idle(max_pages: int = 10_000) -> int:
    """W2: 서비스 간 단일 실행 — DB 리스를 잡은 한 곳만 돈다. 실행 기록은 서비스별로 남긴다."""
    from src.services import workers as _w
    if not _w.lease("imgko-auto"):
        logger.info("[이미지번역·자동] 다른 서비스가 돌리는 중 — 이번엔 건너뜀")
        return 0
    n = 0
    try:
        n = _drain(max_pages)
        return n
    finally:
        _w.release("imgko-auto")
        _w.record_run("imgko-auto", n)


def _drain(max_pages: int = 10_000) -> int:
    """큐가 빌 때까지(또는 상한·일시정지) 한 장씩. 처리한 장 수."""
    q = _q()
    n = 0
    while n < max_pages:
        if pause_state().get("paused"):
            return n
        from src.services import workers as _w
        _w.lease("imgko-auto")                                 # 리스 갱신(장마다)
        job = q.lease_next()
        if not job:
            return n
        # Z10-C: 인스턴스 메모리 합계가 상한 이상이면 이 장은 대기로 되돌리고 멈춘다(다음 접수·크론이 다시 깨운다)
        from src.utils import rss as _rss
        _ok_mem, _cur_mb, _lim_mb = _rss.start_ok()
        if not _ok_mem:
            q.requeue(job["id"])
            logger.warning("[이미지번역·자동] 메모리 여유 없음(%dMB ≥ %dMB) — 대기", _cur_mb, _lim_mb)
            return n
        today = q.day_count(_day_key())
        if today >= daily_cap():
            q.requeue(job["id"])                  # 보내지 않았다 — 대기로(내일 KST 자정 뒤 다시)
            logger.info("[이미지번역·자동] 일일 상한 도달(%s/%s) — 대기", today, daily_cap())
            return n
        # Y11-C: 「오늘 n/상한」은 **텐센트에 실제로 보낸 수**다 — 세는 곳은 `translate_image`(PictureWithoutText도 1회 ·
        #   OCR 「한자 0」·스페이서·예산 건너뜀은 0회). 예전엔 줄에서 꺼낼 때마다 셌다(보내지 않은 장도).
        try:
            status_, reason = _translate_job(job)
        except Exception as exc:                   # pragma: no cover
            status_, reason = "failed", f"{type(exc).__name__}: {exc}"
        q.finish(job["id"], status_, reason)
        n += 1
        if status_ == "failed" and q.failed_since(_since_resume()) >= FAIL_PAUSE_AT:
            pause(f"번역 실패 {FAIL_PAUSE_AT}장 누적 — 원인을 확인한 뒤 「재개」를 눌러 주세요(마지막 사유: {reason[:80]})")
            return n
    return n


def _entry_of(extra: dict, ko_key: str, idx: int) -> dict:
    return next((e for e in (extra.get(ko_key) or []) if isinstance(e, dict) and int(e.get("idx", -1)) == int(idx)), {})


def _translate_job(job: dict) -> tuple:
    """한 장 — `(status, reason)`. 결과는 상품의 `images_ko`/`detail_images_ko`에 장별로 적는다."""
    import json as _json

    from src.seller_console import collect_history_store as store
    from src.services import image_translate_store as istore
    item_id, kind, idx, uid = job["item_id"], job["kind"], int(job["idx"]), job["user_id"]
    row = store.get(item_id, seller_ids={uid}) or {}
    try:
        extra = _json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        extra = {}
    ko_key = istore.keys_of(kind)[1]
    originals = istore.originals_of(extra, kind)                  # Y11-U: SKU 사진은 skus[].image에서
    if not (0 <= idx < len(originals)):
        return "skipped", "그 장이 더는 없습니다"
    # Y11-F: 줄에 선 뒤 다른 길(편집기 「번역하고 글자 상자 받기」 등)이 이미 번역해 상자를 얻었으면 — 보내지도 덮지도 않는다.
    #   (줄은 접수 시점의 판단이다 — 꺼낼 때 지금 상태를 다시 본다. 실측 18:20 KST 갤러리 3)
    if istore.has_boxes(_entry_of(extra, ko_key, idx)):
        return "skipped", istore.PROTECTED_REASON
    if _entry_of(extra, ko_key, idx).get("upside_down"):
        return "skipped", UPSIDE_REASON                          # Y11-H: 또 보내도 거꾸로 — 과금만 남는다
    from src.services import prop_text as _pt
    entry = translate_page(originals[idx], idx=idx, kind=kind, item_id=item_id, seller_id=uid,
                           title=str(extra.get("title_en") or extra.get("title") or row.get("title") or ""),
                           prop_exempt=_pt.exempt(extra))
    # 저장 직전 다시 읽는다 — 그 사이 다른 장이 적혔을 수 있다(장별 병합).
    row = store.get(item_id, seller_ids={uid}) or {}
    try:
        extra = _json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        extra = {}
    by_idx = {int(e.get("idx", -1)): e for e in (extra.get(ko_key) or []) if isinstance(e, dict)}
    if istore.has_boxes(by_idx.get(idx)):
        return "skipped", istore.PROTECTED_REASON               # 번역하는 사이 상자 있는 번역본이 생겼다 — 덮지 않는다
    istore.carry_versions(by_idx.get(idx), entry)               # Y11-E: 다시 번역해도 앞선 번역본·편집본은 버전으로 남는다
    by_idx[idx] = entry
    by_idx.pop(-1, None)
    extra[ko_key] = [by_idx[k] for k in sorted(by_idx)]
    store.update(item_id, seller_ids={uid}, extra_json=_json.dumps(extra, ensure_ascii=False))
    try:
        istore.record_usage(uid, [entry], vendor="tencent")
    except Exception:
        pass
    st = entry.get("status")
    why = str(entry.get("error_message") or entry.get("reason") or "")
    if kind == "sku" and st == "done":
        _after_sku_translated(item_id, uid, extra)
    if st == "done":
        # Y11-V: 번역본이 바뀌면 네이버 등록본 본문 다시 보내기 줄(보내는 건 크론 — 이 상품의 번역·다듬기가 다 끝난 뒤 · 판매중일 때만)
        from src.services import naver_detail_refresh as _ndr
        _ndr.enqueue_item(item_id, extra, uid)
    if st == "done" and istore.has_boxes(entry):
        # Y11-I: 번역 직후 자동 다듬기 — 새 버전(번역본(다듬음))만 만든다. 텐센트 번역본은 버전으로 남는다. 실패해도 번역은 그대로.
        from src.services import image_polish as _ip
        _ip.polish_job(item_id, uid, kind, idx)
    if st not in ("done", "skipped") and _q().is_no_text(why):
        # Y4: 글자 없는 사진 = **성공(원본 유지)**. 실패로 세면 차단기가 멀쩡한 큐를 멈춘다(실측 20장 중 14장이 이것).
        return "skipped", f"글자 없는 사진 — 원본 그대로({why[:60]})"
    if st not in ("done", "skipped") and _q().is_benign(why):
        # Y11-C: 옛 D3 「그릴 줄 없음」 — 큐는 멈추지 않지만(Y4) **글자 없는 사진이라 부르지 않는다**(PWT만 그렇게 부른다)
        return "skipped", f"원본 그대로 — 그릴 줄 없음(D3) · {why[:60]}"
    if st == "excluded":                          # Y9: 주소·크기로 뺀 장 — 보내지 않았다(실패 아님)
        return "skipped", str(entry.get("reason") or "")
    return (st if st in ("done", "skipped") else "failed"), why


def _after_sku_translated(item_id: str, uid: str, extra: dict) -> None:
    """Y11-U — 옵션(SKU) 사진이 번역됐고 이 상품의 다른 장이 더 줄에 없으면 쿠팡 등록본 갱신 줄을 세운다(옵션 대표 사진 + 정가).
    장마다 세우면 장마다 재심사가 걸린다 — 마지막 장에서 한 번."""
    try:
        c = _q().counts(item_id) or {}
        if int(c.get("queued") or 0) > 0 or int(c.get("running") or 0) > 1:     # 지금 이 장이 running 1
            return
        from src.services import coupang_detail_refresh as _cdr
        n = _cdr.enqueue_item(item_id, extra, uid)
        if n:
            logger.info("[이미지번역·자동] item=%s 옵션 사진 번역 끝 — 쿠팡 등록본 %d건 갱신 줄", str(item_id)[:8], n)
    except Exception as exc:                                     # noqa: BLE001 — 갱신 줄은 덤 — 번역 결과는 그대로
        logger.warning("[이미지번역·자동] 쿠팡 갱신 줄 세우기 실패: %s", exc)


def translate_page(url: str, *, idx: int, kind: str, item_id: str, seller_id: str, title: str = "",
                   prop_exempt: bool = False) -> dict:
    """한 장 → `images_ko` 한 줄(`build_entry` 모양). Y9: 기본은 **텐센트 본선**(갤러리 「번역」 버튼과 같은 결과물),
    `IMAGE_TRANSLATE_D3=1`일 때만 옛 D3 파이프라인."""
    if not d3_enabled():
        return translate_page_tencent(url, idx=idx, kind=kind, item_id=item_id, seller_id=seller_id, prop_exempt=prop_exempt)
    return translate_page_d3(url, idx=idx, kind=kind, item_id=item_id, seller_id=seller_id, title=title)


def translate_page_tencent(url: str, *, idx: int, kind: str, item_id: str, seller_id: str, prop_exempt: bool = False) -> dict:
    """Y9(오너 2026-10-13) — 텐센트 `ImageTranslateLLM` 본선. 받기 전에 주소 정리(`//`·알리 webp 꼬리), 보내기 전에 JPEG 정규화
    (webp·gif 첫 프레임 → JPEG · 긴 변 ≤ 4096 · ≤ 4MB — `InvalidParameterValue.Data` 2장의 원인). 글자 없는 사진
    (`PictureWithoutText`)은 실패가 아니라 원본 그대로(`use=True`). 번역 결과 글자에 판촉·스토어 문구가 있으면 `exclude` 사유."""
    import time as _time
    from src.media.image_label import make_label, run_stamp
    from src.services import detail_image_plan as dip
    from src.services import image_text_precheck as precheck
    from src.services import image_translate_budget as budget
    from src.services import image_translate_store as istore
    from src.services import image_translate_tencent as tc
    t0 = _time.monotonic()
    now_iso = datetime.now(timezone.utc).isoformat()
    u = dip.fix_url(url)
    why_x = dip.url_exclusion(u)
    if why_x:
        return {"idx": int(idx), "kind": kind, "status": "excluded", "vendor": "rule", "ms": 0, "at": now_iso,
                "exclude": why_x, "reason": "등록에서 뺍니다 — " + why_x}
    raw, why = tc.fetch_image(u)
    if not raw:
        return istore.build_entry(idx, {"ok": False, "vendor": "tencent", "error_class": "FetchFailed", "error_message": why,
                                        "hint": "원본 주소가 아직 열려 있는지 확인하세요."},
                                  item_id=item_id, seller_id=seller_id, kind=kind)
    data, info = dip.prepare_for_tencent(raw)
    del raw
    if data is None:
        return istore.build_entry(idx, {"ok": False, "vendor": "tencent", "error_class": "ConvertFailed",
                                        "error_message": f"텐센트 입력으로 바꾸지 못했어요 — {info.get('note')}"},
                                  item_id=item_id, seller_id=seller_id, kind=kind)
    sz = dip.size_exclusion(int(info.get("w") or 0), int(info.get("h") or 0))
    if sz:
        return {"idx": int(idx), "kind": kind, "status": "excluded", "vendor": "rule", "ms": 0, "at": now_iso,
                "exclude": sz, "reason": "등록에서 뺍니다 — " + sz}
    # Z3-2 ① OCR 먼저 — 한자가 없다고 **확신**하면 이미지 번역에 안 보낸다(모르면 보냄).
    has, seen = precheck.han_text(data)
    if has is False:
        budget.record_skip("ocr")
        return {"idx": int(idx), "kind": kind, "status": "skipped", "vendor": "tencent-ocr", "use": True, "ms": 0, "at": now_iso,
                "ocr_text": str(seen or "")[:500], "section": dip.section(seen),
                "reason": "중국어 글자 없음(OCR 판정 — 한자 0) — 원본 그대로" + (f" · 읽은 글자 「{seen}」" if seen else "")}
    m = budget.mode()
    ok_send, spent, cap = budget.can_send(m)
    if not ok_send:
        budget.record_skip("budget")
        return {"idx": int(idx), "kind": kind, "status": "skipped", "vendor": "budget", "use": True, "ms": 0, "at": now_iso,
                "reason": f"이번 달 이미지 번역 예산 소진(${spent:.2f}/${cap:.0f}) — 원본으로 등록합니다"}
    res = tc.translate_image(data=data, mode=m)
    budget.record_call(m, bool(res.get("ok")))
    if not res.get("ok") and "PictureWithoutText" in str(res.get("error_code") or ""):
        return {"idx": int(idx), "kind": kind, "status": "skipped", "vendor": "tencent", "use": True,
                "ms": int(res.get("ms") or 0), "at": now_iso, "reason": "글자 없는 사진(PictureWithoutText) — 원본 그대로"}
    label = make_label(run_stamp("auto"), item_id, idx, "TENCENT", folder="seller")
    entry = istore.build_entry(idx, res, item_id=item_id, seller_id=seller_id, kind=kind, label=label, prop_exempt=prop_exempt)
    entry["vendor"] = "tencent"
    if info.get("converted"):
        entry["input_note"] = info.get("note")
    if entry.get("status") == "done":
        text = dip.entry_text(entry)
        entry["section"] = dip.section(text)
        x = dip.text_exclusion(text)
        if x:
            entry["exclude"] = x
    entry["wall_ms"] = int((_time.monotonic() - t0) * 1000)
    return entry


def translate_page_d3(url: str, *, idx: int, kind: str, item_id: str, seller_id: str, title: str = "") -> dict:
    """한 장 = 벤치 최신 D3 파이프라인(`IMAGE_TRANSLATE_D3=1`일 때만)."""
    from src.media.image_label import make_label, run_stamp
    from src.services import image_translate_bench as bench
    from src.services import image_translate_store as istore
    from src.services import image_translate_tencent as tc
    from src.services.image_bench_axes import brand_tokens

    from src.services import image_translate_budget as budget
    from src.services import image_text_precheck as precheck
    now_iso = datetime.now(timezone.utc).isoformat()
    # Z3-2 ① OCR 먼저(Z7: 로컬 RapidOCR → 텐센트 OCR API) — 한자가 없다고 **확신**하면 이미지 번역에 안 보낸다(모르면 예전처럼 보냄).
    raw0, _why0 = tc.fetch_image(url)
    has, seen = precheck.han_text(raw0) if raw0 else (None, "")
    if has is False:
        budget.record_skip("ocr")
        return {"idx": int(idx), "kind": kind, "status": "skipped", "vendor": "tencent-ocr", "ms": 0, "at": now_iso,
                "reason": "중국어 글자 없음(OCR 판정 — 한자 0) — 원본 그대로" + (f" · 읽은 글자 「{seen}」" if seen else "")}
    # ② 월 예산(계정 전체 하나) — 넘으면 보내지 않고 원본으로 등록을 계속한다.
    m = budget.mode()
    ok_send, spent, cap = budget.can_send(m)
    if not ok_send:
        budget.record_skip("budget")
        return {"idx": int(idx), "kind": kind, "status": "skipped", "vendor": "budget", "ms": 0, "at": now_iso,
                "reason": f"이번 달 이미지 번역 예산 소진(${spent:.2f}/${cap:.0f}) — 원본으로 등록합니다"}
    res = tc.translate_image(url=url, mode=m)    # 박스+원문(렌더본은 쓰지 않는다)
    budget.record_call(m, bool(res.get("ok")))
    if not res.get("ok"):
        return istore.build_entry(idx, res, item_id=item_id, seller_id=seller_id, kind=kind)
    lines = res.get("lines") or []
    if not lines:
        return {"idx": int(idx), "kind": kind, "status": "skipped", "vendor": "d3", "ms": int(res.get("ms") or 0),
                "reason": "이미지에 번역할 글자가 없습니다 — 원본을 씁니다", "at": datetime.now(timezone.utc).isoformat()}
    raw, why = (raw0, _why0) if raw0 else tc.fetch_image(url)
    if not raw:
        return istore.build_entry(idx, {"ok": False, "vendor": "d3", "error_class": "FetchFailed",
                                        "error_message": f"원본을 받지 못했습니다: {why}"},
                                  item_id=item_id, seller_id=seller_id, kind=kind)
    out = bench._render_d3_for(raw, lines, brand_tokens(title), gen_remove=True)
    pick, pipe = _pick_render(out)
    credits = float((out.get("gen_remove") or {}).get("cloud_credits") or 0.0)
    if credits:
        logger.info("[이미지번역·자동] item=%s %s#%s gen_remove 크레딧 추정 %.3f", item_id, kind, idx, credits)
    if not (pick and pick.get("ok") and pick.get("image_bytes")):
        err = (pick or {}).get("error") or out.get("error") or "렌더 결과가 없습니다"
        return istore.build_entry(idx, {"ok": False, "vendor": "d3", "error_class": "RenderFailed",
                                        "error_message": err}, item_id=item_id, seller_id=seller_id, kind=kind)
    rows = out.get("rows") or []
    result = {"ok": True, "vendor": "d3", "ms": int(res.get("ms") or 0),
              "image_b64": base64.b64encode(pick["image_bytes"]).decode("ascii"),
              "lines": lines,
              "source_text": "\n".join(str(r.get("source") or "") for r in rows),
              "target_text": "\n".join(str(r.get("render_text") or "") for r in rows)}
    label = make_label(run_stamp("auto"), item_id, idx, pipe, folder="seller")
    entry = istore.build_entry(idx, result, item_id=item_id, seller_id=seller_id, kind=kind, label=label)
    entry["pipeline"] = pipe
    if credits:
        entry["cloud_credits"] = credits
    return entry


def _f_score(one: dict):
    try:
        return float(((one or {}).get("axes") or {}).get("F", {}).get("score"))
    except (TypeError, ValueError):
        return None


def _pick_render(out: dict) -> tuple:
    """telea vs gen_remove — **실제로 gen_remove가 그렸고**(폴백 아님) F축이 같거나 높으면 gen_remove."""
    tel = out if out.get("ok") else None
    g = out.get("gen_remove") or {}
    g_ok = bool(g.get("ok") and g.get("image_bytes") and g.get("inpainter") == "gen_remove")
    if g_ok and (not tel or (_f_score(g) or 0) >= (_f_score(tel) or 0)):
        return g, "GEN_REMOVE"
    return (tel, "TELEA") if tel else (None, "TELEA")
