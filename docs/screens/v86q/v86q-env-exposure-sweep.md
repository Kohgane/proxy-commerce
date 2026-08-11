# v86-Q — 셀러 화면 개발표기(env-var·내부 문서경로) 정직 스윕

v86-P(알림) 외 잔여 셀러 노출 개발표기를 전수 triage(셀러 템플릿 `<code>` 내 env-var/경로)한 뒤,
**실제 누출만** 평문 교체. 절대원칙("일반 유저에게 개발 표기 노출 금지").

## triage 결과
| 위치 | 내용 | 판정 |
|---|---|---|
| sourcing.html | `NAVER_SEARCH_CLIENT_ID/SECRET` (빈 상태) | **누출 → 제거** |
| markets_guide.html | `docs/operations/LIVE_VERIFICATION_GUIDE.md` (내부 저장소 경로) | **누출 → 제거** |
| pricing_console.html | 환율 출처 라벨 `환경변수`(개발 용어) | **개발 용어 → '설정값'** |
| markets_connect.html | `MARKET_CRED_ENC_KEY` | 보존 — `?` 툴팁(data-bs-title) 안(고급 안내, v5 선례) |
| markets_guide.html | `GW.IP_NOT_ALLOWED` 등 | 보존 — 마켓 실제 에러코드(셀러 트러블슈팅에 필요) |
| billing.html | `const TOSS_CLIENT_KEY` | 오탐 — JS 변수명 + 공개용(publishable) 클라이언트 키 |

## before/after (문자열)
- sourcing: `… (네이버 쇼핑 검색 API 키 <code>NAVER_SEARCH_CLIENT_ID/SECRET</code> 미설정)`
  → `… (네이버 쇼핑 검색이 아직 연결되지 않았어요)` — "가짜 수치는 표시하지 않습니다" 유지.
- markets_guide: `자세한 운영 문서: <code>docs/operations/LIVE_VERIFICATION_GUIDE.md</code>`
  → `막히는 부분이 있으면 각 마켓 판매자센터의 도움말을 함께 확인하거나 문의해 주세요.`
- pricing_console: 환율 출처 라벨 `환경변수` → `설정값`.

## 판정
- 가드 `tests/test_v86_q_env_exposure_sweep.py`(4): 누출 3종 제거 + 보존 2종(툴팁 게이트·에러코드) 확인.
- 회귀: sourcing/pricing/guide/markets/audit/friendly **864 passed**.
- 순수 텍스트(개발표기 제거) — 레이아웃/시각 변경 없음(캡처 대신 문자열 before/after).

적용 스킬: (사용자 카피 정직화 — 레이아웃 변경 없음. impeccable/humanizer CLI 미설치 → 평문 톤 수동.)
