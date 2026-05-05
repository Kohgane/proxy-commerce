# WOOCOMMERCE.md — WooCommerce REST API 연동 가이드 (Phase 132)

## 개요

kohganemultishop.org (외부 WordPress/WooCommerce 자체몰)와 본 셀러 콘솔을 연동합니다.

WooCommerce REST API v3 + Basic Auth (consumer_key:consumer_secret over HTTPS) 방식입니다.

---

## API 키 발급 단계

1. **kohganemultishop.org WordPress 관리자** 접속 (`/wp-admin`)
2. **WooCommerce → 설정** 메뉴 진입
3. **고급** 탭 → **REST API** 선택
4. **키 추가** 버튼 클릭
5. 설명: `퍼센티 셀러 콘솔`
6. 권한: **읽기/쓰기 (Read/Write)** 선택
   - 읽기만 필요 시: 상품 조회, 주문 조회만 가능
   - 읽기/쓰기: 상품 등록, 운송장 주문 노트 추가 가능
7. **API 키 생성** 클릭
8. **Consumer Key** (`ck_...`)와 **Consumer Secret** (`cs_...`) 복사
   - ⚠️ 이 화면을 벗어나면 Secret을 다시 볼 수 없습니다!

---

## 환경변수 등록

Render Environment Variables에 다음을 등록합니다:

```
WC_URL=https://kohganemultishop.org
WC_KEY=ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WC_SECRET=cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

또는 별칭 사용:

```
WOO_BASE_URL=https://kohganemultishop.org
WOO_CK=ck_...
WOO_CS=cs_...
```

두 세트 중 어느 쪽이든 인식합니다.

---

## 연동 확인

등록 후 `/health/deep` 엔드포인트에서 확인:

```json
{
  "name": "woocommerce",
  "status": "ok",
  "base_url": "https://kohganemultishop.org",
  "detail": "WooCommerce REST API 정상"
}
```

미설정 시:

```json
{
  "name": "woocommerce",
  "status": "missing",
  "hint": "WC_URL, WC_KEY, WC_SECRET 환경변수 등록 필요"
}
```

---

## 기능

| 기능 | 엔드포인트 | 설명 |
|---|---|---|
| 상품 목록 조회 | `GET /wp-json/wc/v3/products` | 페이지네이션 자동 처리 (100개씩) |
| 상품 등록 | `POST /wp-json/wc/v3/products` | 셀러 콘솔에서 WordPress로 등록 |
| 주문 조회 | `GET /wp-json/wc/v3/orders` | since 파라미터로 증분 조회 |
| 운송장 등록 | `POST /wp-json/wc/v3/orders/{id}/notes` | 주문 노트로 기록 |

---

## 운송장 등록 방식

WooCommerce 기본에는 운송장 필드가 없습니다.

본 연동은 **주문 노트(Order Note)** 방식으로 기록합니다:

```
[퍼센티] 운송장 등록: CJ대한통운 / 1234567890
```

Advanced Shipment Tracking 플러그인이 설치된 경우 별도 엔드포인트로 연동 가능합니다.

---

## 트러블슈팅

### 401 Unauthorized
- WC_KEY / WC_SECRET 값 확인
- WordPress Basic Auth가 활성화되어 있는지 확인
- `.htaccess`에 `Authorization` 헤더 전달 설정 필요할 수 있음:
  ```apache
  RewriteRule .* - [E=HTTP_AUTHORIZATION:%{HTTP:Authorization}]
  ```

### 404 Not Found
- WordPress Permalink 설정 확인: **설정 → 고유 주소 → 글 이름** (기본값 제외 모두 가능)
- WooCommerce REST API 활성화 확인

### CORS 오류
- 브라우저 직접 호출이 아닌 서버-서버 호출이므로 CORS 무관

### per_page 제한
- WooCommerce 기본 최대 100개/페이지
- 본 어댑터는 100개씩 페이지네이션 자동 처리

---

## 관련 파일

- `src/seller_console/market_adapters/woocommerce_adapter.py` — 어댑터 구현
- `docs/operations/DOMAINS.md` — 도메인 정책
- `docs/operations/API_KEYS.md` — 전체 API 키 목록
