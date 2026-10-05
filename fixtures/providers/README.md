# 외부 공급자 응답 픽스처 (Z3-B)

- `onebound_item_get_652874751412.json` — **오너 실측 응답**(첨부 txt의 Result Object). ★아직 이 레포에 없음:
  2026-10-05 브리프 메시지에 원문이 실려 오지 않았다. 파일을 이 이름으로 넣으면 `tests/test_z3_onebound.py`의
  실측 계약(제목·가격 480.0·사진 5·상세 19·축 2(几人坐 8 / 颜色分类 1)·SKU 8·is_tmall False·가게 「佑安居」)이 돈다 —
  그 전엔 그 테스트는 **사유를 밝히고 건너뛴다**(그린으로 세지 않음).
  진단 `/admin/diagnostics/taobao-provider`의 「원문 내려받기」(키 가림)로 받은 파일도 같은 모양이다.
- `onebound_item_get_reconstructed.json` — **재구성**(값은 지어낸 것). 키 모양은 오너 지시(2026-10-05)의 필드 매핑을
  따른다: `props[]{name,value}` · `props_list{"pid:vid":"축:값"}` · `skus.sku[]{price,quantity,properties,sku_id}` ·
  `prop_imgs.prop_img[]` · `desc_img`(o0b.cn 추적 픽셀 1장 포함) · `video.url` · `location` · `tmall` · `seller_info.shop_name` ·
  `cache` · `data_update` · `api_info`. 단 `prop_img` 원소의 키(`properties`·`url`)는 지시에 이름이 없어 **확인 전**.
