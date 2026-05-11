# SIDEBAR 운영 가이드 (Phase 145)

- 셀러 사이드바: `src/seller_console/templates/_base.html`
- admin 사이드바: `src/dashboard/admin_views.py` (`_BASE_HTML`, `_DIAGNOSTICS_TEMPLATE`)
- 그룹 표시 토글: `SIDEBAR_GROUPED=1`
- 새 셀러 메뉴 추가 시:
  1. `_base.html` 링크 추가
  2. `src/dashboard/admin_views.py`의 `SELLER_SIDEBAR_LINKS` 동기화
  3. `tests/test_sidebar_menu.py` 갱신
