# SOURCING.md — 소싱 파이프라인 운영 가이드 (Phase 143)

## 개요

소싱 파이프라인은 라쿠텐, 아마존JP, Yahoo Shopping 등 일본 플랫폼에서 키워드·카테고리 기반으로 신상품·할인 상품을 자동 발견하고, 마진 시뮬레이션을 거쳐 운영자 승인 후 본 등록까지 연결하는 자동화 시스템입니다.

## 아키텍처

```
[Watch 등록] → [discover_candidates] → [simulate_margin] → [queue_candidate]
                                                                    ↓
[운영자 승인] → [auto_publish] → [채널 등록 (쿠팡/스마트스토어/11번가)]
```

## 핵심 모듈

| 모듈 | 위치 | 역할 |
|------|------|------|
| WatchStore | `src/sourcing/pipeline.py` | watch CRUD |
| CandidateQueue | `src/sourcing/pipeline.py` | 후보 큐 관리 |
| `discover_candidates()` | `src/sourcing/pipeline.py` | 신상품·할인 발견 |
| `simulate_margin()` | `src/sourcing/pipeline.py` | 마진 시뮬레이션 |
| `queue_candidate()` | `src/sourcing/pipeline.py` | 후보 큐 적재 |
| `run_watch_cycle()` | `src/sourcing/pipeline.py` | 전체 사이클 |

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SOURCING_WATCH_INTERVAL_MINUTES` | `60` | Watch 실행 주기 (분) |
| `SOURCING_AUTO_QUEUE_MIN_MARGIN_PCT` | `15` | 자동 큐 최소 마진율 (%) |

## 관리 화면

- **Watch 관리**: `/seller/sourcing/watches`
- **후보 큐**: `/seller/sourcing/candidates`
- **진단 대시보드**: `/admin/diagnostics` → 섹션 11

## Watch 등록 방법

1. `/seller/sourcing/watches` 접속 (관리자 로그인 필요)
2. 플랫폼 선택 (라쿠텐 / 아마존JP / Yahoo Shopping)
3. 키워드 입력 (예: `ユニクロ`, `Nike`)
4. 카테고리, 가격 범위 입력 후 등록
5. ▶ 실행 버튼으로 즉시 테스트

## 마진 시뮬레이션 공식

```
소싱원가(KRW) = 소싱가 × FX 환율
플랫폼 수수료 = 소싱원가 × 수수료율
  - 라쿠텐: 10%  / 아마존JP: 8%  / Yahoo Shopping: 8%
배송비: 5,000원 (고정)
광고비: 판매가 × 5%
총비용 = 소싱원가 + 수수료 + 배송비 + 광고비
마진율 = (판매가 - 총비용) / 판매가 × 100
```

## 후보 큐 승인 플로우

1. 마진 기준(기본 15%) 통과한 후보만 큐 적재
2. `/seller/sourcing/candidates` 에서 목록 확인
3. 개별 승인 또는 전체 일괄 승인
4. 승인 후 📤 등록 버튼 → `auto_publish()` 호출

## 운영 팁

- **Watch 주기**: 60분마다 자동 실행하려면 cron/APScheduler 연동 필요
- **마진 기준 조정**: `SOURCING_AUTO_QUEUE_MIN_MARGIN_PCT` 환경변수로 조정
- **플랫폼 API 연동**: 현재 stub 데이터 사용, 실제 운영 시 Rakuten Product API / Amazon PA-API 연동
- **FX 환율**: 현재 고정값 사용, `src/fx/` 모듈 연동으로 실시간 환율 적용 가능
