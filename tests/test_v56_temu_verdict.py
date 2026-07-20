"""tests/test_v56_temu_verdict.py — v56 STEP4: 테무 Tier1 최종 판정(v55 결과 회수).

v55 MAIN 월드 인터셉터 감사(주입·버전) + Tier1 진단을 **payload에 동봉·서버 저장·드로어 표기**(콘솔 안 봐도
최종 판정 확인). tier1 미채택이면 진단 결과(원인)가 드로어에 남아 '어느 시그니처 미발견'을 지목.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
CS = (ROOT / "extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
API = (ROOT / "src/api/extension_api.py").read_text(encoding="utf-8")
TPL = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


def test_audit_main_interceptor_present():
    # v55 MAIN 인터셉터가 코드에 있음(main 병합 후) + 확장 버전 갱신.
    nets = [c for c in MANIFEST["content_scripts"]
            if c.get("world") == "MAIN" and c.get("run_at") == "document_start" and "kgp-net.js" in c.get("js", [])]
    assert nets, "kgp-net.js MAIN document_start 인터셉터 없음"
    # 숫자 semver 비교(문자열 비교는 1.5.106 < 1.5.56 오판 — 3자리 패치 대응).
    assert tuple(int(x) for x in MANIFEST["version"].split(".")) >= (1, 5, 56)
    assert Path("extensions/chrome-collector/kgp-net.js").exists()


def test_tier1_diag_attached_and_stored():
    assert "merged.tier1_diag =" in CS                    # 진단 결과 payload 동봉
    assert '"tier1_diag": payload.get("tier1_diag")' in API   # 서버 저장


def test_drawer_shows_tier1_verdict():
    assert "tier1_diag" in TPL and "Tier1 동작" in TPL and "Tier1 미동작" in TPL   # 드로어 판정 표기


def test_e2e_tier1_diag_persisted():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    payload = {"url": "https://www.temu.com/kr/x-g-1.html", "title": "책상", "price": "20605",
               "currency": "KRW", "images": ["https://img.temu.com/1.jpg"],
               "tier1_source": "https://temu.com/api/goods/detail",
               "field_sources": {"price": "tier1"},
               "tier1_diag": {"used": True, "netBound": True, "captured": 3, "topScore": 4,
                              "source": "https://temu.com/api/goods/detail", "cause": ""}}
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension", data=json.dumps(payload),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            ex = json.loads(ch.get(r.get_json()["item_id"], seller_ids={"u1"})["extra_json"])
    assert ex["tier1_diag"]["used"] is True and ex["tier1_diag"]["topScore"] == 4
    assert ex["tier1_source"] == "https://temu.com/api/goods/detail"
    # 미동작 케이스: 원인 저장(진단 표 지목)
    payload2 = dict(payload, tier1_source="", field_sources={"price": "tier2"},
                    tier1_diag={"used": False, "netBound": True, "captured": 0, "topScore": 0,
                                "source": "", "cause": "매치 0건(상품 API 응답을 아직 못 잡음)"})
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c2"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension", data=json.dumps(dict(payload2, url="https://www.temu.com/kr/y-g-2.html")),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            ex2 = json.loads(ch.get(r.get_json()["item_id"], seller_ids={"u1"})["extra_json"])
    assert ex2["tier1_diag"]["used"] is False and "매치 0건" in ex2["tier1_diag"]["cause"]
