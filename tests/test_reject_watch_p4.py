"""tests/test_reject_watch_p4.py — 등록 파이프 P4: 반려감시 서버화.

기존 반려 3유형 표준 자동 분류(이미지규격→재등록/상표권→삭제/옵션값→값대체) + 애플 카테고리
(iPhone 보류·삼성/픽셀 유효) + comment 기반 판정(상태 문구 아님·오독 지뢰) + 오너 게이트. 오프라인·주입.
"""
from __future__ import annotations

from src.pipeline import reject_watch as RW


# ── 분류: comment(사유)로만 판정 ──────────────────────────────────────────────────
def test_classify_three_standard_kinds():
    assert RW.classify_rejection("대표 이미지 규격이 맞지 않습니다(해상도 부족)")["kind"] == "image_spec"
    # 처방 코드는 불변(reupload). 사람용 문구만 반려 1호 실데이터로 구체화됨(이미지 재수집·교체 후 재제출).
    _img = RW.classify_rejection("대표 이미지 규격")
    assert _img["prescription"] == "reupload" and "재제출" in _img["prescription_ko"]
    tm = RW.classify_rejection("상표권 침해 소지 — 브랜드 권리 확인 필요")
    assert tm["kind"] == "trademark" and tm["prescription_ko"] == "삭제 권고"
    ov = RW.classify_rejection("옵션값 정보가 누락되었습니다")
    # #690 P5: 처방 문구가 '값 대체' → '허용값으로 대체'로 구체화됐다(단위 계열은 별도 유형).
    assert ov["kind"] == "option_value" and ov["prescription_ko"] == "허용값으로 대체"


def test_classify_status_phrase_is_not_reason():
    # "담당자 검토 결과 반려" = 상태 문구(사유 아님) → 자동 판정 금지(오너 확인). [[반려 사유 요약 오독 지뢰]]
    r = RW.classify_rejection("담당자 검토 결과 반려되었습니다")
    assert r["kind"] == "unknown" and r["comment_is_status_only"] is True
    assert RW.classify_rejection("")["kind"] == "unknown"


def test_classify_apple_category_targets():
    # 애플 카테고리 사전승인 반려 — 대상 기기로 처방 분기(오너 지시).
    iph = RW.classify_rejection("애플 카테고리 사전승인 필요", title="아이폰15 케이스 투명")
    assert iph["kind"] == "apple_category" and iph["apple_target"] == "apple"      # iPhone → 보류
    sam = RW.classify_rejection("애플 카테고리 사전승인 대상", title="갤럭시 S24 케이스")
    assert sam["kind"] == "apple_category" and sam["apple_target"] == "android"    # 삼성 → 유효
    pix = RW.classify_rejection("apple category pre-approval", title="Pixel 8 case")
    assert pix["apple_target"] == "android"
    # 기기 토큰이 comment에 있어도 판정(title 미상일 때).
    cm = RW.classify_rejection("애플 카테고리 사전승인 — 갤럭시 S24용", title="")
    assert cm["kind"] == "apple_category" and cm["apple_target"] == "android"


def test_classify_priority_apple_over_trademark():
    # 애플 우선(카테고리 사전승인이 상표권보다 구체적 처방).
    r = RW.classify_rejection("애플 상표 관련 사전승인", title="아이폰 케이스")
    assert r["kind"] == "apple_category"


# ── /histories comment 추출: 튜플/딕트/리스트 안전 ────────────────────────────────
def test_latest_rejection_comment_tuple_and_reject_row():
    body = {"data": [
        {"statusName": "승인요청", "comment": "요청"},
        {"statusName": "승인반려", "comment": "이미지 규격 부적합"},
    ]}
    assert RW.latest_rejection_comment((200, body)) == "이미지 규격 부적합"     # (status, body) 언패킹
    assert RW.latest_rejection_comment(body) == "이미지 규격 부적합"           # dict 직접
    assert RW.latest_rejection_comment([{"status": "REJECTED", "reason": "옵션값"}]) == "옵션값"


def test_latest_rejection_comment_fallback_and_empty():
    # 반려 표기 없어도 마지막 comment 폴백(조용한 누락 방지).
    assert RW.latest_rejection_comment({"data": [{"statusName": "심사중", "comment": "대기"}]}) == "대기"
    assert RW.latest_rejection_comment((500, "err")) == ""
    assert RW.latest_rejection_comment(None) == ""


# ── scan: 조회·분류·알림(실행 없음) ───────────────────────────────────────────────
def test_scan_rejections_groups_and_manual():
    items = [{"sid": "1", "title": "케이스", "account": "gogane"},
             {"sid": "2", "title": "지갑", "account": "gogane"},
             {"sid": "3", "title": "아이폰 케이스", "account": "gogane"}]
    hist = {"1": {"data": [{"statusName": "승인반려", "comment": "이미지 규격"}]},
            "2": {"data": [{"statusName": "승인반려", "comment": "상표권 침해"}]},
            "3": {"data": [{"statusName": "승인반려", "comment": "애플 사전승인 필요"}]}}
    out = RW.scan_rejections(items, history_fn=lambda sid, acct: hist[sid])
    assert out["scanned"] == 3
    assert out["by_kind"] == {"image_spec": 1, "trademark": 1, "apple_category": 1}
    assert "반려 3건" in out["alert"]
    assert all("registered" not in r for r in out["rows"])       # 등록/삭제 안 함


def test_scan_history_error_is_honest_unknown():
    def boom(sid, acct):
        raise RuntimeError("타임아웃")
    out = RW.scan_rejections([{"sid": "9", "title": "x"}], history_fn=boom)
    assert out["rows"][0]["kind"] == "unknown" and "조회 실패" in out["rows"][0]["error"]
    assert out["needs_manual"] == 1


# ── apply: 오너 게이트 뒤 실행(비가역) ────────────────────────────────────────────
def test_apply_gated_when_not_approved():
    row = {"sid": "1", "kind": "trademark"}
    r = RW.apply_prescription(row, approved=False, delete_fn=lambda s: 1/0)
    assert r["applied"] is False and "보류" in r["reason"]        # 실행 0(핸들러 호출 안 됨)


def test_apply_routes_by_prescription_when_approved():
    calls = {"del": [], "reup": [], "reissue": []}
    common = dict(reupload_fn=lambda sid, row: calls["reup"].append(sid) or {"success": True},
                  delete_fn=lambda sid: calls["del"].append(sid) or True,
                  reissue_fn=lambda sid: calls["reissue"].append(sid) or {"success": True})
    img = RW.apply_prescription({"sid": "1", "kind": "image_spec"}, approved=True, **common)
    tm = RW.apply_prescription({"sid": "2", "kind": "trademark"}, approved=True, **common)
    assert img["applied"] and img["action"] == "reupload" and calls["reup"] == ["1"]
    assert tm["applied"] and tm["action"] == "delete" and calls["del"] == ["2"]


def test_apply_apple_target_gates_iphone_but_reissues_android():
    common = dict(reissue_fn=lambda sid: {"success": True})
    iph = RW.apply_prescription({"sid": "1", "kind": "apple_category", "apple_target": "apple"},
                                approved=True, **common)
    sam = RW.apply_prescription({"sid": "2", "kind": "apple_category", "apple_target": "android"},
                                approved=True, **common)
    assert iph["applied"] is False and "보류" in iph["reason"]     # iPhone → 보류
    assert sam["applied"] is True and sam["action"] == "reissue"   # 삼성/픽셀 → 유효 재등록


def test_apply_unknown_always_held():
    r = RW.apply_prescription({"sid": "1", "kind": "unknown"}, approved=True,
                              delete_fn=lambda s: True, reupload_fn=lambda s, r: True)
    assert r["applied"] is False


# ── 라우트(오너 세션 인증·자격 미설정 정직·apply 게이트) ──────────────────────────────
def _admin_client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner"; s["user_email"] = "shanks8@hanmail.net"; s["user_role"] = "admin"
    return c


def test_route_scan_honest_when_no_creds(monkeypatch):
    for k in ("COUPANG_GOGANE_ACCESS_KEY", "COUPANG_GOGANE_SECRET_KEY", "COUPANG_ACCESS_KEY",
              "COUPANG_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    c = _admin_client(monkeypatch)
    r = c.post("/admin/reject-watch/scan", json={"account": "gogane", "sids": ["1", "2"]})
    d = r.get_json()
    assert d["ok"] is False and "자격 미설정" in d["error"]         # 가짜 조회 0


def test_route_apply_gated_preview(monkeypatch):
    monkeypatch.delenv("REJECT_WATCH_APPROVED", raising=False)
    c = _admin_client(monkeypatch)
    r = c.post("/admin/reject-watch/apply",
               json={"account": "gogane", "rows": [{"sid": "1", "kind": "trademark"}]})
    d = r.get_json()
    assert d["ok"] and d["approved"] is False and d["applied"] == 0   # 비가역 보류(미리보기만)
    assert d["results"][0]["applied"] is False


# ── 셀러 콘솔 화면(조회·분류·알림, 실행 없음) ─────────────────────────────────────
def _seller_client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    return app.test_client()


def test_seller_screen_get_renders_input(monkeypatch):
    c = _seller_client(monkeypatch)
    r = c.get("/seller/sourcing/reject-watch")
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "반려 감시" in body and "이력 comment" in body


def test_seller_screen_post_honest_when_no_creds(monkeypatch):
    for k in ("COUPANG_GOGANE_ACCESS_KEY", "COUPANG_GOGANE_SECRET_KEY", "COUPANG_ACCESS_KEY",
              "COUPANG_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    c = _seller_client(monkeypatch)
    r = c.post("/seller/sourcing/reject-watch", data={"account": "gogane", "sids": "123\n456"})
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "자격 미설정" in body           # 가짜 조회 0
