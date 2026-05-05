# DOMAINS.md — 도메인 라우팅 정책 (Phase 132)

## 개요

이 프로젝트는 두 개의 독립적인 도메인을 운영합니다.

| 도메인 | 역할 | 소유/관리 |
|---|---|---|
| **kohganepercentiii.com** | 셀러 SaaS + 운영 백오피스 (본 앱) | 본 레포 |
| **kohganemultishop.org** | 외부 WordPress + WooCommerce 자체몰 | 별도 WordPress 서버 |

---

## kohganepercentiii.com 라우팅 표

| 경로 | 동작 |
|---|---|
| `/` | `ROOT_REDIRECT` 환경변수 따라 (기본: `/seller/` redirect) |
| `/seller/*` | 셀러 콘솔 (상품/주문/마켓 관리) |
| `/admin/*` | 어드민 패널 |
| `/api/*` | REST API |
| `/shop`, `/shop/` | **302 redirect → https://kohganemultishop.org** |
| `/health/*` | 헬스체크 |

---

## ROOT_REDIRECT 환경변수

루트(`/`) 접속 시 동작을 제어합니다.

| 값 | 동작 |
|---|---|
| `seller` (기본) | `/seller/` 셀러 콘솔로 redirect |
| `landing` | 통합 랜딩 페이지 표시 |
| `shop_external` | https://kohganemultishop.org 로 외부 redirect |
| `shop` | `shop_external`과 동일 (레거시 호환) |

---

## kohganemultishop.org 연동

본 앱은 **WooCommerce REST API v3**를 통해 kohganemultishop.org의 데이터를 통합 조회합니다.

직접 접속은 항상 외부 WordPress 서버로, 본 앱은 **백오피스 연동만** 담당합니다.

### 환경변수

```
WC_URL=https://kohganemultishop.org      # 또는 WOO_BASE_URL
WC_KEY=ck_...                             # 또는 WOO_CK
WC_SECRET=cs_...                          # 또는 WOO_CS
```

---

## ENABLE_INTERNAL_SHOP 환경변수 (옵트인)

Phase 131에서 만든 내부 `/shop` 블루프린트는 **기본 비활성** 상태입니다.

향후 데모/쇼윈도우 용도로 활성화하려면:

```
ENABLE_INTERNAL_SHOP=1
```

이 값이 설정되면 내부 `/shop/*` 라우트가 활성화되고, `/shop` redirect는 동작하지 않습니다.

---

## 관련 파일

- `src/order_webhook.py` — 라우팅 로직
- `src/seller_console/market_adapters/woocommerce_adapter.py` — WooCommerce 연동
- `docs/operations/WOOCOMMERCE.md` — WooCommerce API 키 발급 가이드
