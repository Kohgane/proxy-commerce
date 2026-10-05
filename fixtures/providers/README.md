# 외부 공급자 응답 픽스처 (Z3-B)

- `onebound_item_get.json` — **재구성**(2026-10-05). onebound 문서(open.onebound.cn)는 이 컨테이너에서 egress 차단이라
  원문 대조를 못 했다. 키는 웹 검색 결과로 확인된 것만 썼다(`src/collectors/taobao_provider.py`의 `FIELDS_SOURCE`).
  값(제목·가격·SKU)은 지어낸 것.
- **교체 방법:** 키를 넣고 `/admin/diagnostics/taobao-mtop?via=provider`로 1건 실측 → 화면의 「item_get 실응답 내려받기」
  (키·시크릿은 가려서 저장됨)를 이 파일로 덮어쓰고 `pytest tests/test_z3b_provider.py`. 모양이 다르면 파서 테스트가 먼저 깨진다.
