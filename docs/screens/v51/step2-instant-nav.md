# v51 STEP2 — 0.5초 내비게이션

전제: DNS 싱가포르 전환 완료 후 판정(오너 진행). 서울↔싱가포르 RTT ~70ms.

## dbq 3페이지 계측 (로그인 상태, 로컬 PG · 풀 ON)
| 페이지 | 쿼리 수 | db 합계 | 비고 |
|---|---|---|---|
| 수집이력 `/seller/collect/history` | **3** | ~3.4ms | list + summary + distinct (lean) |
| 카탈로그 `/seller/catalog` | **0** | ~0ms | PG 미사용(Sheets/인메모리 카탈로그) |
| 드로어 `/seller/collect/preview/<id>` | **6 → 2** | ~1ms | 마켓 연결상태 5회 왕복 → 1회로 감축 |

→ 3페이지 모두 **쿼리 ≤3** 목표 충족. 배포 절대 ms·이관 전후는 오너 캡처(네트워크 탭 Server-Timing).

## 다이어트 (v49 재검 결과)
- **상시 커넥션 풀 기본 ON**(v49 opt-in → v51 기본): `PG_PERSISTENT_POOL` 기본 "1", `=0`으로만 끔. DB URL
  없음·풀 미설치 시 폴백(무회귀). 요청당 TCP+TLS 핸드셰이크 제거(내비 지연 완화).
- **드로어 마켓 연결상태 배치**: `is_connected`를 5개 마켓마다 부르면 `_load_all`(=PG 쿼리)이 5회 → 대륙 간
  RTT×5. `connected_markets`로 **1회 읽어 메모리 판정** → 드로어 6→2 쿼리.

## 내비 즉시화
- **hover/focus/touch prefetch**(기존 v13, instant.page식): 마우스 올리면 다음 페이지를 `<link rel=prefetch>`로
  미리 받아 클릭 시 즉시.
- **클릭 즉시 skeleton 오버레이**(신규): 같은 출처 내비 클릭 순간(0ms) 반투명 skeleton 셔머를 띄워 '반응함'을
  즉시 표시 → 새 페이지 도착(프리패치로 워밍) 시 자연 소멸. 상단 진행바(기존)와 함께. reduced-motion 존중.
- 정적자산 **immutable 캐시**(버전드 1년, 기존 v40-B) + gzip 유지.

## 판정 (오너, DNS 전환 후)
서울 실기기에서 수집이력→카탈로그→드로어 연속 이동 화면녹화: 각 클릭→첫 콘텐츠 0.5초 이내 + 네트워크 탭
Server-Timing(dbq·db·total) 캡처. (풀 ON은 SG 서비스에서 실효과 계측.)

## 가드
test_v51_instant_nav(5): 풀 기본 ON·DB없음 폴백 / connected_markets 1회 로드 / 드로어 배치 사용 / 즉시
skeleton+prefetch+진행바 / immutable 캐시. + test_v49_db_metering 풀 기본 ON 반영. 로컬 PG로 드로어 6→2 실측.
