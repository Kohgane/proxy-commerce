# 비전 마스터 문서 — Proxy Commerce (kohganepercentiii.com)

> **최종 수정**: 2026-05-02 · Phase 122 기준

---

## 목차

1. [프로젝트 정체성](#1-프로젝트-정체성)
2. [인프라 토폴로지](#2-인프라-토폴로지)
3. [핵심 기능 정의](#3-핵심-기능-정의)
4. [갭 분석 표](#4-갭-분석-표)
5. [우선순위 큐](#5-우선순위-큐)
6. [모듈 매핑](#6-모듈-매핑)
7. [수익 모델](#7-수익-모델)
8. [결정된 약속](#8-결정된-약속)
9. [용어집](#9-용어집)

---

## 1. 프로젝트 정체성

**Proxy Commerce**는 Kohgane(형)의 개인 SaaS 셀러툴이다.

| 항목 | 내용 |
|------|------|
| 프로덕션 도메인 | `kohganepercentiii.com` (i 3개) |
| 인프라 | Render (Docker, Free tier) |
| 레포 | `Kohgane/proxy-commerce` (`main` 브랜치 → 자동 배포) |
| 벤치마크 | 한국 퍼센티 (`percenty.co.kr`) — 해외 상품 자동 수집/번역/업로드 SaaS |
| 외부 채널 | `kohganemultishop.org` (WordPress + WooCommerce + PortOne, 블루호스트) |

### 한 줄 정의

> "해외 소싱처(Amazon/타오바오/Porter/Memo/Alo/Lululemon)에서 상품을 수집·번역·가격 책정 후
>  한국 마켓(쿠팡/스마트스토어/11번가)과 자체몰(코가네멀티샵)에 자동 업로드하는 개인 맞춤 SaaS."

### 포지셔닝

```
퍼센티(percenty.co.kr)  →  범용 셀러툴 SaaS (공개 서비스)
kohganepercentiii.com  →  Kohgane 개인화 버전 (추후 SaaS 공개 고려)
```

---

## 2. 인프라 토폴로지

```mermaid
graph TD
    subgraph "SaaS 본체 (Render)"
        A["kohganepercentiii.com<br/>Flask 3 + Python 3.11<br/>Docker · Free Tier"]
    end

    subgraph "외부 채널"
        B["kohganemultishop.org<br/>WordPress + WooCommerce<br/>PortOne PG · 블루호스트"]
    end

    subgraph "한국 마켓"
        C1["쿠팡 (Coupang)"]
        C2["스마트스토어 (Naver)"]
        C3["11번가"]
    end

    subgraph "해외 소싱처"
        D1["Amazon US / JP"]
        D2["타오바오 / 1688 / Tmall"]
        D3["Porter (en.porter.jp)"]
        D4["Memo Paris (memoparis.com)"]
        D5["Alo Yoga (aloyoga.com)"]
        D6["lululemon (lululemon.com)"]
        D7["프리미엄 스포츠<br/>(Nike, UA, Arc'teryx...)"]
    end

    A -->|REST API / Webhook| C1
    A -->|REST API| C2
    A -->|REST API| C3
    A -->|WC REST API| B
    A -->|스크래핑 (Phase 123)| D1
    A -->|스크래핑 (Phase 123)| D2
    A -->|스크래핑 (Phase 123)| D3
    A -->|스크래핑 (Phase 123)| D4
    A -->|스크래핑 (Phase 123)| D5
    A -->|스크래핑 (Phase 123)| D6
    A -->|스크래핑 (Phase 123)| D7
    B -->|주문 Webhook| A
```

> **핵심 원칙**: `kohganemultishop.org`는 Render 서비스에 추가하지 않는다.
> SaaS 본체(`kohganepercentiii.com`)가 WC REST API로 외부 채널을 제어한다.

---

## 3. 핵심 기능 정의

사용자 비전 노트를 정리한 13개 핵심 기능:

| # | 기능명 | 설명 |
|---|--------|------|
| 1 | **수동 수집기** | 상품 URL → 메타데이터 추출 → 번역 → 마켓 업로드 (퍼센티 스타일) |
| 2 | **자동 수집기** | 소싱처 모니터링 → 조건 충족 상품 자동 수집 (Phase 108/115) |
| 3 | **반품/교환 관리** | 자동 분류·승인·회수물류·검수·환불 오케스트레이션 (Phase 37/118) |
| 4 | **자동 구매** | 주문 접수 → 소싱처 자동 발주 (Phase 96/101/104) |
| 5 | **마진 계산기** | 원가+배송+관세+수수료+환율 전부 포함 실시간 계산 (Phase 33/97/110) |
| 6 | **신상품 감지** | 트렌드 기반 신규 소싱처/상품 자동 발견 (Phase 115) |
| 7 | **마켓 현황** | 쿠팡/스스/11번가 상품 상태 통합 모니터링 (Phase 71/109) |
| 8 | **배대지 관리** | 미국/유럽/중국 배대지 자동 선택 및 운송장 추적 (Phase 102) |
| 9 | **배송 추적 알림** | 배송 상태 기반 고객 자동 알림 (Phase 99/103/117) |
| 10 | **멀티테넌시** | 테넌트별 구독 플랜, 사용량 추적 (Phase 49) |
| 11 | **셀러 대시보드** | 오늘 KPI·수집큐·마켓현황·알림·환율 통합 화면 (Phase 122 신규) |
| 12 | **WC 마이그레이션** | 스마트스토어 상품 → kohganemultishop.org 일괄 이전 (Phase 125 예정) |
| 13 | **PortOne 연동** | 한국 PG 결제 게이트웨이 통합 (Phase 126 예정) |

---

## 4. 갭 분석 표

→ 상세 내용: [GAP_ANALYSIS.md](GAP_ANALYSIS.md)

| 기능 | 백엔드 상태 | UI 상태 | 관련 Phase |
|------|-------------|---------|------------|
| 반품/교환 | ✅ 완료 | ❌ UI 없음 | P37, P118 |
| 자동 구매 | ✅ 완료 | ❌ UI 없음 | P96, P101, P104 |
| 마진 계산기 | ✅ 완료 | ✅ P122 추가 | P33, P97, P110 |
| 신상품 감지 | ✅ 완료 | ❌ UI 없음 | P115 |
| 마켓 현황 | ✅ 완료 | ✅ P122 추가 | P71, P109 |
| 배대지 | ✅ 완료 | ❌ UI 없음 | P102 |
| 배송 알림 | ✅ 완료 | ❌ UI 없음 | P99, P103, P117 |
| 멀티테넌시 | ✅ 완료 | ❌ UI 없음 | P49 |
| **수동 수집기 UI** | ✅ 완료 | ✅ **P122 신규** | P17, P122 |
| **셀러 대시보드** | ✅ 완료 | ✅ **P122 신규** | P122 |
| Alo/Lululemon 어댑터 | ⚠️ mock | ✅ P122 mock | P122→P123 |
| 타오바오 신뢰도 필터 | ⚠️ mock | ✅ P122 mock | P122→P124 |
| WC 마이그레이션 | ❌ 부재 | ❌ | P125 예정 |
| PortOne 연동 | ❌ 부재 | ❌ | P126 예정 |

---

## 5. 우선순위 큐

### P0 (이번 PR — Phase 122)
- 셀러 대시보드 (`/seller/dashboard`)
- 수동 수집기 UI (`/seller/collect`)
- 마진 계산기 UI (`/seller/pricing`)
- 마켓 현황 UI (`/seller/market-status`)
- 비전 마스터 문서

### P1 (다음 PR — Phase 123)
- Alo Yoga / lululemon 어댑터 실연동 (스크래핑)
- 프리미엄 스포츠 브랜드 확장

### P2 (Phase 124~127)
- 타오바오 셀러 신뢰도 실연동 + 자동 차단
- WooCommerce 마이그레이션 도구
- PortOne 결제 게이트웨이 연동
- 배대지 확장 (미국/유럽/중국)

### P3 (Phase 128~130)
- 신상품 자동 캐치 + 브랜드별 구독 알림
- 멀티테넌시 SaaS 활성화
- 수입/수출 양방향 배송 자동화

---

## 6. 모듈 매핑

| 비전 항목 | src/* 모듈 |
|-----------|-----------|
| 수동 수집기 | `src/seller_console/manual_collector.py` |
| 셀러 대시보드 | `src/seller_console/views.py`, `widgets.py` |
| 반품 관리 | `src/returns/`, `src/returns_automation/` |
| 자동 구매 | `src/auto_purchase/` |
| 마진 계산 | `src/margin/`, `src/margin_calculator/`, `src/pricing_engine/` |
| 신상품 감지 | `src/sourcing_discovery/` |
| 마켓 현황 | `src/marketplace_sync/`, `src/channel_sync/` |
| 배대지 | `src/forwarding/`, `src/forwarding_integration/` |
| 배송 추적 | `src/logistics/`, `src/delivery_notifications/` |
| 멀티테넌시 | `src/tenancy/` |
| 환율 | `src/fx/` |
| 타오바오 신뢰도 | `src/seller_console/seller_trust.py` |

---

## 7. 수익 모델

### 현재 (형 단독 운영)
- 단일 테넌트, Render Free tier
- 비용: Render $0/월 (슬립 있음) + 도메인 ~$10/년

### SaaS 공개 시 (Phase 129)

| 플랜 | 월 요금 | 한도 |
|------|---------|------|
| Free | $0 | 1 테넌트, 50 상품, 기본 마켓 1개 |
| Starter | $29 | 1 테넌트, 500 상품, 마켓 3개 |
| Pro | $79 | 3 테넌트, 5,000 상품, 마켓 전체 |
| Enterprise | 문의 | 무제한 테넌트, 전용 인스턴스 |

Phase 92 (구독 관리), Phase 49 (멀티테넌시) 모듈 활용.

---

## 8. 결정된 약속

이 항목들은 변하지 않는 원칙이다.

1. **`kohganemultishop.org`는 Render에 추가하지 않는다.**
   - 별도 블루호스트 인프라, SaaS의 외부 채널일 뿐
   - SaaS → WC REST API → WooCommerce 방식으로 제어

2. **`kohganepercentiii.com`이 SaaS 본체다.**
   - i가 3개 (`percentiii`) — 오타 아님

3. **모든 신규 기능은 기존 Phase 모듈 최대 재사용.**
   - 새 모듈 생성 전 기존 `src/*` 확인

4. **mock 우선 → 검증 후 실연동.**
   - 모든 어댑터/스크래퍼는 mock 데이터로 시작

5. **기존 `/admin/*` 경로/모듈/엔드포인트 변경 금지.**
   - 셀러 콘솔은 `/seller/*` prefix 사용

6. **`FX_DISABLE_NETWORK` 가드 유지.**
   - CD Staging 환경 안정화

7. **백워드 호환 유지.**
   - 기존 API 응답 스키마 변경 금지

8. **인증은 Phase 24 OAuth 모듈 연결 전까지 stub.**
   - `SELLER_CONSOLE_AUTH=1` 환경변수로 활성화

---

## 9. 용어집

| 용어 | 한국어 | 설명 |
|------|--------|------|
| Sourcing | 수집/소싱 | 해외 소싱처에서 상품 정보 수집 |
| Forwarding | 배대지 | 해외 → 한국 배송 중계 서비스 |
| Marketplace | 마켓 | 쿠팡/스마트스토어/11번가 등 판매 채널 |
| Tenant | 테넌트 | 멀티테넌시 환경의 개별 사용자/조직 |
| ProductDraft | 상품 초안 | 수집 후 업로드 전 검수 대기 상품 |
| GMV | 총 거래액 | Gross Merchandise Volume |
| Margin | 마진 | (판매가 - 원가 - 수수료 - 배송비) / 판매가 |
| Adapter | 어댑터 | 소싱처별 데이터 추출 로직 캡슐화 클래스 |
| SaaS | - | Software as a Service — 구독형 소프트웨어 서비스 |
| PG | 결제대행사 | PortOne(구 아임포트), 토스페이먼츠 등 |
| WC | WooCommerce | kohganemultishop.org의 쇼핑몰 플랫폼 |
| mock | 목 데이터 | 실연동 전 테스트용 가짜 데이터 |
