# CLAUDE.md — proxy-commerce 작업 메모리

> 이 파일은 매 세션 시작 시 로드된다. 오너(Kohgane) 지시·검증된 팩트를 누적 기록한다.

## 🔴 작업 원칙 (오너 지시 — 2026-06-14)
- **추측 금지. 팩트로만 말한다.** 모르면 "모른다 / 확인 필요"라고 말하고, 검증한 것만 단정한다.
- 코드/문서/로그/실제 응답 등 **확인 가능한 근거**가 있을 때만 단정적으로 답한다.
- 헛다리(추측 기반 단정) 반복 금지. 화면·응답 원문 등 증거를 우선한다.

## 📌 마켓 연동 — 검증된 팩트 (2026-06-14)
- **쿠팡**: ✅ 연결됨. 차단 원인은 **IP 허용목록**이었음 — 서버 아웃바운드 IP(예 74.220.49.7)를
  Wing 'API 호출 허용 IP'에 등록해야 함(쉼표로 다중 가능). 서명/키 정상.
- **WooCommerce**: ✅ 연결됨. 과거 406은 User-Agent/Accept 헤더 누락이 원인(수정됨).
- **스마트스토어(네이버)**: 인증·서명 정상. 차단 원인 = **네이버 허용 IP(앱당 최대 3개)에 서버 IP 미등록**.
  bcrypt 전자서명(client_secret_sign) 필요(수정됨).
- **11번가**: 997 "등록된 API 정보 없음" = 키/OpenAPI 승인 문제(IP 아님).
- **Shopify** (검증된 팩트, 미해결):
  - 토큰 `atkn_…` = 개발자 대시보드 '앱 자동화 토큰'. 앱 `kohgane-uploader5`가 상점 KOHGANE(`catdyy-p0.myshopify.com`)에 설치됨. scope에 read_products/write_products 포함. 토큰 만료 2026-11-29.
  - **검증 결과**: 이 `atkn_` 토큰을 `X-Shopify-Access-Token`으로 REST(`/shop.json`)·GraphQL(`/graphql.json`) 둘 다 호출 시 **401 "Invalid API key or access token"**.
  - **따라서**: 401은 스코프 문제 아님(스코프 정상). Shopify가 `atkn_` 토큰을 **상점 Admin API 액세스 토큰으로 인식하지 않음**.
  - 다음 단계(미확정): 올바른 Admin API 액세스 토큰(보통 `shpat_`, in-admin Develop apps에서 발급) 확보 또는 atkn_ 토큰의 정식 사용법 확인. (이 환경은 egress 차단으로 Shopify 직접 호출/문서 접근 불가)

## 🛠 인앱 마켓 연결 (셀프서비스)
- `/seller/markets/connect`(+`/<market>` 단독) — 셀러별 Fernet 암호화 저장(`market_credentials.py`).
- `/seller/markets/guide` — 그림 포함 발급 가이드.
- `data/` 저장은 Render 재배포 시 초기화됨(ephemeral) → durable은 Render 환경변수.

## 작업 방식
- 브랜치 `claude/magical-noether-oo4831`에서 작업 → PR 생성·main 머지(오너 승인됨)로 배포.
- 변경 후 전체 테스트(`python -m pytest tests/ -q`) 통과 확인.
