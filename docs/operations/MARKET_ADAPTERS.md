# MARKET_ADAPTERS (Phase 151)

- 기본 위치: `src/markets/adapters/`
- 기본 모드: `MARKET_ADAPTER_DEFAULT=mock`
- live 모드는 각 마켓 자격증명이 모두 있을 때만 사용

## 포함 어댑터

- `coupang_wing.py` — 쿠팡 윙 scaffold
- `naver_commerce.py` — 네이버 커머스 scaffold
- `eleven_st.py` — 11번가 scaffold
- `mock.py` — 기본 mock

## 공통 인터페이스

- `create_listing(payload)`
- `update_inventory(sku, qty)`
- `get_order_status(external_order_id)`
