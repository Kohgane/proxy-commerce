"""tests/test_v55_tier1_sanity.py — v55 STEP1(Tier1 진단) + STEP2(서버 sanity 봉인).

STEP1: MAIN world 주입 검증 + 수집 클릭 시 Tier1 캐시 진단(미주입/매치0/시그니처미달 콘솔 1줄, 무음 금지).
STEP2: 가격 sanity를 서버 단일 지점으로 — KRW<100/통화미상 시 **값 폐기**(9 저장 금지), 이미지 도메인·중복 필터.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

ROOT = Path(__file__).resolve().parent.parent
CS = (ROOT / "extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MAIN = (ROOT / "extensions/chrome-collector/kgp-main.js").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


# ── STEP1: Tier1 진단 ─────────────────────────────────────────
def test_manifest_net_main_document_start():
    nets = [c for c in MANIFEST["content_scripts"]
            if c.get("world") == "MAIN" and c.get("run_at") == "document_start" and "kgp-net.js" in c.get("js", [])]
    assert nets, "kgp-net.js MAIN world document_start 주입 없음"


def test_tier1_diagnostic_source_contract():
    # kgp-main이 diag(netBound·captured·topScore·topUrl) 동봉, content_script가 원인 1줄 로그(무음 금지).
    assert "diag" in MAIN and "netBound" in MAIN and "captured" in MAIN
    assert "인터셉터 미주입" in CS and "매치 0건" in CS and "시그니처 미달" in CS
    assert "Tier1 동작" in CS                             # 기여 시 확인 로그
    assert "MAIN world 미응답" in CS                       # 타임아웃 폴백도 원인 로그
    assert "tier1_source" in CS                            # 채택 URL 전파


# ── STEP2: 서버 sanity 봉인 ───────────────────────────────────
def test_sanitize_price_discards_insane():
    from src.collectors.collect_sanitize import sanitize_price
    assert sanitize_price("9", "KRW")[0] == ""            # 9 KRW → 값 폐기(저장 금지)
    assert sanitize_price("9", "KRW")[1] == "needs_check"
    assert sanitize_price("500", "")[0] == ""             # 통화 미상 → 폐기
    assert sanitize_price("20605", "KRW")[0] == "20605"   # 정상 유지
    assert sanitize_price("12.99", "USD")[0] == "12.99"


def test_sanitize_images_domain_dedup():
    from src.collectors.collect_sanitize import sanitize_images
    r = sanitize_images(["https://t/a.jpg", "https://t/logo.png", "data:x", "https://t/a.jpg", "https://t/b.jpg", "/rel.jpg"])
    assert r == ["https://t/a.jpg", "https://t/b.jpg"]    # logo·data·상대·중복 제외


def test_e2e_extension_9krw_discarded():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension",
                       data=json.dumps({"url": "https://www.temu.com/kr/x-g-1.html", "title": "책상",
                                        "price": "9", "currency": "KRW",
                                        "images": ["https://img.temu.com/a.jpg", "https://img.temu.com/logo.png", "https://img.temu.com/a.jpg"]}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            it = ch.get(r.get_json()["item_id"], seller_ids={"u1"})
            assert it["price"] in ("", None)              # 9 폐기(저장 안 됨)
            ex = json.loads(it["extra_json"])
            assert ex.get("price_status") == "needs_check"
            assert len(ex.get("images", [])) == 1         # logo 제외 + 중복 제거
            # 상태 배지: 가격 누락 + 값 9 아님(정합)
            srcs = {f["key"]: f["ok"] for f in ex["collect_status"]["fields"]}
            assert srcs["price"] is False                 # 가격 present 아님(9 저장 안 함)


def test_manifest_bumped():
    # 숫자 semver 비교(문자열 비교는 1.5.110 < 1.5.56 오판 — 3자리 패치 대응).
    assert tuple(int(x) for x in MANIFEST["version"].split(".")) >= (1, 5, 56)
