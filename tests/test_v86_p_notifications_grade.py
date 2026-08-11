"""tests/test_v86_p_notifications_grade.py — v86-P: 알림 설정 화면 정직화 + 에디토리얼 격상.

결함: /seller/notifications(셀러 노출)가 env-var 이름(TELEGRAM_BOT_TOKEN·RESEND_API_KEY·
RESEND_FROM_EMAIL·TELEGRAM_CHAT_ID)·개발 경로(/health/deep)·내부 플레이스홀더([상품명] 등)를
그대로 노출 → 절대원칙(일반 유저에게 개발 표기 노출 금지) 위반. 디자인도 제네릭(h4·부트스트랩
badge bg-*).

수리: 개발 표기 제거→평문 카피, gogabridj 에디토리얼(오버라인+금 헤어라인) + 공통 상태 뱃지
(pc-badge: 청록 연결 / 주황 미연결). views 테스트 응답의 env-var 누출도 제거.
"""
from __future__ import annotations

from pathlib import Path

TPL = Path("src/seller_console/templates/notifications.html").read_text(encoding="utf-8")
APPCSS = Path("src/static/app.css").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")

# 셀러 화면에 노출되면 안 되는 개발 표기(절대원칙).
_DEV_LEAKS = [
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "RESEND_API_KEY", "RESEND_FROM_EMAIL",
    "/health/deep", "환경변수",
]


def test_notifications_template_has_no_dev_exposure():
    for tok in _DEV_LEAKS:
        assert tok not in TPL, f"알림 화면에 개발 표기 노출: {tok}"
    # 내부 대괄호 플레이스홀더([상품명]·[서비스명]·[실패])도 평문으로 교체됐다.
    for ph in ("[상품명]", "[서비스명]", "[실패]"):
        assert ph not in TPL, f"내부 플레이스홀더 노출: {ph}"


def test_notifications_uses_editorial_header_and_hairline():
    assert "console-kpi-label" in TPL, "오버라인 키커 없음"
    assert "pc-hairline" in TPL, "금 헤어라인 없음"


def test_notifications_uses_gogabridj_status_badges_not_bootstrap():
    assert "pc-badge" in TPL, "gogabridj 상태 뱃지(pc-badge) 미사용"
    assert "pc-badge-on" in TPL and "pc-badge-off" in TPL, "연결/미연결 뱃지 변형 누락"
    # 부트스트랩 컬러 뱃지 잔재 0.
    assert "badge bg-success" not in TPL and "badge bg-warning" not in TPL, "부트스트랩 badge bg-* 잔재"
    # 이모지 0(bi-* 아이콘만).
    for emo in ("✅", "❌", "⚠️", "📦", "🏛️", "↩️"):
        assert emo not in TPL, f"이모지 노출: {emo}"


def test_pc_badge_component_is_token_based_single_source():
    # app.css에 공통 상태 뱃지 컴포넌트가 토큰(var(--teal)/var(--orange))으로 정의됐다(하드코딩 색 아님).
    assert ".pc-badge" in APPCSS and ".pc-badge-on" in APPCSS and ".pc-badge-off" in APPCSS
    i = APPCSS.find(".pc-badge-on")
    seg = APPCSS[i:i + 240]
    assert "var(--teal)" in seg, "연결 뱃지가 청록 토큰을 안 씀"
    j = APPCSS.find(".pc-badge-off")
    seg2 = APPCSS[j:j + 240]
    assert "var(--orange)" in seg2, "미연결 뱃지가 주황 토큰을 안 씀"


def test_notifications_test_endpoint_message_no_env_leak():
    # /notifications/test 실패 응답이 env-var 이름을 누출하지 않는다.
    i = VIEWS.find("def notifications_test")
    seg = VIEWS[i:i + 700]
    assert "TELEGRAM_BOT_TOKEN" not in seg and "TELEGRAM_CHAT_ID" not in seg, \
        "알림 테스트 응답에 env-var 누출"
    assert "연결되지 않았" in seg, "정직한 미연결 안내 문구 없음"


def test_notifications_route_renders(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as client:
        r = client.get("/seller/notifications")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "알림 설정" in body
        for tok in _DEV_LEAKS:
            assert tok not in body, f"렌더 결과에 개발 표기 노출: {tok}"
