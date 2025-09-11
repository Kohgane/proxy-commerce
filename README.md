# Proxy Commerce – 2단계 구매대행 자동화 (Runnable)

이 레포는 **즉시 실행** 가능한 2단계(반자동 주문 라우팅) 템플릿입니다.

## 빠른 시작

1) **Google Sheet** 만들기 → 시트명 `catalog`, 헤더/데이터는 이 레포의 `data/catalog.sample.csv`를 그대로 Import (즉시 배포용)
2) **Cloudinary** 키 준비 (Dashboard에서 cloud_name/api_key/api_secret)
3) **Shopify** 앱 생성 → Admin API Token / Shop 도메인 준비
4) **WooCommerce** → REST API 키(consumer key/secret) 생성
5) 이 레포를 깃허브에 올린 뒤, 레포 **Settings → Secrets and variables → Actions**에 아래 시크릿 입력
6) **Actions** 탭에서 워크플로 수동 실행 → Shopify/Woo에 제품이 생성됨
7) `order_webhook`를 Render/Cloud Run 등에 배포 후, Shopify에 주문 Webhook 등록

### 필수 Secrets
- `GOOGLE_SERVICE_JSON_B64`: Google 서비스계정 JSON base64
- `GOOGLE_SHEET_ID`: 카탈로그 시트 파일 ID
- `SHOPIFY_ACCESS_TOKEN`: Shopify Admin API Token
- `SHOPIFY_SHOP`: `your-shop.myshopify.com`
- `SHOPIFY_LOCATION_ID`: (선택) 재고 관리 위치 ID (없으면 기본값 사용)
- `WOO_BASE_URL`: WooCommerce 사이트 URL (예: https://example.kr)
- `WOO_CK`: WooCommerce Consumer Key
- `WOO_CS`: WooCommerce Consumer Secret
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
- (선택) `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- (선택) `NOTION_TOKEN`, `NOTION_DB`

> 주의: 실제 판매 전 **이미지 사용권/상표권/약관**을 반드시 확인하세요.

---

## 명령

로컬 테스트:
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export $(cat .env.example | xargs)  # 필요 시 값 수정 후 사용
python -m src.catalog_sync  # 카탈로그 동기화 1회 실행
python -m src.order_webhook  # 웹훅 서버 로컬 실행 (기본 8000)
```
