# v63 STEP2 — 필드 손실 지도 → 정밀 타격 + 품질 게이트

## 원칙
- **매트릭스 먼저, 추측 서술 금지.** 수집 시 서버가 기록한 `collect_status`(필드별 present + 채택 tier)만 집계한다.
- **매트릭스 없는 추출 로직 변경 금지** — 이 STEP은 측정 도구(매트릭스 집계 + 품질 게이트)만 추가하고 추출 로직은 건드리지 않는다. 실제 필드 수리는 라이브 매트릭스가 상위 손실을 지목한 뒤 다음 STEP에서.

## 신설 — `src/collectors/field_loss_matrix.py`
- `domain_of(url)` — 도메인 정규화(amazon·temu·aliexpress·taobao·tmall·1688·yahoo·yoshida·기타).
- `build_field_loss_matrix(items)` — 저장 `collect_status.fields`를 도메인별로 집계 → **[필드 × tier × 결과]**:
  - `field_present[field]` = present 건수, `field_source[field][tier]` = tier별 채택 건수(Tier1 API/상태·Tier2 DOM·Tier3 og).
  - `gate_field_rate[field]` = 게이트 필드별 충족률.
  - `completeness` = 도메인 평균 충족률, `status` = 완료/미완/대조군.
- `adapter_quality_gate(items)` — 디폴트 마켓 어댑터별 게이트: **충족률 90% 미만 = '미완'** + `weak_fields`(90% 미만 필드) 명시.

## 품질 게이트 (브리프 명세)
- 필드 = **[제목·가격·이미지≥3·옵션(존재 시)·상세]**.
- **옵션은 존재 시만 분모**에 포함(무옵션 상품 미감점) — `item_completeness`.
- 가격은 `needs_check`면 미충족(임의 확정 금지), 상세는 ≥20자 또는 상세이미지, 이미지는 갤러리 ≥3장.
- 디폴트 마켓 도메인 충족률 < 0.90 → `status='미완'` → **diagnostics가 '완료' 서술 불가**.
- 요시다 = 제네릭 대조군(게이트 비대상, `status='대조군'`).

## diagnostics 라우트
- `GET /seller/collect/field-loss?days=90` — 본인 스코프 수집 상품의 `matrix` + `adapter_gate` JSON 반환(미인증 401).

## 판정
- 가드 `tests/test_v63_field_loss_matrix.py` (8): 도메인 정규화·완비/무옵션 미감점/결손 충족률·도메인 tier 집계·게이트 미완 플래그·요시다 대조군·라우트 등록.
- **전/후 매트릭스(실 URL 3종 × 2경로)**는 오너가 라이브 수집 후 `/seller/collect/field-loss`로 회수 — 개발 환경 프록시가 라이브 마켓 차단으로 대행 불가(가짜 매트릭스 날조 금지).

적용 스킬: (백엔드 집계 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
