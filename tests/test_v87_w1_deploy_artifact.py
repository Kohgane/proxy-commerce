"""tests/test_v87_w1_deploy_artifact.py — v87-W1 배포 아티팩트 게이트 (완료 조건 5항).

갭 인정: 운영자가 Render Shell에서 실행하는 산출물(scripts/hygiene_report.py)이 Dockerfile에
개별 COPY되지 않아 배포 이미지 /app 에서 누락됐다(오너 실증). 예전 #423(migrate)과 같은 유형.
수리: scripts/ 통째 COPY로 재발 봉인 + 이 가드로 '배포 이미지에 산출물 존재'를 계약화한다.
(운영 컨테이너 경로 실증 `ls`는 오너 배포 후 1줄로 확인 — 이 가드는 이미지 빌드 계약을 못박음.)
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

DOCKERFILE = Path("Dockerfile").read_text(encoding="utf-8")
DOCKERIGNORE = Path(".dockerignore").read_text(encoding="utf-8") if Path(".dockerignore").exists() else ""
CI_DOCKER = Path(".github/workflows/render_deploy_check.yml").read_text(encoding="utf-8")

# 배포 이미지에 반드시 있어야 하는 운영 스크립트(오너가 Render Shell에서 실행).
OPERATIONAL = ["hygiene_report.py", "qa_test_order.py", "persistence_check.py",
               "migrate_to_supabase.py", "start_render.sh"]


def _dockerignore_patterns():
    return [l.strip() for l in DOCKERIGNORE.splitlines() if l.strip() and not l.strip().startswith("#")]


def _is_ignored(relpath: str) -> bool:
    # .dockerignore 간이 매칭(경로/베이스명 글롭).
    for pat in _dockerignore_patterns():
        p = pat.rstrip("/")
        if fnmatch.fnmatch(relpath, p) or fnmatch.fnmatch(relpath, p + "/*") \
           or fnmatch.fnmatch(Path(relpath).name, p) or relpath == p:
            return True
    return False


def test_dockerfile_copies_whole_scripts_dir():
    assert "COPY scripts/ " in DOCKERFILE, "Dockerfile이 scripts/를 통째 COPY하지 않음(개별 COPY 누락 갭)"


def test_operational_scripts_not_ignored():
    # 운영 스크립트가 .dockerignore에 걸려 이미지에서 빠지면 안 된다(누락 재발 봉인).
    for f in OPERATIONAL:
        assert Path("scripts", f).exists(), f"scripts/{f} 없음(자산 부재)"
        assert not _is_ignored(f"scripts/{f}"), f"scripts/{f}가 .dockerignore에 걸림 → 이미지 누락"


def test_devshots_explicitly_excluded_not_implicit():
    # 개발 전용 devshot은 '명시 제외'돼야 한다(암묵 제외 금지). 패턴이 .dockerignore에 이름으로 존재.
    assert any("_devshot" in p for p in _dockerignore_patterns()), \
        "devshot 명시 제외 패턴이 .dockerignore에 없음"
    # 실제로 devshot 하나가 제외 매칭되는지 확인.
    assert _is_ignored("scripts/_devshot_v87w1_hygiene.py")


def test_ci_docker_job_asserts_artifacts_in_image():
    # 완료조건 5항: 빌드 이미지에서 운영 스크립트 존재를 ls로 실증하는 CI 스텝이 있어야 한다.
    assert "ls -1 /app/scripts/" in CI_DOCKER
    for f in OPERATIONAL:
        assert f in CI_DOCKER, f"CI Docker 스텝이 {f} 존재를 검증하지 않음"


def test_hygiene_report_script_present_and_read_only():
    src = Path("scripts/hygiene_report.py").read_text(encoding="utf-8")
    for bad in ("delete_ids", ".delete(", ".update(", ".append(", "bulk-delete", "DELETE FROM"):
        assert bad not in src, f"리포트 스크립트에 데이터 변경 의심: {bad}"
    assert "summarize_candidates" in src and "list_items" in src
