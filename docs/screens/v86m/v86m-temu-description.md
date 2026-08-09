# v86-M — 테무 상세설명(goodsProperty) 수집

## 진단 (오너 실기기 파일, 1.5.142 · commit db177c4)
`payload_echo=null`은 이 스냅샷이 수집 클릭 없이 저장돼 예상된 값(경로 계약은 정상). **실질 신호는
extracted**:

| 필드 | 값 | 소스 |
|---|---|---|
| price | **12730 KRW** | tier1 |
| images | **8** | tier1 |
| options | 1 (검정) | tier1 |
| reviews | **10** | tier1 |
| **description** | **빈값** | **none** |

→ 오너 최초 P0("price=0·title만")는 **이미 해소**. 남은 실결함은 **상세설명 하나**. tier1 계측:
seen 29·hits 3·goods_ids 40·pending false — tier1 정상 착지.

## 근본
추출기 `_fromJson` 워커가 **테무 goodsProperty(스펙 배열 `[{key, values[]}]`)를 안 읽어** specs가
비고, 기존 **specs→상세설명 사다리**가 안 탔다. (title/price/images/options/reviews 케이스는 있는데
스펙표 케이스만 없었다.)

## 수리
워커에 goodsProperty(·유사 productproperty/paramproperty/attributelist) → `res.specs` 케이스 추가.
`{key, values[]}` → `{k, v}`. 그러면 기존 `specs`→`description` 사다리가 상세를 채운다(신규 로직 0,
기존 사다리 재사용). manifest 1.5.142→**1.5.143**.

**오너 실스냅샷 재현(로컬 jsdom, 실제 캡처):** 상세설명 = **스펙 37개 클린 추출**
`전원 모드: USB 충전 · 작동 전압: ≤36V · 배터리 용량(mAh): 800 · 제품 충전 포트: Type-C · 최대 정격 출력: 18W · 부피/중량 …` (before: none).

## 판정
- **실페이지 하네스(CI 게이트)** `temu-goodsproperty` 픽스처 신설 — 실브라우저(Playwright)로 상세설명
  스펙표 채움 고정(`description_contains: "전원 모드"`). 상태는 실제 테무처럼 `window.rawData` JSON.
  `test_v70_realpage_harness` **15 passed**.
- 가드 `test_v86_m_temu_desc`(3): 워커 케이스 소스계약 + 픽스처 계약 + 버전.
- **추출 회귀 0:** realpage·extract-contract·currency·detail_images·desc_priority·desc_filler·yoshida·
  ali·amazon **47 passed**.
- **인위회귀:** goodsProperty 케이스 무력화 → 가드 + temu 픽스처 RED(상세 빈값=오너 결함 재현, 타 14
  픽스처 무영향) → 원복 18 passed.

## 참고(후속 별건)
- `detection.adopted=null`(v86-K 계측): adopted 리더가 MAIN world(kgp-net)에서 ISOLATED world의 tier1
  전역을 읽어 항상 비는 브릿지 결함. **진단 전용**(추출 무영향) — 별도 STEP.
- 추출기 변경 규칙(v70 STEP5) 준수: 실페이지 하네스 그린 확인 후 머지.
