"""tests/test_v40s6a_dashboard.py — 디자인 v3 Stage 6-a: 운영 대시보드.

**이 계약은 합격 게이트가 아니다**(오너 지시): 합격은 오너 눈으로만 판정한다.
여기서 지키는 건 규율뿐 — 4믹스 배분·토큰 단일 소스·집계 발명 0·미연결 정직 표기.
"""
from __future__ import annotations

import re
from pathlib import Path

TPL = Path("src/seller_console/templates/dashboard.html")
CSS = Path("src/static/app.css")
SNAP = Path("src/pipeline/ops_snapshot.py")


def _tpl() -> str:
    return TPL.read_text(encoding="utf-8")


def _s6_css() -> str:
    """Stage 6 CSS 선언부만(주석은 근거로 값을 인용할 수 있어 제외)."""
    css = CSS.read_text(encoding="utf-8")
    block = css.split("Stage 6-a: 운영 대시보드")[1].split("v2 Stage 5-b")[0]
    return re.sub(r"/\*.*?\*/", "", block, flags=re.S)


def _block(css: str, selector: str) -> str:
    m = re.search(r"(?:^|\n)\s*" + re.escape(selector) + r"\s*(?:,[^{]*)?\{([^}]*)\}", css)
    assert m, f"선택자 없음: {selector}"
    return m.group(1)


def test_tokens_only_no_hardcoded_values():
    """토큰 단일 소스 — 하드코딩 hex 0(디자인 절대원칙)."""
    css, html = _s6_css(), _tpl()
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), "Stage 6 CSS에 하드코딩 hex"
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", html)
    assert "color:" not in html and "background:" not in html and "<style" not in html


def test_g1_viewport_fit_and_mobile_fallback():
    """G1 — 1920×940 스크롤바 0 · 390px 1열 폴백. 5-f 문법 승계.

    실측(scripts/_devshot_v40s6a.py): 0데이터·실데이터 **scrollHeight 940/940 · 공동 0px**,
    390px는 1열 · 가로 스크롤 0.
    """
    css = _s6_css()
    shell = _block(css, ".op-shell")
    assert "100dvh" in shell and "repeat(12" in shell        # 뷰포트에 묶인 12열 그리드
    # 조건부 스트립(온보딩)이 위에 붙어도 넘치지 않는다 — 5-e에서 배운 것(상수 오프셋 금지).
    assert "main:has(> .op-shell)" in css
    assert "@media (max-width: 1199.98px)" in css


def test_g1_no_hollow_by_construction():
    """카드가 열 높이를 끝까지 쓴다 → 카드 밖 공동이 생기지 않는다(5-f 교훈)."""
    css = _s6_css()
    assert "align-items: stretch" in _block(css, ".op-shell")
    card = _block(css, ".op-card")
    assert "flex-direction: column" in card and "overflow: hidden" in card
    assert "flex: 1 1 auto" in _block(css, ".op-card-body")   # 바디가 남는 높이를 먹는다
    assert "flex: 0 0 auto" in _block(css, ".op-card-foot")   # 액션은 카드 푸터(G1)


def test_g2_four_mix_allocation_does_not_overlap():
    """★ G2 — 넷이 **한 요소에 겹치지 않는다**.

    Bauhaus 기하는 계정/집계 타일에만, Neumo 깊이는 조작 요소에만.
    타일은 그림자를 쓰지 않고(기하), 버튼·셀렉트만 `--nm-*`를 쓴다.
    """
    css = _s6_css()
    tile = _block(css, ".op-tile")
    assert "aspect-ratio" in tile                      # Bauhaus — 기하 모듈
    assert "--nm-" not in tile, "기하 타일에 Neumo 깊이가 겹쳤다"
    neumo = _block(css, ".op-card-foot .btn, .op-card-foot select.form-select")
    assert "--nm-soft-sm" in neumo and "min-height: 44px" in neumo
    # 원색은 **신호 1점만** — 경고 타일의 점에만 주황이 쓰인다.
    assert "--orange" in _block(css, ".op-tile-alert::after")
    assert css.count("--orange") == 1, "원색이 신호 외 자리에도 쓰였다"


def test_g2_v3_supersedes_v2_geometry_ban():
    """v2 '기하 금지'와 만나면 v3 우선(오너 G2). Stage 5 계약은 자기 구역만 검사한다."""
    s5 = Path("tests/test_v40s5_regpipe_redesign.py").read_text(encoding="utf-8")
    assert "_s5_css" in s5
    css = CSS.read_text(encoding="utf-8")
    # Stage 6 블록이 Stage 5 슬라이스(`v2 Stage 5-b` 이후) **앞**에 있어야 v2 계약이 오작동하지 않는다.
    assert css.index("Stage 6-a: 운영 대시보드") < css.index("v2 Stage 5-b")


def test_g3_content_blocks_present():
    """G3 — 4계정 타일 · 반려 최근 N건 · 등록 대장 · 소싱 대기."""
    html = _tpl()
    for num, label in (("01", "등록 계정"), ("02", "반려 감시"),
                       ("03", "등록 대장"), ("04", "소싱 대기")):
        assert f'rp-step-num">{num}<' in html and label in html, label
    for key in ("ops.accounts", "ops.rejections", "ops.registrations", "ops.sourcing"):
        assert key in html, key


def test_g3_no_new_aggregation_invented():
    """★ G3 — 집계 발명 0. 스냅샷은 **기존 산출을 모으기만** 한다.

    새 합계·비율·추정을 만들면 여기서 걸린다(수치 연산 금지).
    """
    src = SNAP.read_text(encoding="utf-8")
    body = "\n".join(l for l in re.sub(r'""".*?"""', "", src, flags=re.S).splitlines()
                     if not l.lstrip().startswith("#"))
    for banned in ("sum(", "/ len(", "* 100", "round(", "avg", "mean"):
        assert banned not in body, banned
    # 소스는 전부 기존 모듈(재구현 0).
    for source in ("coupang_replicate", "naver_uploader",
                   "market_registrations_pg", "collect_history_store"):
        assert source in src, source


def test_g3_disconnected_is_honest_not_zero():
    """★ 미연결이면 숫자를 만들지 않는다 — 0을 찍으면 '0건'과 구분이 안 된다."""
    from src.pipeline import ops_snapshot as ops
    snap = ops.build()
    for key in ("registrations", "rejections", "sourcing"):
        blk = snap[key]
        assert "connected" in blk
        if not blk["connected"]:
            assert blk["note"], key            # 사유 없는 미연결 금지
    html = _tpl()
    assert "미연결" in html and "op-off" in html


def test_snapshot_block_failure_does_not_kill_dashboard(monkeypatch):
    """블록 하나가 죽어도 대시보드는 산다 — 스냅샷이 화면을 끌고 들어가지 않는다."""
    from src.pipeline import ops_snapshot as ops
    monkeypatch.setattr("src.db.market_registrations_pg.enabled",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    snap = ops.build()
    assert snap["registrations"]["connected"] is False
    assert snap["registrations"]["note"]
    assert snap["accounts"]                    # 다른 블록은 멀쩡하다


def test_onboarding_funnel_survived():
    """온보딩은 Stage 6-a에서도 살아 있다 — 3카드 블록이 한 줄 스트립으로 압축됐을 뿐."""
    html = _tpl()
    assert "op-strip" in html and "5분 시작 가이드" in html
    assert "onboarding.dismiss_href" in html and "/seller/start" in html


def test_no_dead_links_on_dashboard():
    """죽은 버튼 0 — 카드 푸터 링크가 전부 실제 라우트다."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    rules = {str(r) for r in app.url_map.iter_rules()}
    for href in re.findall(r'href="(/seller/[^"{]+)"', _tpl()):
        assert href in rules, href


# ── S3: 연동 마켓 요약 신호줄 (비차단 진단) ──────────────────────────────────────

def test_s3_signal_row_covers_markets_outside_the_four_account_axis():
    """★ 축(4계정)은 쿠팡·스마트스토어뿐이다 — 11번가 오류가 첫 화면에 안 뜨던 구멍.

    축은 그대로 두고 지원 마켓 전부를 점 하나씩으로 요약하는 줄을 붙인다.
    """
    from src.pipeline import ops_snapshot as ops
    axis = {m for m, _ko, _accts in ops.ACCOUNT_AXES}
    assert axis == {"coupang", "smartstore"}                  # 축은 4계정 유지
    rows = ops.linked_markets("s3")["rows"]
    markets = {r["market"] for r in rows}
    assert "elevenst" in markets and not markets <= axis       # 축 밖 마켓이 실제로 들어온다
    for r in rows:
        assert set(r) >= {"market", "label", "configured", "source"}
    html = _tpl()
    assert "opMarketSignal" in html and "op-sig-item" in html


def test_s3_signal_row_uses_the_single_connection_judge():
    """판정은 `market_credentials`가 정본 — 대시보드가 자기 판정기를 새로 만들지 않는다."""
    src = SNAP.read_text(encoding="utf-8")
    assert "market_credentials" in src and "credential_source" in src
    # 자격 env를 직접 읽어 "연결됐다"를 스스로 판정하면 화면마다 답이 갈린다(S1에서 잡은 유형).
    for reinvented in ("ELEVENST_API_KEY", "WC_KEY", "SHOPIFY_CLIENT_ID", "os.environ"):
        assert reinvented not in src, f"판정 재구현: {reinvented}"


def test_s3_diagnostics_are_non_blocking_and_reuse_the_endpoint():
    """★ 진단은 렌더를 막지 않는다 — 3초 타임아웃 + 엔드포인트 재사용(재구현 0)."""
    html = _tpl()
    assert "markets_integration_diagnostics" in html           # 기존 진단 라우트를 그대로 부른다
    assert "AbortController" in html and "3000" in html        # 3초 상한
    # 서버 렌더 경로에는 진단 호출이 없다(있으면 대시보드가 마켓 응답만큼 느려진다).
    assert "run_market_diagnostic" not in SNAP.read_text(encoding="utf-8")


def test_s3_diagnostic_failure_says_it_failed_not_ok():
    """실패를 성공처럼 두지 않는다 — 못 받으면 '진단 실패'라고 말한다."""
    html = _tpl()
    assert "진단 실패" in html
    css = _s6_css()
    assert "--danger" in _block(css, ".op-sig-item.is-err .op-sig-dot")
    assert "dashed" in _block(css, ".op-sig-item.is-unknown .op-sig-dot")
    assert css.count("--orange") == 1                          # 원색은 여전히 신호 1점만
