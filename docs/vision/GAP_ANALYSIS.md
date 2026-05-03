# 갭 분석 — Proxy Commerce Phase 122

> 사용자 비전 항목 vs 현재 구현 상태 분석.
> 비전 마스터 문서 참조: [MASTER_VISION.md](MASTER_VISION.md)

---

## 전체 갭 분석 표

| 우선순위 | 기능 | 백엔드 상태 | UI 상태 | 관련 Phase | 다음 PR 후보 | 예상 공수 |
|----------|------|-------------|---------|------------|-------------|----------|
| **P0** | 수동 수집기 UI | ✅ 완료 | ✅ Phase 122 완료 | P17, P122 | — | 완료 |
| **P0** | 셀러 대시보드 | ✅ 완료 | ✅ Phase 122 완료 | P122 | — | 완료 |
| **P0** | 마진 계산기 UI | ✅ 완료 | ✅ Phase 122 완료 | P33, P97, P110 | — | 완료 |
| **P0** | 마켓 현황 UI | ✅ 완료 | ✅ Phase 122 완료 | P71, P109 | — | 완료 |
| **P0** | 비전 마스터 문서 | ✅ — | ✅ Phase 122 완료 | P122 | — | 완료 |
| **P1** | Alo/Lululemon 실연동 | ⚠️ mock | ⚠️ mock | P122→P123 | Phase 123 | 소 (1 PR) |
| **P1** | 프리미엄 스포츠 확장 | ⚠️ mock | ⚠️ mock | P122→P123 | Phase 123 | 소 (1 PR) |
| **P2** | 타오바오 신뢰도 실연동 | ⚠️ mock | ⚠️ mock | P122→P124 | Phase 124 | 중 (1~2 PR) |
| **P2** | WC 마이그레이션 도구 | ❌ 부재 | ❌ 부재 | P125 예정 | Phase 125 | 중 (1 PR) |
| **P2** | PortOne 연동 | ❌ 부재 | ❌ 부재 | P126 예정 | Phase 126 | 대 (2 PR) |
| **P2** | 배대지 확장 | ⚠️ 일부 | ❌ UI 없음 | P102, P127 | Phase 127 | 중 |
| **P3** | 신상품 자동 캐치 | ✅ 완료 | ❌ UI 없음 | P115, P128 | Phase 128 | 소 |
| **P3** | 멀티테넌시 SaaS 공개 | ✅ 완료 | ❌ UI 없음 | P49, P129 | Phase 129 | 대 |
| **P3** | 양방향 배송 자동화 | ⚠️ 일부 | ❌ UI 없음 | P130 | Phase 130 | 대 |

---

## P0 상세 (Phase 122 완료)

### 수동 수집기 UI
- **파일**: `src/seller_console/manual_collector.py`, `templates/manual_collect.html`
- **어댑터**: Amazon, Taobao, Alibaba, Porter, Memo, Alo Yoga, lululemon, PremiumSports, Generic
- **현재 상태**: mock 데이터 (실 스크래핑은 Phase 123)
- **셀러 신뢰도**: 타오바오 URL 자동 평가 + 경고 배너

### 셀러 대시보드
- **파일**: `src/seller_console/views.py`, `widgets.py`, `data_aggregator.py`
- **위젯**: KPI·수집큐·마켓현황·소싱알림·반품CS·자동구매큐·환율
- **모든 위젯**: graceful import + mock fallback

### 마진 계산기
- **파일**: `templates/pricing_console.html`, `data_aggregator.py:calculate_margin()`
- **입력**: 매입가/통화, 배송비, 관세율, 마켓수수료, PG수수료, 목표마진%
- **출력**: 판매가, 실마진, 손익분기점 + 5종 시나리오 테이블

### 마켓 현황
- **파일**: `templates/market_status.html`
- **기능**: 마켓별 활성/품절/오류 카드 + 필터 + 30초 자동 새로고침

---

## P1 상세 (Phase 123 목표)

### Alo Yoga / lululemon 실연동
- 현재: `AloAdapter`, `LululemonAdapter` mock 구현
- Phase 123 목표: 실제 HTTP 스크래핑 + 이미지 추출
- 고려사항: robots.txt 준수, 속도 제한, User-Agent 설정

### 프리미엄 스포츠 확장
- 현재: `PremiumSportsAdapter` — Nike, Under Armour, Arc'teryx, Patagonia, TNF
- Phase 123 목표: 브랜드별 개별 어댑터로 분리 + 실연동

---

## P2 상세 (Phase 124~127 목표)

### 타오바오 셀러 신뢰도 실연동 (Phase 124)
- 현재: `TaobaoSellerTrustChecker` mock 구현
- Phase 124 목표: 타오바오 API 또는 스크래핑으로 실데이터 조회
- 기준: 별점≥4.7, 판매≥1000, 운영≥12개월, 부정리뷰≤5%, 응답≤24h
- 자동 차단: 기준 미달 셀러 상품 자동 필터링

### WooCommerce 마이그레이션 도구 (Phase 125)
- 스마트스토어 상품 목록 → kohganemultishop.org 일괄 이전
- WC REST API v3 활용
- 이미지/설명/가격/재고 매핑 테이블 제공

### PortOne 결제 게이트웨이 (Phase 126)
- PortOne(구 아임포트) V2 API 통합
- 한국 주요 PG: 토스페이먼츠, KG이니시스, NHN KCP
- kohganemultishop.org 결제 흐름 연동

### 배대지 확장 (Phase 127)
- 미국: 현재 지원 + 확장
- 유럽: 새 배대지 추가
- 중국: 타오바오 직배송 경로 추가
