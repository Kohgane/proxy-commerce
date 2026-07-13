# v61 STEP2 — Shopify 실패 진단 (/admin/diagnostics)

## 수리
- `ShopifyAdapter._error_summary`: JSON 오류 구조 없으면 **실제 HTTP 상태 + 본문 앞부분** 표기(뭉뚱그림 금지)
  + **자격증명 마스킹**(STEP0 mask_text — access_token 등 평문 0).
- `check_connection` 성공 시 **api_version**(사용 중 Admin API 버전) 반환 → 진단에 'API 2026-04' 표기.
- `_shopify_read_step`(진단 스텝): 실패 지점 **구분** —
  · 미설정(not_configured) → `token_missing` + **미설정 env 이름만**(값 미표시)
  · 401 → `token_expired` + `HTTP 401` + reason
  · 403/scope → `scope_insufficient` + `HTTP 403` + reason
  · 그 외 → `api_error`(단, detail에 **HTTP {status} + 본문 요약** 포함 → 뭉뚱그림 아님).

## 판정 (배포 후 — 오너)
/admin/diagnostics Shopify 스텝: 유효 키 설정 시 녹색(shop 이름·도메인·플랜·API 버전) + 상품 1건 등록.
실패 시 실제 HTTP·에러 본문(마스킹)으로 원인 구분 표기.

가드 test_v61_shopify_diag(4): error_summary 마스킹+HTTP · api_version · 미설정/401/403 구분 · api_error 비뭉뚱.
