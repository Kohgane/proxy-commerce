# v57 STEP2 — 수집 → 목록 실시간 반영 (전체 리렌더 금지)

## 수집이력 (`/seller/collect/history`) — 증분 삽입
3중화:
1. **visibilitychange** — 탭 복귀 시 즉시 `since` 재조회
2. **15초 폴링** — 활성 탭만(`document.hidden` 가드), 커서 = `collected_at`(updated_after)
3. **신규 감지 → 맨 위 삽입 + 토스트** — 서버가 렌더한 `<tr>`만 `insertBefore(body.firstChild)`,
   `pcToast('새 상품 N건 수집됨')`. 기존 행 재렌더 **0**(전체 리렌더 금지 준수).

- 신규 endpoint `GET /seller/collect/history/since?after=<iso>&days=` → `{ok, count, server_max, html}`.
  - 커서 미지정(첫 호출) = 신규 0 + `server_max`만(초기 화면과 중복 삽입 방지).
  - 신규 = 최신 60건 훑어 `collected_at > after`만, 최대 20행 렌더(폭주 방지).
  - 정직: 저장 스코프(user_id+email 관용집합) 재읽기 → 서버 커밋된 값만(가짜 실시간 0).
- 중복 방지: 삽입 전 `.row-chk[value=id]` 존재 확인(폴링 경합 이중 삽입 0).
- 편집 중(드로어/모달 열림) = 삽입 보류 + 배너("편집 중 새로 수집된 N건 대기"), 드로어 닫히면 반영.
- 삭제 경합(`window._kgpDeleting`) 시 삽입 보류(v43-1 부활 방지 유지).
- 새 행 강조: `.kgp-newrow` 청록 페이드(2.6s, prefers-reduced-motion 정지).

## 카탈로그 (`/seller/catalog`) — 정직 갱신 배너
카탈로그는 **수집이 아니라 마켓 동기화 결과** → '수집됨' 토스트는 오해 유발이라 금지.
- `GET /seller/catalog/count` → 총건수. visibilitychange + 15초 폴링(활성 탭만)으로 증가 감지 시
  **'마켓 동기화로 상품 N건 갱신됨' 배너 + [새로고침] 버튼**(자동 전체 리렌더 금지 — 사용자 클릭만).

## 판정
- 가드 `test_v57_live_list`(since 커서·신규만·중복0·auth401·증분폴링 소스계약·카탈로그 count·정직배너) 8 pass.
- v41 STEP1-0b(count 전체 reload) → v57 STEP2(since 증분 삽입)로 승격, 전체 리렌더 제거.
