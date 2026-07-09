"""tests/test_v49_sg_migration.py — v49 STEP1: 싱가포르 이관 준비(render.yaml + 체크리스트).

render.yaml에 region:singapore·plan:starter 신규 서비스 + DATABASE_URL sync:false + healthCheckPath.
이관 문서는 키명만(값 절대 기재 금지). 코드에 인프라 리전·IP 하드코딩 없음(DATABASE_URL만).
"""
from __future__ import annotations

from pathlib import Path

import yaml


def test_render_yaml_has_singapore_starter_service():
    d = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    svcs = {s["name"]: s for s in d["services"]}
    assert "proxy-commerce-sg" in svcs, "싱가포르 신규 서비스 없음"
    sg = svcs["proxy-commerce-sg"]
    assert sg["region"] == "singapore"
    assert sg["plan"] == "starter"
    assert sg["healthCheckPath"] == "/health"
    # 기존 서비스는 건드리지 않음(회귀)
    assert "proxy-commerce" in svcs and svcs["proxy-commerce"]["region"] == "virginia"


def test_sg_service_has_db_env_sync_false():
    d = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    sg = {s["name"]: s for s in d["services"]}["proxy-commerce-sg"]
    env = {e["key"]: e for e in sg["envVars"]}
    # DB·세션·암호화 키는 값 없이 sync:false(오너 입력)
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT", "SECRET_KEY", "MARKET_CRED_ENC_KEY"):
        assert k in env, f"{k} 누락"
        assert env[k].get("sync") is False, f"{k} 는 sync:false 여야(값 하드코딩 금지)"
        assert "value" not in env[k], f"{k} 에 값이 하드코딩됨"
    # DB는 그대로(값 불변) — render.yaml에 DB 접속 문자열 리터럴 없음(주석의 포트 언급은 무관)
    raw = Path("render.yaml").read_text(encoding="utf-8")
    assert "postgresql://" not in raw and "postgres://" not in raw and ".supabase.co" not in raw


def test_migration_doc_keys_only_no_secret_values():
    doc = Path("docs/migration_sg_v1.md").read_text(encoding="utf-8")
    # 절차·검증 항목 존재
    assert "Blueprint" in doc and "singapore" in doc.lower()
    assert "CNAME" in doc and "Suspend" in doc            # DNS 전환 + 구 서비스 정리
    assert "/health" in doc and "로그인" in doc and "수집 1건" in doc and "드로어" in doc
    assert "DATABASE_URL" in doc and "MARKET_CRED_ENC_KEY" in doc
    # 값 기재 금지 원칙 명시
    assert "값" in doc and ("절대" in doc or "키명만" in doc)
    # 흔한 비밀값 패턴이 문서에 없어야(키명만) — postgres 접속 문자열/Bearer 등
    assert "postgresql://" not in doc and "postgres://" not in doc
    assert "sk-" not in doc and "shpat_" not in doc and "Bearer " not in doc


def test_no_hardcoded_infra_region_or_ip_in_code():
    # 인프라 리전/DB IP 하드코딩 없음 — DATABASE_URL 환경변수만 사용.
    import subprocess
    out = subprocess.run(
        ["grep", "-rnE", r"postgresql://|postgres://|\.supabase\.co|ap-southeast-1", "src/"],
        capture_output=True, text=True,
    )
    # 접속 문자열/리전 하드코딩 라인 0(주석·문서 제외 src 코드)
    hits = [ln for ln in out.stdout.splitlines() if ln and "test" not in ln.lower()]
    assert not hits, f"인프라 접속 하드코딩 발견: {hits[:5]}"
