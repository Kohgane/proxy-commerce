# v73 STEP3 — v72 잔여 판정 회수

v72(b) 3건은 **이미 배포·머지**(main, 확장 1.5.92 포함)됐고 가드 그린이다. 이 STEP은 라이브 프록시 차단으로
오너 몫이던 **판정 캡처를 하네스로 회수**한다. 미배포분 없음(전부 반영 확인).

## ① 가격 단일화 — 드로어 0.00 소멸 (v72b STEP1, #503)
- **구조**: 서버 `canonical_price(price→price_original)` 단일 관문 + 드로어 클라 `_normPriceStr`(number 입력
  전 정규화). `collect_preview_by_id`가 `extra.price`를 `_EXTRA`로 주입 → 프리필이 `_normPriceStr`로 정규화 후 대입.
- **회수 캡처**: `step3-drawer-price-single-truth.png` — 실 `_normPriceStr`(템플릿에서 추출) 실행 결과.
  `_EXTRA.price="81,800."`(끝점·콤마) → **naive input.value 직접 대입 = 빈값(=0.00)** vs **_normPriceStr 정규화 = 81800**.
- **가드**: `tests/test_v72b_price_single_source.py`(10) — canonical_price 계약 + Playwright(number 입력 '81800.'
  거부='' / `_normPriceStr('81800.')`='81800'). 현행(1.5.92) 그린.

## ② 토큰 수명 — 구 설치본 생존 (v72b STEP2, #504)
- **구조**: `generate_token`은 insert-only(폐기 호출 0) · TTL 365일 · 브라우저별 다수 토큰 동시 유효.
  401(login_required)에 `reissue_url:/seller/bookmarklet` → 토스트 [토큰 재발급 열기](30초 복구).
- **회수 판정**: behavioral 가드가 재현 — 같은 유저 2회 연속 발급 → **두 토큰 모두 validate 성공(1회차 생존)**.
  (시각 캡처보다 동작 증명이 본질 — 폐기 미발생을 코드로 못박음.)
- **가드**: `tests/test_v72b_token_lifecycle.py`(3) — 발급 무폐기·TTL≥90·파일365 + 2토큰 동시유효 + 401 재발급 링크.
  현행 그린.

## ③ [다시 수집] 세탁 (v72b STEP3, #505)
- **구조**: 목록 벌크바 `[다시 수집]`(data-act=recollect) → 선택분 `force` 재수집 → 서버가 기존 레코드
  덮어씀(신규 행 0) + 보강 큐 재투입. 구버전 '-' 가격 세탁 통로.
- **회수 캡처**: `step1-amazon-search-bulkbar.png`(STEP1 실 렌더) 벌크바에 **[다시 수집] 버튼 실존** 확인.
- **가드**: `tests/test_v72b_recollect.py`(6) — 소스계약 + server force=update(append 아님) + behavioral
  ('-' 가격 → 같은 id·가격 채움·행 수 불변·recollected 마킹) + node(force 부착). 현행 그린.

## 판정 요약
| 항목 | 배포 | 가드 | 캡처 회수 |
|---|---|---|---|
| ① 드로어 0.00 소멸 | #503(1.5.92 포함) | 10 그린 | ✅ step3-drawer-price-single-truth.png |
| ② 토큰 수명 | #504 | 3 그린 | ✅ behavioral(2토큰 동시유효) |
| ③ [다시 수집] 세탁 | #505 | 6 그린 | ✅ step1 벌크바 [다시 수집] 버튼 |

## 금지 준수
추출기 변경 0 · 가짜 성공 0(실 함수·실 가드 출력) · 코드 변경 없음(캡처/문서 회수 STEP).

적용 스킬: (검증·캡처 회수 — 코드 변경 없음. impeccable/humanizer CLI 미설치.)
