"""tests/test_v53_deploy_marker.py — v53 STEP0: 배포 마커 규약.

증상: 코드는 main에 머지됐는데 라이브에 안 보임(3회 반복) → 머지/배포 누락. 페이지 <meta name="build">
+ /health build 필드에 배포 커밋(7자리)을 노출 → curl 한 줄로 라이브 코드 버전 판정.
"""
from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")


def test_build_sha_priority_and_dev_fallback():
    from src.utils.build_info import get_build_sha
    get_build_sha.cache_clear()
    os.environ["RENDER_GIT_COMMIT"] = "deadbeefcafe1234"
    try:
        assert get_build_sha() == "deadbee"          # RENDER_GIT_COMMIT 우선, 7자리
    finally:
        os.environ.pop("RENDER_GIT_COMMIT", None)
        get_build_sha.cache_clear()
    # env 없으면 git 폴백(개발) 또는 unknown — 빈 문자열/None 아님
    v = get_build_sha()
    assert isinstance(v, str) and v and " " not in v


def test_health_exposes_build():
    from src.order_webhook import app
    with app.test_client() as c:
        j = c.get("/health").get_json()
    assert "build" in j and j["build"]                # /health 에 build 필드


def test_pages_carry_build_meta():
    from src.order_webhook import app
    with app.test_client() as c:
        # 랜딩(_base_app) — 공개 페이지, 세션 없이.
        html = c.get("/").get_data(as_text=True)
        assert re.search(r'<meta name="build" content="([^"]+)">', html), "landing: build 메타 누락"
        # 콘솔(_base) — 로그인 세션.
        with c.session_transaction() as s:
            s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
        html = c.get("/seller/dashboard").get_data(as_text=True)
        assert re.search(r'<meta name="build" content="([^"]+)">', html), "dashboard: build 메타 누락"


def test_marker_matches_health():
    # 페이지 메타와 /health build 가 같은 소스(동일 커밋) — 라이브 판정 일관.
    from src.order_webhook import app
    from src.utils.build_info import get_build_sha
    with app.test_client() as c:
        j = c.get("/health").get_json()
        with c.session_transaction() as s:
            s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
        html = c.get("/seller/dashboard").get_data(as_text=True)
        meta = re.search(r'<meta name="build" content="([^"]+)">', html).group(1)
    assert j["build"] == meta == get_build_sha()
