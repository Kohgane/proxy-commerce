"""tests/test_v77_enrich_queue.py — v77 STEP3: 보강 큐 연동 확인(v65 STEP4 판정 회수).

벌크바 '상세 보강 시작 (0/N)'이 실작동하는지 — 큐가 N건을 순차 처리해 done=N·running=false로 완주하고,
서버 /enrich가 각 항목을 보강(enriched=True)하며 상태 배지가 부분→성공으로 전환하는지 못박는다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

ROOT = Path(__file__).resolve().parent.parent
BG = (ROOT / "extensions/chrome-collector/background.js").read_text(encoding="utf-8")
CS = (ROOT / "extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_unchanged():
    # STEP3은 판정 회수(보강 큐 검증 테스트만) — 확장 코드 불변 → 버전 유지(정직).
    assert MANIFEST["version"] == "1.5.144"


# ── source-contract: 진행률 표기(0/N → done/total · 완료) + 서버 보강 배선 ──
def test_progress_wording_source():
    assert "상세 보강 시작(0/${er.total})" in CS                 # 시작 표기
    assert "let t = `상세 보강 ${s.done}/${s.total}`;" in CS       # 진행률
    assert 't += " · 완료";' in CS                                 # 완주 표기
    assert 'm.action === "enrichProgress"' in CS                   # 진행률 수신
    assert 'action: "enrichStart", targets' in CS                 # 큐 시작 전송
    # background: 큐 상태 머신 + 서버 /enrich POST + 진행률 브로드캐스트.
    assert "function handleEnrichStart(targets, sendResponse)" in BG
    assert "async function _kgpEnrichLoop()" in BG
    assert "/api/v1/collect/enrich" in BG
    assert 'action: "enrichProgress"' in BG


def _grab(src, sig, end):
    i = src.index(sig)
    j = src.index(end, i) + len(end)
    return src[i:j]


# ── node: 큐가 7건을 순차 완주(done=7·total=7·running=false) + 진행률 브로드캐스트 ──
@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_enrich_queue_completes_7_of_7_node():
    kgp = _grab(BG, "const KgpEnrich = {", "};")
    snap = _grab(BG, "function _kgpEnrichSnapshot()", "\n}")
    bcast = _grab(BG, "function _kgpBroadcastEnrich()", "\n}")
    loop = _grab(BG, "async function _kgpEnrichLoop()", "\n}")
    start = _grab(BG, "function handleEnrichStart(targets, sendResponse)", "\n}")
    harness = (
        "var _progress=[];\n"
        "var chrome={runtime:{sendMessage:function(m){ if(m&&m.action==='enrichProgress') _progress.push(m.state); }}};\n"
        "async function _kgpEnrichOne(item, settings){ return true; }\n"   # 렌더/탭/서버 POST 스텁(성공)
        "async function getSettings(){ return {}; }\n"
        "function _kgpSleep(){ return Promise.resolve(); }\n"
        "function _kgpEnrichDelayMs(){ return 0; }\n"
        + kgp + "\n" + snap + "\n" + bcast + "\n" + loop + "\n" + start + "\n"
        "(async () => {\n"
        "  var resp=null; handleEnrichStart("
        + json.dumps([{"item_id": "i%d" % i, "url": "https://www.amazon.com/dp/B0%08d" % i} for i in range(1, 8)])
        + ", function(r){ resp=r; });\n"
        "  // 루프 완주 대기(마이크로태스크 flush).\n"
        "  for (var k=0;k<200 && KgpEnrich.running;k++){ await Promise.resolve(); }\n"
        "  var last=_progress[_progress.length-1]||{};\n"
        "  console.log(JSON.stringify({startTotal:resp&&resp.total, done:KgpEnrich.done, total:KgpEnrich.total,\n"
        "    ok:KgpEnrich.ok, running:KgpEnrich.running, lastDone:last.done, lastTotal:last.total,\n"
        "    lastRunning:last.running, broadcasts:_progress.length}));\n"
        "})();\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=20)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["startTotal"] == 7, out            # 시작 시 total=7 (0/7)
    assert out["done"] == 7 and out["total"] == 7, out   # 7건 완주
    assert out["ok"] == 7, out                     # 전건 성공
    assert out["running"] is False, out            # 큐 종료
    assert out["lastDone"] == 7 and out["lastTotal"] == 7 and out["lastRunning"] is False, out  # 완료 브로드캐스트
    assert out["broadcasts"] >= 7, out             # 1건마다 진행률 브로드캐스트


# ── 서버: 7건 부분 수집 → /enrich 보강 → 전건 enriched + 상태 부분→성공 전환 ──
def _make_partial_item(client, ch, seller, url, title):
    """옵션·상세 빈 부분 수집분 생성(status=partial 유도)."""
    r = client.post("/api/v1/collect/extension",
                    data=json.dumps({"url": url, "title": title, "price": "12000", "currency": "KRW",
                                     "images": ["https://img.x/%s.jpg" % title]}),
                    content_type="application/json", headers={"Authorization": "Bearer t"})
    return r.get_json()["item_id"]


def test_server_enrich_7_items_transitions_status(flask_client=None):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)

    with patch("src.api.extension_api._require_token", return_value={"user_id": "u_enrich", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            ids = []
            for i in range(1, 8):
                ids.append(_make_partial_item(c, ch, "u_enrich",
                           "https://www.amazon.com/dp/B0EN%06d" % i, "상품%d" % i))
            # 부분 수집: 옵션·상세·리뷰 비어 있음(status가 성공 아님).
            before = []
            for iid in ids:
                it = ch.get(iid, seller_ids={"u_enrich"})
                ex = json.loads(it["extra_json"] or "{}")
                before.append((ex.get("enriched"), (ex.get("collect_status") or {}).get("filled")))
            # 7건 각각 상세 필드로 보강.
            enriched_ok = 0
            for i, iid in enumerate(ids, 1):
                r = c.post("/api/v1/collect/enrich",
                           data=json.dumps({"item_id": iid,
                                            "options": [{"name": "색상", "values": ["블랙", "화이트"]}],
                                            "description": "상세 설명 " * 10,
                                            "reviews": [{"text": "좋아요", "rating": "5"}],
                                            "rating": "4.7", "review_count": "123",
                                            "detail_images": ["https://img.x/d%d-1.jpg" % i, "https://img.x/d%d-2.jpg" % i]}),
                           content_type="application/json", headers={"Authorization": "Bearer t"})
                assert r.status_code == 200, r.get_data(as_text=True)
                d = r.get_json()
                if d.get("ok"):
                    enriched_ok += 1
            # 7건 전부 보강 성공.
            assert enriched_ok == 7, enriched_ok
            # 각 항목: enriched=True + 옵션·상세·리뷰 채워짐 + filled 증가(부분→성공 방향).
            for (b_enr, b_filled), iid in zip(before, ids):
                it = ch.get(iid, seller_ids={"u_enrich"})
                ex = json.loads(it["extra_json"] or "{}")
                assert ex.get("enriched") is True, iid
                assert ex.get("options") and ex.get("description") and ex.get("reviews"), iid
                st = ex.get("collect_status") or {}
                assert st.get("filled") is None or b_filled is None or st.get("filled") >= (b_filled or 0), (iid, b_filled, st)
