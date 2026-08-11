"""tests/test_v86_q_env_exposure_sweep.py — v86-Q: 셀러 화면 개발표기(env-var·내부 문서경로) 정직 스윕.

v86-P(알림) 외 잔여 셀러 노출 개발표기 triage 후 실 누출 제거:
- sourcing: 국내 베스트셀러 빈 상태에 `NAVER_SEARCH_CLIENT_ID/SECRET` 노출 → 평문.
- markets_guide: 내부 저장소 문서경로 `docs/operations/LIVE_VERIFICATION_GUIDE.md` 노출 → 평문 안내.
- pricing_console: 환율 출처 라벨 '환경변수'(개발 용어) → '설정값'.

보존(정직·유용): markets_connect의 `MARKET_CRED_ENC_KEY`는 '?' 툴팁(data-bs-title) 안(고급 안내,
v5 선례) / markets_guide의 마켓 실제 에러코드(GW.IP_NOT_ALLOWED 등)는 셀러 트러블슈팅에 필요.
"""
from __future__ import annotations

from pathlib import Path

TPLDIR = Path("src/seller_console/templates")
SOURCING = (TPLDIR / "sourcing.html").read_text(encoding="utf-8")
GUIDE = (TPLDIR / "markets_guide.html").read_text(encoding="utf-8")
PRICING = (TPLDIR / "pricing_console.html").read_text(encoding="utf-8")
CONNECT = (TPLDIR / "market_connect.html") if (TPLDIR / "market_connect.html").exists() else (TPLDIR / "markets_connect.html")
CONNECT_TXT = CONNECT.read_text(encoding="utf-8")


def test_sourcing_no_raw_env_var_names():
    assert "NAVER_SEARCH_CLIENT_ID" not in SOURCING and "NAVER_SEARCH_CLIENT_SECRET" not in SOURCING
    # 정직한 빈 상태 안내는 유지.
    assert "아직 연결되지 않았어요" in SOURCING
    assert "가짜 수치는 표시하지 않습니다" in SOURCING


def test_markets_guide_no_internal_doc_path():
    assert "LIVE_VERIFICATION_GUIDE" not in GUIDE
    assert "docs/operations/" not in GUIDE
    # 마켓 실제 에러코드(트러블슈팅용)는 유지.
    assert "GW.IP_NOT_ALLOWED" in GUIDE


def test_pricing_console_fx_label_not_dev_term():
    # 환율 출처 사용자 라벨이 '환경변수'(개발 용어)가 아니어야 한다.
    i = PRICING.find("srcLabel")
    seg = PRICING[i:i + 200]
    assert "'환경변수'" not in seg and '"환경변수"' not in seg
    assert "설정값" in seg


def test_markets_connect_enc_key_stays_tooltip_gated():
    # MARKET_CRED_ENC_KEY는 제거가 아니라 '?' 툴팁(data-bs-title) 안에만 존재(고급 안내).
    assert "MARKET_CRED_ENC_KEY" in CONNECT_TXT
    i = CONNECT_TXT.find("MARKET_CRED_ENC_KEY")
    # 그 등장 위치가 data-bs-title(툴팁) 속성 안이어야 한다(본문 노출 아님).
    before = CONNECT_TXT[max(0, i - 400):i]
    assert "data-bs-title" in before, "MARKET_CRED_ENC_KEY가 본문에 노출(툴팁 밖)"
