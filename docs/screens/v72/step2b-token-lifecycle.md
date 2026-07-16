# v72(b) STEP2 — 북마클릿 토큰 수명 구조

## 원인 감사 (PR 명시)
- **발급 시 폐기 여부**: `generate_token`은 신규 토큰을 **insert만** 함 — 기존 토큰 폐기 호출(`revoke_token`/`revoke_all`)·`revoked=True` 변형 **0**. 파일/코드 재발급이 기존 설치본을 죽이지 않음.
- **TTL**: `_DEFAULT_EXPIRY_DAYS=365`(장수명). 북마클릿 파일도 `expires_days=365`.
- **동시 유효 N개**: append 방식이라 브라우저별 다수 토큰이 동시 유효.
- **401 유발 조건**: (a) 잘못된/만료 토큰(365일 경과·명시 폐기) + (b) **세션도 없음**(v72 STEP1 세션 폴백 실패). 즉 토큰이 죽어도 콘솔 로그인 세션이 있으면 401 안 남(세션 폴백). 401은 토큰死 AND 세션死일 때만.

## 구조 (수리)
- 재발급 무폐기·365일·다중 유효는 **이미 충족**(회귀 가드로 못박음).
- **401 토스트에 [토큰 재발급 열기] 링크**: collect 401(login_required) 응답에 `reissue_url: /seller/bookmarklet` 추가 → 북마클릿 토스트가 재발급 페이지 링크를 붙임(죽어도 30초 복구). 코어 버전 `bm-v72b`.

## 판정
- 가드 `tests/test_v72b_token_lifecycle.py` (3):
  - 감사(generate_token revoke 호출 0·TTL≥90·파일 365일).
  - **behavioral**: 같은 유저 2회 연속 발급 → 두 토큰 모두 validate 성공(**1회차 생존, 폐기 미발생**).
  - 401 재발급 링크(reissue_url·토스트 [토큰 재발급 열기]).
- 회귀: `test_personal_tokens`·`test_v29_tokens`·`test_v42_e1_token_persist`·`test_v58_options_version`(bm-v72b) 그린. 전체 그린.
- **실기기(오너 몫)**: 파일 2회 연속 발급 후 1회차 설치본으로 수집 성공 + 401 시나리오 토스트 링크 캡처. (개발 프록시 라이브 차단.)

## 금지 준수
- 토큰 발급 시 전체 폐기 0(회귀) · 가짜 성공 0 · 자격증명 평문 0(해시 저장).

적용 스킬: (백엔드 토큰·북마클릿 토스트 — UI 렌더 변경 최소. impeccable/humanizer CLI 미설치.)
