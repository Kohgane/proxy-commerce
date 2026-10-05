# Z3-B — 타오바오 상세: 온바운드(万邦) item_get

## 왜
익명 mtop(h5api getdetail)은 **로그인 요구**(`login_required`)로 막힌다 — 프록시(한국 주거)·폰 LTE·집 PC 모두 같은
`login_jump` 스크립트(오너 실측 2026-10-05). IP 문제가 아니라 mtop 자동 경로는 보류(코드는 그대로 — Z3-L 로그인 쿠키 경로에서 재사용, `docs/z3-l.md`).

## 비용·계정
- 단가 **0.023元/회**. 체험 키: **하루 10회**, 2026-10-08 만료(응답 `api_info`에 「today: max:10 … expires:2026-10-08」).
- `lang=zh-CN` 고정 — 다른 언어는 번역 과금. 번역은 우리 체인(Papago·텐센트).

## env
| 이름 | 뜻 |
|---|---|
| `TAOBAO_DETAIL_PROVIDER` | `mtop`(기본) · `onebound`. onebound면 이 설정만으로 담기 자동 수집이 켜진다(`TAOBAO_MTOP_AUTO` 불필요·건드리지 않음) |
| `ONEBOUND_KEY` · `ONEBOUND_SECRET` | 비면 부팅 경고 + 담기 건은 「공급자 키 미설정」 수동 카드(mtop으로 조용히 안 감). 값은 로그·화면에 안 남김 |
| `ONEBOUND_DAILY_CAP` | 기본 60 — **계정 전체** 하루 호출 상한(`cache=no` 재호출도 1회로 셈). 넘으면 호출 전에 「온바운드 일일 한도」 보류 |

## 흐름
폰 담기(share `?text=`) → 상품번호(e.tb.cn은 기존 해석 재사용 — 실패면 「상품번호 해석 실패」) → item_get → 정규화 →
기존 병합(`apply_enrich`) → 담았어요/M5 카드. 실패는 (c) 수동 카드(사진 추가·옵션 직접 입력) — **mtop 재시도 없음**.
그 뒤 체인(Y6 제목·Y2/Y8 옵션·이미지 번역 예산·Y7·Z5 배송비)은 손대지 않았다 — 같은 키로 들어간다.

## 호출 규칙
- 타임아웃 15초. 재시도는 **5xx·타임아웃만 1회**. 4xx·`error_code`≠`"0000"`은 재시도 0, `reason`/`error` 원문을 그대로 카드에.
- 호출마다 로그: num_iid · HTTP · error_code · cache · execution_time · 응답 바이트 · ms.
- 원문 JSON 상품당 최신 1건 보관(app_state `onebound:raw:<상품번호>`). **같은 상품 24시간 안 재담기는 보관본 재사용**(호출 0).
  진단 「새로 받기」만 재호출.

## 캐시
캐시 우회 = **`cache=no`**(오너 실측 2026-10-05 — 테스트 페이지 「캐시 업데이트」 체크 시 Request address `…&is_promotion=1&cache=no&&lang=zh-CN&…`).
기본은 미지정 = 캐시 허용.
- 진단 「새로 받기」 → `cache=no`로 호출(유료 1회) · 보관본을 덮어쓴다.
- 자동 경로: 응답 `cache`=1이고 `data_update`(베이징 시각)가 24시간 넘었을 때만 `cache=no`로 **1회** 재호출 — 일일 한도에 1회로 더한다.
  재호출이 실패하면 받은 캐시 값을 쓰고 카드에 「가격 기준 {data_update}」.
- 24시간 보관본 재사용 규칙은 그대로(「새로 받기」만 건너뜀).

## 타입 관용(실측 1호·2호 차이)
total_sold·sales: int/str 모두 정수로(참고만) · video.url null → 「동영상 없음」 · post_fee·express_fee·ems_fee·freight·item_weight:
null·""·0 → **「미기재」**(Z5 배송비 계산에 0으로 넣지 않음) · brand `other/其他` → 브랜드 없음(Y6·상품명에 안 넘김) ·
prop_imgs 없으면 props_imgs(복수형) · desc_img 비면 desc(html) `<img src>`(o0b.cn 제외) · 모르는 키는 무시하되 보관 원문엔 남김.

## 상품번호 검사(캐시 오염 방어)
응답 `item.num_iid` ≠ 요청 `num_iid`(또는 응답에 없음)면 **실패**(「온바운드 응답 상품번호 불일치(요청 … ≠ 응답 …)」) — 보관도 안 한다.
24시간 보관본을 재사용할 때도 같은 검사를 지난다.

## 필드 매핑(오너 지시)
title · price/orginal_price → price_cny/original_price_cny(float) · pic_url+item_imgs[].url → images(https 보정) ·
desc_img → 상세 이미지(o0b.cn 추적 픽셀·Y1 쓰레기 제외) · desc(html) 파싱 안 함 · props[] → 규격표(`detail_specs`, Z5 무게·치수 재료,
五孔/国标插座 판정에도 포함) · props_list + skus.sku[].properties → 축별 값·SKU 가격/재고(properties_name 안 씀) ·
prop_imgs.prop_img[{properties, url}] + props_img{pid:vid: url} → 옵션값 사진(http:// → https://, 실측 확인) · video.url · location(표기만) · tmall · seller_info.shop_name/nick · num(총재고).
sales/total_sold는 안 믿는다.

## 진단
`/admin/diagnostics/taobao-provider` — e.tb.cn 링크·상품번호 → 원문(키 가림) · 정규화 결과 · 캐시·data_update · api_info 한도/만료 ·
오늘 호출 수/CAP · 「새로 받기」 · 원문 내려받기. mtop 실측(`/admin/diagnostics/taobao-mtop`)은 판정 코드
(`login_required` · `rgv587` · `x5_loop` · `ok`)와 출구 IP 줄.

## Y8 전압·플러그(온바운드 상품에서 처음 실측 — 667810641388 제습기)
옵션 값의 110V·220V·100V·110-220V와 国内用·美规·英规·澳规·欧规… 토큰을 「전압/플러그」 축으로 분리(`src/collectors/voltage_plug.py`).
국내 마켓(쿠팡 고가네·우주대행·스마트스토어·11번가)만: 110V(·100V) 전용·플러그 G/A/I형 SKU는 등록에서 빠지고(M5 회색 줄),
220V+중국 플러그 SKU가 하나라도 있으면 상세 **맨 위**에 플러그 안내 + 표준 구매대행 고지(문구 = `src/seller_console/notice_texts.py`).
모든 SKU가 제외면 「전압/플러그 불일치」 보류 → 「그래도 등록」. 멀티탭 자체(五孔·国标插座)는 별개 규칙 그대로.
