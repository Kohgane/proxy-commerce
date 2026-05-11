# SIDEBAR_ROUTE_MATRIX (Phase 146)

- 목적: 사이드바에 노출된 링크가 실제 라우트로 등록되어 있는지 회귀 방지.
- 테스트: `tests/test_sidebar_route_matrix.py`
  - 셀러 대시보드 HTML에 링크 존재 여부 검증
  - 각 링크 GET 시 404 아님 검증
- 진단 카드: `/admin/diagnostics`의 "라우트 매트릭스 (Phase 146)"
