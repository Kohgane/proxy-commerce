"""tests/test_v88_c_pilot_data_artifact.py — v88-C 파일럿 배포 아티팩트 게이트 (#423 동류 재발방지).

증상(오너 실측): 배포본 `/admin/coupang-pilot` 400 "pilot_population 없음" — Dockerfile이 data/를 COPY하지
않고 .dockerignore가 data/를 제외해 pilot_population.json·sourcing_map.json이 이미지에 부재.
계약: ① Dockerfile이 두 파일을 COPY ② .dockerignore가 두 파일을 재포함(!) ③ 파일이 레포에 실재.
"""
from __future__ import annotations

from pathlib import Path

DOCKERFILE = Path("Dockerfile").read_text(encoding="utf-8")
DOCKERIGNORE = Path(".dockerignore").read_text(encoding="utf-8")

_FILES = ["data/sourcing_map.json", "data/pilot_population.json"]


def test_dockerfile_copies_pilot_data():
    # data/ 통째 COPY는 런타임 junk 유입 위험 → 두 정적 파일만 명시 COPY.
    assert "COPY data/sourcing_map.json data/pilot_population.json ./data/" in DOCKERFILE


def test_dockerignore_reincludes_pilot_data():
    # data/ 제외 + 두 파일 재포함(!) — 순서상 재포함이 뒤에 와야 승.
    assert "\ndata/\n" in ("\n" + DOCKERIGNORE)
    for f in _FILES:
        assert f"!{f}" in DOCKERIGNORE, ("dockerignore 재포함 누락", f)


def test_pilot_data_files_present_in_repo():
    for f in _FILES:
        assert Path(f).is_file(), ("레포에 데이터 파일 부재", f)


def test_pilot_population_shape():
    import json
    d = json.loads(Path("data/pilot_population.json").read_text(encoding="utf-8"))
    assert d.get("count") == 396 and len(d.get("population") or []) == 396
    assert d.get("reduction", {}).get("distinct_sid") == 396


def test_smoke_asserts_data_in_image():
    # 배포 이미지 스모크가 /app/data/ 존재를 실증(암묵 신뢰 금지).
    smoke = Path(".github/workflows/render_deploy_check.yml").read_text(encoding="utf-8")
    assert "/app/data/$f" in smoke and "pilot_population.json" in smoke
