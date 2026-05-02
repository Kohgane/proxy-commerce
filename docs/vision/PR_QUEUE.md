# PR 큐 — Proxy Commerce Phase 122+

> 앞으로 띄울 PR 시리즈 명세 카드.
> 갭 분석 참조: [GAP_ANALYSIS.md](GAP_ANALYSIS.md)

---

## Phase 122 — 셀러 SaaS 코어 UI ✅ (현재 PR)

| 항목 | 내용 |
|------|------|
| 제목 | Phase 122: 셀러 SaaS 코어 UI (셀러 대시보드 + 수동 수집기 + 마진 계산기 + 마켓 현황 + 비전 마스터 문서) |
| 목표 | 셀러(형) 관점 UI 전무 상태 → 핵심 4개 화면 추가 |
| 산출물 | `src/seller_console/`, `docs/vision/`, `tests/test_seller_console.py` |
| URL | `/seller/dashboard`, `/seller/collect`, `/seller/pricing`, `/seller/market-status` |
| 완료 기준 | ✅ 모든 라우트 200 응답, ✅ mock 추출 동작, ✅ 마진 계산 정확, ✅ 테스트 통과 |

---

## Phase 123 — 신규 브랜드 어댑터 실연동

| 항목 | 내용 |
|------|------|
| 제목 | Phase 123: Alo Yoga / lululemon / 프리미엄 스포츠 어댑터 실연동 |
| 목표 | mock 어댑터 → 실제 HTTP 스크래핑 |
| 산출물 | `src/seller_console/manual_collector.py` 어댑터 실구현, `tests/` |
| 완료 기준 | Alo/Lululemon URL 입력 시 실제 이미지/제목/가격 추출 성공 |
| 선행 조건 | Phase 122 머지 |

---

## Phase 124 — 타오바오 셀러 신뢰도 실연동

| 항목 | 내용 |
|------|------|
| 제목 | Phase 124: 타오바오 셀러 신뢰도 실연동 + 자동 차단 |
| 목표 | mock TrustChecker → 실데이터 평가 + 기준 미달 셀러 자동 필터 |
| 산출물 | `src/seller_console/seller_trust.py` 실구현 |
| 완료 기준 | 실 타오바오 URL에서 셀러 신뢰도 점수 정확 산출, 임계치 미달 시 경고 |
| 선행 조건 | Phase 122 머지 |

---

## Phase 125 — WooCommerce 마이그레이션 도구

| 항목 | 내용 |
|------|------|
| 제목 | Phase 125: 스마트스토어 → kohganemultishop.org 상품 일괄 이전 |
| 목표 | 스마트스토어 상품 목록 CSV 입력 → WC REST API로 일괄 등록 |
| 산출물 | `src/migration/wc_migrator.py`, CLI 커맨드, 매핑 가이드 문서 |
| 완료 기준 | 테스트 상품 10개 WC 등록 성공 |
| 선행 조건 | Phase 122 머지, WC API 키 발급 |

---

## Phase 126 — PortOne 결제 게이트웨이 연동

| 항목 | 내용 |
|------|------|
| 제목 | Phase 126: PortOne V2 한국 PG 연동 |
| 목표 | kohganemultishop.org 결제 흐름 PortOne V2로 통합 |
| 산출물 | `src/payment_gateway/portone_v2.py`, Webhook 핸들러, 테스트 |
| 완료 기준 | 테스트 결제 성공, 취소/환불 플로우 동작 |
| 선행 조건 | Phase 125 머지, PortOne 계정 |

---

## Phase 127 — 배대지 확장

| 항목 | 내용 |
|------|------|
| 제목 | Phase 127: 미국/유럽/중국 배대지 자동 선택 확장 |
| 목표 | 소싱처 위치 기반 최적 배대지 자동 선택 |
| 산출물 | `src/forwarding/` 확장, 배대지 비용 비교 API |
| 완료 기준 | 3개 지역 배대지 자동 선택 + 비용 계산 정확 |
| 선행 조건 | Phase 122 머지 |

---

## Phase 128 — 신상품 자동 캐치 + 브랜드 구독

| 항목 | 내용 |
|------|------|
| 제목 | Phase 128: 신상품 자동 캐치 + 브랜드별 구독 알림 |
| 목표 | 소싱처 신상품 감지 → 텔레그램 알림 자동 발송 |
| 산출물 | `src/sourcing_discovery/` 강화, 브랜드 구독 관리 UI |
| 완료 기준 | Alo/lululemon 신상 감지 후 5분 이내 텔레그램 알림 |
| 선행 조건 | Phase 123 머지 |

---

## Phase 129 — 멀티테넌시 SaaS 공개

| 항목 | 내용 |
|------|------|
| 제목 | Phase 129: 멀티테넌시 SaaS 활성화 (가입/요금제/공개) |
| 목표 | 형 단독 운영 → 외부 셀러 가입 가능 SaaS로 전환 |
| 산출물 | 가입 플로우, 요금제 페이지, Phase 49 멀티테넌시 활성화 |
| 완료 기준 | 테스트 계정으로 가입 → 플랜 선택 → 셀러 콘솔 접근 성공 |
| 선행 조건 | Phase 126 머지, 도메인 SSL 확인 |

---

## Phase 130 — 양방향 배송 자동화

| 항목 | 내용 |
|------|------|
| 제목 | Phase 130: 수입/수출 양방향 배송 자동화 (kohganemultishop.org 통합) |
| 목표 | 해외 구매대행 입고 + 한국→해외 역직구 흐름 자동화 |
| 산출물 | 배송 자동화 오케스트레이터, WC 주문 동기화 |
| 완료 기준 | 해외→한국 수입 + 한국→해외 수출 양방향 배송 추적 성공 |
| 선행 조건 | Phase 127, Phase 129 머지 |
