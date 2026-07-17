# 디폴트 소싱처 커버리지 매트릭스 (v75 STEP1)

> 근거는 **실페이지 하네스 픽스처**(`fixtures/realpages/<fixture>.expected.json`)의 실제 어서션뿐이다.
> 추측 기입 금지 — 픽스처 없는 마켓은 '픽스처 필요'(오너 스냅샷 제출 후 하네스 검증).
> 버튼 3열(목록·호버·상세)은 **제네릭 타일 감지**로 전 사이트 보장(v70/v74). 추출 6열은 하네스 검증분만 ✓.

| 마켓 | 도메인 | 목록 | 호버 | 상세 | 제목 | 가격+통화 | 갤러리 | 옵션 | 상세 | 리뷰 | 지원수준 | 근거 픽스처 |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| 타오바오 | taobao.com | ✓ | ✓ | ✓ | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 미검증 | — |
| 티몰 | tmall.com | ✓ | ✓ | ✓ | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 미검증 | — |
| 1688 | 1688.com | ✓ | ✓ | ✓ | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 미검증 | — |
| 테무 | temu.com | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 미검증 | 완전 지원 | synthetic-temu-detail |
| 아마존 | amazon.com · amazon.co.jp 등 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 미검증 | 완전 지원 | synthetic-amazon-dp |
| 알리익스프레스 | aliexpress.com · aliexpress.us | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 미검증 | 미검증 | 부분 지원 | ali-detail |
| 아이허브 | iherb.com | ✓ | ✓ | ✓ | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 미검증 | — |
| DHgate | dhgate.com | ✓ | ✓ | ✓ | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 미검증 | — |
| 큐텐 | qoo10.* | ✓ | ✓ | ✓ | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 미검증 | — |
| 메루카리 | mercari.com | ✓ | ✓ | ✓ | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 미검증 | — |
| 라쿠텐 | rakuten.co.jp · rakuten.com | ✓ | ✓ | ✓ | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 미검증 | — |
| 야후쇼핑(재팬) | shopping.yahoo.co.jp · paypaymall.yahoo.co.jp | ✓ | ✓ | ✓ | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 미검증 | — |
| 요시다카반 | yoshidakaban.com | ✓ | ✓ | ✓ | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 픽스처 필요 | 미검증 | — |

## 오너 스냅샷 요청 목록 (미검증 마켓)
각 사이트의 **상품 상세 1곳**에서 확장 팝업 '진단 스냅샷 저장'으로 스냅샷을 커밋하면 하네스 계약을 추가한다.

- [ ] **타오바오** (`taobao.com`) → `fixtures/realpages/taobao-detail.html` + `.expected.json`
- [ ] **티몰** (`tmall.com`) → `fixtures/realpages/tmall-detail.html` + `.expected.json`
- [ ] **1688** (`1688.com`) → `fixtures/realpages/1688-detail.html` + `.expected.json`
- [ ] **아이허브** (`iherb.com`) → `fixtures/realpages/iherb-detail.html` + `.expected.json`
- [ ] **DHgate** (`dhgate.com`) → `fixtures/realpages/dhgate-detail.html` + `.expected.json`
- [ ] **큐텐** (`qoo10.*`) → `fixtures/realpages/qoo10-detail.html` + `.expected.json`
- [ ] **메루카리** (`mercari.com`) → `fixtures/realpages/mercari-detail.html` + `.expected.json`
- [ ] **라쿠텐** (`rakuten.co.jp · rakuten.com`) → `fixtures/realpages/rakuten-detail.html` + `.expected.json`
- [ ] **야후쇼핑(재팬)** (`shopping.yahoo.co.jp · paypaymall.yahoo.co.jp`) → `fixtures/realpages/yahoo-detail.html` + `.expected.json`
- [ ] **요시다카반** (`yoshidakaban.com`) → `fixtures/realpages/yoshida-detail.html` + `.expected.json`

## 수리 우선순위 (× 칸 중 3핵심=제목·가격·갤러리 미달)
픽스처 도착 순서대로 마켓당 1커밋(하네스 계약 동반)으로 어댑터/제네릭 보강. 현재 검증 완료: **아마존·테무(완전), 알리(부분·상세/리뷰 남음)**.

> 이 파일은 `src/collectors/sourcing_registry.py`의 coverage 데이터에서 파생(수기 편집 금지). 재생성: `python scripts/gen_coverage_matrix.py`.
