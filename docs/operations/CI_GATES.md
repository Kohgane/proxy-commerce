# CI_GATES (Phase 152)

추가된 필수 게이트:
- `tests/test_no_merge_conflict_markers.py`
  - `src/`, `templates/`, `tests/` 범위에서 `<<<<<<<`, `=======`, `>>>>>>>` 차단
- `tests/test_python_syntax_compiles.py`
  - `src/**/*.py` 전체 `py_compile` 사전 검증

목적:
- 머지 충돌 마커 유입으로 인한 부팅 실패 방지
- 문법 오류를 테스트 수집 이전 단계에서 빠르게 검출
