"""tests/test_a1_wing_state_dictionary.py — A1: 최신 확정 상태를 읽는다.

오너 WING 실측(2026-09-07): 16369251981은 **판매중**이었다. 우리는 계속 '임시저장'이라 했다.
원인은 낡은 이력을 읽어서가 아니라 **최신 이력을 읽을 눈이 없어서**였다:

  · 상태 사전에 `판매중`도 `심사중`도 없었다 → 그 행은 매칭 0으로 그냥 건너뛰었다.
  · `rejected`가 **절대 우선**이라, 이력 어딘가의 과거 반려 한 줄이 최신 확정을 영원히 덮었다.
  · "최신"의 방향(정렬)이 실측된 적 없이 `states[-1]`로 **가정**돼 있었다.

세 번째는 가정을 없애는 쪽으로 고쳤다 — 시각이 있으면 시각으로 정렬한다.
방향 자체는 다음 크론 로그(`log_history_shape`)로 확정한 뒤 여기에 근거를 적는다.
"""
from __future__ import annotations

import logging

from src.pipeline import reject_watch as RW


def _h(*rows):
    return {"data": list(rows)}


def _row(status, at=None, comment=None):
    r = {"statusName": status}
    if at:
        r["createdAt"] = at
    if comment:
        r["comment"] = comment
    return r


# ── 사전: 없던 두 상태 ────────────────────────────────────────────────────────
def test_selling_is_now_readable():
    """★ 오너가 실제로 본 그 상태 — 판매중."""
    assert RW.wing_state(_h(_row("판매중"))) == "selling"
    assert RW.WING_STATES["selling"]["ko"] == "판매중"
    # 노출·판매 중이면 심사는 끝났다 → 확정이라 큐를 떠난다.
    assert "selling" in RW.GRADUATING_STATES
    assert RW._next_status({"wing_state": "selling"}) == "selling"


def test_pending_is_readable_and_stays_in_queue():
    """★ 심사중·승인요청은 **결과가 아니다** — 확정으로 세면 안 되고 큐에 남아야 한다."""
    for label in ("심사중", "승인요청", "검수중", "승인 대기", "IN_REVIEW", "PENDING"):
        assert RW.wing_state(_h(_row(label))) == "pending", label
    assert "pending" not in RW.GRADUATING_STATES
    # 큐 잔류 상태로 떨어진다(다음 회전이 결과를 본다).
    from src.db.market_registrations_pg import _WATCH_STATUSES
    assert RW._next_status({"wing_state": "pending"}) in _WATCH_STATUSES


def test_approval_request_is_not_approval():
    """★★ 회귀 케이스 — [[등록 파이프 이식]]의 과탐 함정.

    처음에 '승인'을 넓게 잡았더니 **`승인요청`(제출)이 승인으로 둔갑**해 분류가 통째로 무너졌다.
    그때 얻은 교훈이 "우선순위 신호를 넓게 잡으면 전부 우선순위가 되어 신호가 죽는다"다.
    사전에 `pending`을 새로 넣으면서 그 함정을 다시 밟을 수 있어, 여기서 못 박는다.
    """
    assert RW.wing_state(_h(_row("승인요청"))) == "pending"      # 제출은 승인이 아니다
    assert RW.wing_state(_h(_row("승인완료"))) == "approved"     # 완료만 승인이다
    # 규칙 순서 자체를 박는다 — pending이 approved보다 **위**에 있어야 위 두 줄이 성립한다.
    keys = [k for k, _rx in RW._WING_STATE_RE]
    assert keys.index("pending") < keys.index("approved")
    # `was_selling`의 협소 정규식도 그대로다(같은 함정의 원래 피해자).
    assert RW.was_selling(_h(_row("승인요청"), _row("반려"))) is False
    assert RW.was_selling(_h(_row("판매중"), _row("반려"))) is True


# ── 우선순위: 최신 확정이 이긴다 ─────────────────────────────────────────────
def test_old_rejection_no_longer_buries_the_latest_state():
    """★ 오너가 잡은 그 결함 — 재제출해 판매중이 돼도 우리 눈엔 계속 반려였다."""
    h = _h(_row("반려", "2026-09-03 00:00", "대표이미지 최소 500*500 미달"),
           _row("판매중", "2026-09-07 09:00"))
    assert RW.wing_state(h) == "selling"


def test_a_later_rejection_still_wins():
    """반대 방향도 지킨다 — 팔리던 게 내려간 건 반려가 맞다(사후 재심사)."""
    h = _h(_row("판매중", "2026-09-01 00:00"), _row("반려", "2026-09-05 00:00", "상표권"))
    assert RW.wing_state(h) == "rejected"


def test_pending_does_not_erase_the_last_settled_fact():
    """심사중은 미확정이다 — 그 앞의 **확정**을 본다. 다시 냈다고 반려 사실이 사라지진 않는다."""
    h = _h(_row("반려", "2026-09-03 00:00", "이미지"), _row("승인요청", "2026-09-06 00:00"))
    assert RW.wing_state(h) == "rejected"


def test_time_sorting_beats_row_order():
    """★ **정렬 가정을 없앴다.** 응답이 최신 우선으로 와도 시각이 있으면 시각이 이긴다.

    예전 `states[-1]`은 "마지막 행 = 최신"을 가정했다 — 그 가정은 실측된 적이 없었다.
    """
    newest_first = _h(_row("판매중", "2026-09-07 09:00"), _row("반려", "2026-09-03 00:00", "이미지"))
    assert RW.wing_state(newest_first) == "selling"
    oldest_first = _h(_row("반려", "2026-09-03 00:00", "이미지"), _row("판매중", "2026-09-07 09:00"))
    assert RW.wing_state(oldest_first) == "selling"


def test_measured_direction_is_recorded_but_not_extrapolated():
    """★★ **방향 실측 확정(2026-09-09, 크론 로그 원문): Wing 이력은 최신 우선.**

    옛 `states[-1]` 가정은 틀린 정도가 아니라 **정확히 거꾸로**였다 — 마지막 행은 최신이 아니라
    가장 오래된 행이었다. 그 사실을 여기 근거로 박는다(가정 폐기 기록).

    다만 **시각 없는 입력까지 뒤집지는 않는다.** 잰 것은 *실제 응답*(시각을 달고 오는)의 방향이지,
    시각 없는 응답의 순서는 잰 적이 없다 — 거기까지 가면 실측이 아니라 외삽이고,
    읽는 순서로 쓰인 기존 픽스처의 의미를 **조용히 뒤집게** 된다. 실제 경로는 시각이 있어
    이 폴백을 타지 않는다. (실측을 넓게 적용하고 싶으면 그 케이스를 먼저 재야 한다.)
    """
    # 시각이 있으면 순서와 무관하게 시각이 이긴다 — 실측이 필요 없는 자리.
    assert RW.wing_state(_h(_row("판매중", "2026-09-07 09:00"),
                            _row("반려", "2026-09-03 00:00"))) == "selling"
    assert RW.wing_state(_h(_row("반려", "2026-09-03 00:00"),
                            _row("판매중", "2026-09-07 09:00"))) == "selling"
    # 시각이 없으면 응답 순서를 **그대로** 쓴다(외삽 0).
    assert RW.wing_state(_h(_row("반려"), _row("판매중"))) == "selling"
    # 순서 규칙은 한 곳에만 산다 — 네 함수가 각자 들고 있다가 동시에 거꾸로였던 자리다.
    assert RW._ordered_rows({"data": []}) == []
    src = __import__("pathlib").Path("src/pipeline/reject_watch.py").read_text(encoding="utf-8")
    assert src.count("_ordered_rows(history)") >= 4, "순서 규칙을 다시 각자 들고 있다"


# ── 계측: 방향을 실측으로 확정하기 위한 로그 ─────────────────────────────────
def test_history_shape_is_logged_for_the_next_cron(caplog):
    """★ 가정을 남겨 두지 않으려면 **다음 크론이 답을 가져와야 한다.**

    첫 행·끝 행의 시각과 상태를 INFO로 남긴다. 자격·개인정보는 싣지 않는다(상태·시각·키 이름만).
    """
    h = _h(_row("반려", "2026-09-03 00:00", "이미지"), _row("판매중", "2026-09-07 09:00"))
    with caplog.at_level(logging.INFO, logger="src.pipeline.reject_watch"):
        shape = RW.log_history_shape("16369251981", h)
    assert shape["n"] == 2
    assert shape["first"]["at"] == "2026-09-03 00:00" and shape["last"]["at"] == "2026-09-07 09:00"
    assert "반려감시 상태" in caplog.text and "16369251981" in caplog.text
    # 원문 comment는 로그에 안 싣는다 — 사유 텍스트는 화면·대장의 몫이다.
    assert "이미지" not in caplog.text


def test_every_rotation_outcome_is_findable_by_one_search_term():
    """★ 회수 검색어 통일(오너 2026-09-07) — 「반려감시 상태」 **하나로** 한 회전의 결말이 다 나온다.

    검색어가 결말마다 갈리면 오너가 무엇으로 찾느냐에 따라 다른 결말을 놓친다. 특히 위험한 건
    **아무것도 안 나오는 경우**다 — 배포가 안 된 건지, 큐가 0건인지, 크론이 터진 건지 구분이 안 된다.
    그 모호함은 "아직"과 "결함"을 가르는 시한 판정을 그대로 망친다. 그래서 실패·완료·상태·
    대상없음·오류 **다섯 결말 전부**와 A1 계측이 같은 접두어를 쓴다.
    """
    from pathlib import Path
    cron = Path("src/pricing/cron.py").read_text(encoding="utf-8")
    # **실제 로그 호출만** 본다 — 주석·docstring·응답 JSON 문구는 로그가 아니라 검색 대상이 아니다
    #   (내가 쓴 설명문이 내 계약을 통과시키는 자해를 이 스위트에서 이미 네 번 했다).
    emitted = [ln.strip() for ln in cron.splitlines() if "logger." in ln and '"반려감시' in ln]
    body = "\n".join(emitted)
    for outcome in ("실패", "큐 잔류", "감시 대상 없음", "오류(백그라운드)"):
        assert outcome in body, f"결말 누락: {outcome}"
    # 로그로 나가는 `반려감시` 줄은 전부 `반려감시 상태`여야 한다 — 하나만 새도 검색이 샌다.
    #   (`반려감시 완료`는 상태 줄과 **같은 회전에 붙어 나오는** 짝이라 예외로 남긴다.
    #    ※ 2026-09-09 부검: 이 예외가 **알림 판정을 가리고 있었다**(`알림 True/False`가 완료 줄에만
    #      있었다). 판정·실패사유를 상태 줄로 옮겨 예외가 이제 무해해졌다 — 예외를 두려면
    #      그 줄에 **판정이 없어야** 한다.)
    stray = [ln for ln in emitted
             if '"반려감시 상태' not in ln and '"반려감시 완료' not in ln]
    assert not stray, f"검색어 밖으로 샌 로그: {stray}"
    # A1 계측도 같은 접두어를 쓴다(크론 결말과 같은 검색 결과에 나오게).
    src = Path("src/pipeline/reject_watch.py").read_text(encoding="utf-8")
    assert '"반려감시 상태·이력 원문(sid=%s)' in src


def test_missing_timestamp_is_not_invented():
    """시각 키가 없으면 **빈 문자열** — 없는 시각을 지어내지 않는다."""
    assert RW._row_at({"statusName": "판매중"}) == ""
    assert RW._row_at({"statusName": "판매중", "createdAt": "2026-09-07"}) == "2026-09-07"


# ── 승인 방향 알림 ───────────────────────────────────────────────────────────
def _watch(rows_by_sid, sids):
    sent = []
    out = RW.watch_registered(
        queue_fn=lambda limit: [{"sid": s, "title": "t", "account": "gogane"} for s in sids],
        history_fn=lambda sid, acc: rows_by_sid[sid], record_fn=lambda sid, **k: True,
        notify_fn=lambda alert, rows: sent.append(alert))
    return out, sent


def test_selling_transition_notifies_once_and_graduates():
    """★ 기대 결과(오너 A1): 판매중 전환 → 졸업 → 알림 1회.

    지금까지는 반려가 있을 때만 알려서 **문제가 풀렸다는 소식은 영영 오지 않았다.**
    졸업하는 건이라 다음 회전엔 큐에 없다 — 그래서 한 번만 뜬다(잡음 0은 유지).
    """
    H = {"A": _h(_row("반려", "2026-09-03 00:00", "대표이미지 최소 500*500 미달"),
                 _row("판매중", "2026-09-07 09:00"))}
    out, sent = _watch(H, ["A"])
    assert out["rows"][0]["wing_state"] == "selling"
    assert out["graduated"] == 1 and out["stayed"] == 0
    assert len(sent) == 1 and sent[0].startswith("✅ 판매중 전환 1건")


def test_graduated_row_is_not_counted_as_a_remaining_rejection():
    """★ 방금 판매중이 된 건을 '반려 N건'에 넣지 않는다 — 해결된 일을 미해결로 읽히게 만든다."""
    H = {"A": _h(_row("반려", "2026-09-03 00:00", "이미지"), _row("판매중", "2026-09-07 09:00")),
         "B": _h(_row("반려", "2026-09-05 00:00", "상표권 침해"))}
    _out, sent = _watch(H, ["A", "B"])
    assert "남은 반려 1건" in sent[0], sent[0]
    _out2, sent2 = _watch(H, ["A"])
    assert "반려" not in sent2[0].replace("판매중 전환", ""), sent2[0]


def test_rejection_only_alert_is_unchanged():
    """전환이 없으면 알림 문구는 예전 그대로다 — 바꾸지 않은 것도 계약이다."""
    H = {"B": _h(_row("반려", "2026-09-05 00:00", "상표권 침해"))}
    _out, sent = _watch(H, ["B"])
    assert sent[0].startswith("반려 1건")


# ── 화면: 확정 상태가 낡은 사유에 가려지지 않는다 ────────────────────────────
def test_settled_state_is_shown_before_the_comment_based_kind():
    """★ 오너 실측(2026-09-07): status=승인인데 분류 뱃지가 「임시저장(승인요청 누락)」이었다.

    `kind`는 **comment 전용**이고(#705), comment는 *과거에 한 말*이다. 그 뒤 상태가 바뀌면
    뱃지가 상태와 어긋난다 — 그리고 A1 이후 이 표엔 승인·판매중 행도 들어온다(수동 조회는
    큐를 안 거치므로 `_WATCH_STATUSES` 밖 상태도 조회된다). 표의 전제가 바뀐 것이다.

    #705 원칙은 **그대로 둔다**: kind는 여전히 comment로만 정한다.
    바꾼 건 **표시 순서**뿐 — 확정 상태를 먼저 놓고, 사유 유형은 '지난 사유'로 아래에.
    """
    from pathlib import Path
    tpl = Path("src/seller_console/templates/reject_watch.html").read_text(encoding="utf-8")
    cell = tpl.split('<td data-label="분류">')[1].split("</td>")[0]
    # 상태 분기가 kind 뱃지보다 **앞**에 있어야 순서가 성립한다.
    assert cell.index("r.wing_state in ('approved', 'selling')") < cell.index("r.kind == 'unknown'")
    assert "{{ r.wing_state_ko }}" in cell, "상태 라벨이 화면에 없다"
    assert "지난 사유" in cell, "승인 건의 옛 유형을 현재 유형처럼 보이게 두면 안 된다"
    # 확정이지만 조치가 필요한 상태(브랜드수정·증빙)도 상태를 먼저 보여 준다.
    assert "r.wing_state in ('brand_fix', 'doc_required')" in cell
    # 애플 카테고리 보조 표기는 **승인된 건엔 안 뜬다**(끝난 일의 처방을 계속 말하지 않는다).
    assert "r.kind == 'apple_category' and r.wing_state not in ('approved', 'selling')" in tpl


def test_kind_is_still_comment_only():
    """★ #705는 안 건드렸다 — 상태를 kind 판정에 섞으면 그게 그 원칙을 깨는 것이다."""
    import inspect
    src = inspect.getsource(RW.classify_rejection)
    assert "wing_state" not in src, "분류가 상태를 보기 시작했다(#705 위반)"
    # 승인된 이력이어도 comment가 이미지 규격이면 kind는 그대로 이미지 규격이다.
    cl = RW.classify_rejection("대표이미지는 최대 10M, 최소 500*500")
    assert cl["kind"] == "image_spec"


def test_settled_rows_carry_no_prescription_and_no_execute_button():
    """★ 판매중 행에 「처방 실행」이 살아 있었다 — 누르면 **살아 있는 상품에 승인요청을 보낸다.**

    처방도 comment 기준이라 상태와 어긋난 것(뱃지와 같은 뿌리). 끝난 일에는 처방이 없다.
    문구만 바꾸고 버튼을 남기면 고친 게 아니라 가린 것이라, **버튼도 같은 조건으로 막는다.**
    """
    from pathlib import Path
    tpl = Path("src/seller_console/templates/reject_watch.html").read_text(encoding="utf-8")
    rx = tpl.split('<td data-label="처방">')[1].split("</td>")[0]
    assert rx.index("r.wing_state in ('approved', 'selling')") < rx.index("r.kind == 'unknown'")
    assert "조치 없음" in rx
    run = tpl.split('<td data-label="실행"')[1].split("</td>")[0]
    assert run.index("r.wing_state in ('approved', 'selling')") < run.index("r.kind == 'unknown'")


def test_summary_counts_do_not_call_a_selling_row_a_rejection():
    """★ 같은 유형 — 집계도 kind 기준이라 판매중이 "반려 3건 … 임시저장 1"에 섞였다(오너 실측).

    숫자가 거짓이면 화면 전체가 거짓이 된다. 끝난 건은 반려 수에서 빼고 **따로 센다**(숨기지 않는다).
    상태가 이미 분류인 건(브랜드수정·증빙)은 '미분류'로도 안 센다 — 같은 행을 두 번 다르게 부르게 된다.
    """
    H = {"A": _h(_row("임시저장중", "2026-09-03 00:00", "임시저장"), _row("판매중", "2026-09-07 09:00")),
         "B": _h(_row("반려", "2026-09-05 09:30", "대표이미지 최소 500*500 미달")),
         "C": _h(_row("브랜드 수정요청", "2026-09-06 14:20", "브랜드 등록 필요"))}
    sc = RW.scan_rejections([{"sid": s, "title": "t", "account": "gogane"} for s in H],
                            history_fn=lambda sid, acc: H[sid])
    assert sc["alert"].startswith("판매중 1건 · 반려 2건"), sc["alert"]
    assert "임시저장" not in sc["alert"], "판매중 건의 옛 유형이 아직 집계에 있다"
    assert "브랜드 수정요청 1" in sc["alert"] and "미분류" not in sc["alert"]
    assert sc["needs_manual"] == 0, "상태가 분류인 건을 '오너 확인 필요'로 세면 안 된다"
    # scanned는 **조회한 전건**이다(숨기지 않는다 — 줄인 건 '반려' 수뿐이다).
    assert sc["scanned"] == 3


# ── 알림 부검(2026-09-09): 졸업 2회인데 「판매중 전환」 보고 0 ────────────────
def test_graduation_alert_header_says_graduation_not_rejection():
    """★ 부검 결론 — **헤더가 상태를 배신하고 있었다.**

    A1이 승인 방향 알림을 만들었는데 제목은 `쿠팡 반려 감지`로 고정이었다. 그래서 졸업 소식이
    **반려 알림 제목으로** 나갔다 — 받아도 '판매중 전환 알림'으로 안 읽힌다.
    오너가 상정한 두 갈래(발송 안 됨 / 발송됐는데 미보고) 어디에도 없던 **세 번째**다:
    발송은 되는 구조인데 **다른 소식으로 도착한다.**

    문자열(alert 문구)이 아니라 **행 데이터**(wing_state)로 가른다 — 문구가 바뀌어도 안 깨지게.
    """
    from pathlib import Path
    cron = Path("src/pricing/cron.py").read_text(encoding="utf-8")
    body = cron.split("def _reject_notify_fn")[1].split("\ndef ")[0]
    assert '"판매중 전환" if graduated else "반려 감지"' in body, "헤더가 아직 고정 문구다"
    assert 'f"[고가브릿지] 쿠팡 {head_ko}' in body
    # 졸업 건의 **옛 사유**를 현재 문제처럼 붙이지 않는다(같은 뿌리 — 과거의 말을 현재로 읽기).
    assert "open_rows = [r for r in rows if r.get(\"wing_state\") not in _GRADUATED]" in body
    assert "for r in open_rows[:5]" in body and "for r in open_rows:" in body


def test_send_attempt_and_verdict_are_findable_by_the_one_search_term():
    """★ 두 번째 부검 소득 — **판정 필드가 오너 검색어 밖에 있었다.**

    `알림 True/False`는 `반려감시 완료` 줄에만 있었는데, 그 줄은 「반려감시 상태」 검색에 안 걸린다.
    검색어를 통일했다고 보고해 놓고 정작 **판정을 못 보게 해 뒀다**(내 보고의 구멍).
    그리고 `notify_error`는 **어디에도 로그되지 않아** '안 보냄'과 '보내려다 실패'가 구분되지 않았다.

    이제 한 검색으로 셋이 다 나온다: 발송 **시도**(직전 줄) · 발송 **판정** · 실패 **사유**.
    """
    from pathlib import Path
    cron = Path("src/pricing/cron.py").read_text(encoding="utf-8")
    emitted = [ln.strip() for ln in cron.splitlines() if "logger." in ln and "반려감시" in ln]
    body = "\n".join(emitted)
    # 발송 시도 — send_telegram **직전**에 찍히는 줄. 있으면 호출됨, 없으면 notify_fn 미호출.
    assert '"반려감시 상태·알림 발송: %s"' in body, "발송 시도 줄이 검색어 밖이다"
    # 판정 + 실패 사유 — 상태 줄에서 같이 읽힌다.
    state_line = next(ln for ln in emitted if "큐 잔류" in ln)
    assert "알림 %s" in state_line, "판정이 상태 줄에 없다"
    assert "notify_error" in cron and "알림실패" in cron, "실패 사유가 로그되지 않는다"
