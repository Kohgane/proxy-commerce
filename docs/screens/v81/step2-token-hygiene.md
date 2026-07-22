# v81 STEP2 — 토큰 위생 (안정 재사용 + 90일 유휴 만료)

## 증상/요구(오너 브리프)
북마클릿 파일을 재다운로드할 때마다 **새 토큰이 발급**돼 토큰 목록이 계속 불어남(신규 남발). 오래된 미사용
토큰도 무한 잔존. → 사용자당 안정 토큰 1개 재사용 + 90일 미사용 자동 만료.

## 근본 원인
`bookmarklet_file`·`bookmarklet_code` 두 라우트가 매 호출마다 `generate_token`을 **직접 호출** → 클릭/다운로드
1회당 토큰 1개 신규 생성. 재사용 로직 없음.

## 수리
1. **세션 재사용 헬퍼** `_bookmarklet_token(user_id)`(views.py 단일 진입) — 세션에 캐시된 raw 토큰(`bm_token_raw`
   /`bm_token_hash`)이 **활성**(`token_active`)이면 그대로 재임베드, 아니면 신규 발급 후 세션에 캐시. 두 라우트
   (`bookmarklet_file`·`bookmarklet_code`)가 `raw = _bookmarklet_token(user_id)`로 통일(generate_token 직접 호출 제거).
2. **90일 유휴 만료** `_IDLE_EXPIRY_DAYS=90` + `_is_idle_expired(row, now)`(최근 사용, 없으면 발급 시각 + 90일 < 지금).
   `validate_token` 인메모리 경로가 유휴면 None(만료 취급). PG 경로는 PG validate가 판정.
3. **`token_active(user_id, token_hash)`** 신설 — 해시가 활성(비회수·비하드만료·비유휴)인지 판정(재사용 게이트).
   PG면 `validate`, 인메모리면 조회.
4. **토큰 페이지 정직 표기**: `list_tokens`가 `idle_expired` 플래그 노출 → `personal_tokens.html`이 유휴면
   **유휴 만료** 배지(warn 토큰·이모지 0). 최근 사용시각·용도(권한) 컬럼은 기존 유지.

## 계약(브리프)
> STEP 2 — 발급 로직을 안정 토큰 재사용으로(사용자당 1개 기본, 파일 재다운로드 시 동일 토큰 임베드). 토큰 페이지에
> [최근 사용시각·용도] 표시, 90일 미사용 자동 만료. 신규 남발 금지.
> **판정: 파일 3회 연속 발급 후 토큰 목록 증가 0.**

## 판정
- 가드 `tests/test_v81_token_hygiene.py`(5):
  - `test_idle_expiry_and_token_active`: 갓 발급=활성, 타사용자 미인정, 91일 미사용→유휴 만료(token_active False·
    validate None), 89일 전 사용=아직 활성.
  - `test_list_tokens_marks_idle`: 120일 미사용 → `idle_expired=True` + 최근사용·권한 노출.
  - `test_bookmarklet_token_helper_source`: 헬퍼 소스계약(세션 캐시·token_active·두 라우트 경유).
  - **`test_three_downloads_no_token_growth`**: 같은 세션에서 `/seller/bookmarklet/file` **3회 연속** → 활성 토큰
    **정확히 1개**(신규 남발 0). ★오너 판정선.
  - `test_token_page_shows_idle_badge`: 템플릿 유휴 만료 배지 + 마지막 사용.
- 기존 토큰/북마클릿 하네스 91 그린(회귀 0).
- 전체 스위트 그린.

## 금지 준수
- 원문 토큰 저장 0(SHA-256 해시 저장 유지) · 세션 캐시는 서버 세션(쿠키 서명)에만 · 유휴 만료는 정직 표기
  (가짜 활성 0) · 재사용은 **활성 확인 후**에만(회수/만료 토큰은 재발급).

적용 스킬: (백엔드 토큰 저장·세션 재사용 로직 + 토큰 페이지 배지 — warn 토큰·이모지 0. impeccable/humanizer CLI 미설치.)
