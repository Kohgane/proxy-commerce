# CI Hardening (Phase 153)

- 머지 충돌 마커 검사: `src/`, `tests/`, `templates/`, `static/`
- Python 사전 컴파일: `python -m compileall src/ -q`
- pytest collect 게이트: `python -m pytest --collect-only -q`

목적: 충돌 마커/문법 오류를 배포 전에 즉시 차단한다.
