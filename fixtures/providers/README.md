# 외부 공급자 응답 픽스처 (Z3-B)

- `onebound_item_get_652874751412.json` — **오너 실측 응답 원문**(2026-10-05 [Z3-B 후속] 투입, 첨부 txt의 Result Object 그대로).
  오너 기대값: error_code 0000 · price 480.00 · item_imgs 5 · desc_img 20(o0b.cn 픽셀 제거 후 19) · 축 2(几人坐 8 / 颜色分类 1) ·
  SKU 8 · tmall false · shop_name 佑安居 · cache 1 · data_update 2026-10-04 20:54:24 · api_info max 10 / expires 2026-10-08.
  계약: `tests/test_z3_onebound.py::test_real_652874751412_parses_as_owner_counted`.
  실측으로 확인된 모양: `prop_imgs.prop_img[] = [{"properties": "pid:vid", "url": …}]` · `props_img = {"pid:vid": url}` — 둘 다 http://로 올 수 있음.
- `onebound_item_get_667810641388.json` — **오너 실측 2호 원문**(운영 Render 「내려받기」, client_ip = Render 출구). 제습기 —
  110V/220V × 미·영·호·국내 플러그 × 흑백 8 SKU(전 298元·재고 45~50) · cache 0 · api_info today 1/max 10/expires 2026-10-08 ·
  1호와 타입 차이(total_sold "6" · video.url null · 배송비/무게 null·"" · brand other/其他 · props_imgs 복수형 · 모르는 키 _ddf 등).
  계약: `tests/test_z3_onebound.py::test_real2_…` · Y8 전압·플러그 `tests/test_y8_voltage_plug.py`.
- `onebound_item_get_913382613725.json` — **오너 실측 3호 원문**(2026-10-07 운영 보관본 = 진단 「내려받기」와 같은 `mask`·`indent=1`.
  첨부가 세션에 닿지 않아 운영 DB `app_state onebound:raw:913382613725`(11:57:59 KST 저장, 이후 새로 받기 성공 0)에서 그대로 옮김 —
  jsonb 정본 md5 `8221231d3424075cc784ebe66d6cf52d` 일치 확인). 티몰 중고풍 티테이블·TV장 — tmall true · 축 2(安装方式 1값 +
  颜色分类 8값: 값 안 [50cm]/[60cm]/[80cm] 사이즈 · 茶几/电视柜 종류 혼합) · brand 亮妆（家俱） · 规格 毛重 40kg · 包装体积 0.36 ·
  尺寸 60x60x62m(오타 m) · desc_img ~crop~ 접미 6장 · total_sold "10"(str) · video.url 있음 · cache 0인데 data_update 2026-08-25.
  계약: `tests/test_z3d_fixture3_913382613725.py`(Y8 사이즈 축·종류 값 유지·섞임 경고 · Z5 毛重/包装体积 · Y1 crop · 가격 기준 · 브랜드).
- `onebound_item_get_reconstructed.json` — **재구성**(값은 지어낸 것) — 실측에 없는 갈래(캐시 하루 이내·SKU 재고 0·
  error_code 실패·5xx 재시도 등) 로직 계약용. 키 모양은 위 실측과 같다.
- 진단 `/admin/diagnostics/taobao-provider`의 「원문 내려받기」(키 가림)로 받은 파일도 같은 모양이다.
