# 외부 공급자 응답 픽스처 (Z3-B)

- `onebound_item_get_652874751412.json` — **오너 실측 응답 원문**(2026-10-05 [Z3-B 후속] 투입, 첨부 txt의 Result Object 그대로).
  오너 기대값: error_code 0000 · price 480.00 · item_imgs 5 · desc_img 20(o0b.cn 픽셀 제거 후 19) · 축 2(几人坐 8 / 颜色分类 1) ·
  SKU 8 · tmall false · shop_name 佑安居 · cache 1 · data_update 2026-10-04 20:54:24 · api_info max 10 / expires 2026-10-08.
  계약: `tests/test_z3_onebound.py::test_real_652874751412_parses_as_owner_counted`.
  실측으로 확인된 모양: `prop_imgs.prop_img[] = [{"properties": "pid:vid", "url": …}]` · `props_img = {"pid:vid": url}` — 둘 다 http://로 올 수 있음.
- `onebound_item_get_reconstructed.json` — **재구성**(값은 지어낸 것) — 실측에 없는 갈래(캐시 하루 이내·SKU 재고 0·
  error_code 실패·5xx 재시도 등) 로직 계약용. 키 모양은 위 실측과 같다.
- 진단 `/admin/diagnostics/taobao-provider`의 「원문 내려받기」(키 가림)로 받은 파일도 같은 모양이다.
