# 싱가포르 이관 체크리스트 v1 (Render 리전 일치)

> 목적: Render 서비스 리전을 **버지니아 → 싱가포르**로 옮겨 Supabase(싱가포르)와 같은 리전에 두면,
> 쿼리 왕복 지연(현재 대륙 간 ~220ms/쿼리)이 사라진다. **DB는 그대로**(같은 Supabase, `DATABASE_URL` 불변).
> 코드 변경 없음 — 인프라 리전·IP 하드코딩이 코드에 없음을 grep으로 확인함(`DATABASE_URL` 환경변수만 사용).
>
> ⚠️ 값은 이 문서에 **절대 적지 마세요**(키명만). 실제 값은 현 서비스 Environment 탭에서 복사합니다.
> ⚠️ 구 서비스는 **즉시 삭제 금지** — DNS 전환·검증이 끝날 때까지 Suspend만.

## 0. 준비물
- Render 대시보드 접근, 도메인(kohganepercentiii.com) DNS 관리 접근.
- 현 서비스(`proxy-commerce`, virginia)의 **Environment 탭을 열어 둔다**(값 복사용).

## 1. 신규 서비스 생성 (Blueprint)
1. Render → **New → Blueprint** → 이 레포(Kohgane/proxy-commerce) 선택 → `render.yaml`의 **`proxy-commerce-sg`**(region: singapore, plan: **starter**) 생성.
2. 생성 직후 `sync:false` 키들은 비어 있음 → **Environment 탭에서 아래 목록을 현 서비스 값 그대로 입력**.
   - 가장 확실한 방법: 현 서비스 Environment 탭의 **모든 키를 그대로 복사**(누락 방지). 아래는 그 중 꼭 필요한 키의 분류.

### 1-1. 환경변수 전수 목록 (키명만 — 값은 현 서비스에서 복사)
**필수 (없으면 부팅 실패/세션 끊김)**
- `DATABASE_URL` (Supabase 트랜잭션 풀러 6543 — 싱가포르, **값 불변**)
- `DATABASE_URL_DIRECT` (직접 연결 5432 — DDL/마이그레이션)
- `SECRET_KEY` (세션 서명 — 반드시 현 값 그대로. 바뀌면 전 사용자 로그아웃)
- `APP_ENV=production`, `PORT=10000`, `FX_DISABLE_NETWORK=1`, `GUNICORN_WORKERS`, `GUNICORN_TIMEOUT`, `GUNICORN_LOG_LEVEL` (render.yaml에 기본값 포함)

**마켓 자격증명 암호화**
- `MARKET_CRED_ENC_KEY` (⚠️ 반드시 동일 값 — 다르면 저장된 마켓 연동정보 복호화 불가)

**AI·번역**
- `OPENAI_API_KEY`, `OPENAI_MODEL`, `DEEPL_API_KEY`, `DEEPL_API_URL`, `ANTHROPIC_API_KEY`

**Sheets 백업(읽기전용 일 1회 덤프)**
- `GOOGLE_SHEET_ID`, `GOOGLE_SERVICE_JSON_B64`

**마켓 연동**
- Shopify: `SHOPIFY_SHOP`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `SHOPIFY_ACCESS_TOKEN`
- WooCommerce: `WOO_BASE_URL`, `WOO_CK`, `WOO_CS`, `WOO_WEBHOOK_SECRET`
- 쿠팡: `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY`, `COUPANG_VENDOR_ID`, `COUPANG_VENDOR_USER_ID`, `COUPANG_OUTBOUND_SHIPPING_PLACE_CODE`, `COUPANG_RETURN_CENTER_CODE`, `COUPANG_RETURN_ZIP_CODE`, `COUPANG_RETURN_ADDRESS`, `COUPANG_RETURN_ADDRESS_DETAIL`, `COUPANG_RETURN_CHARGE_NAME`, `COUPANG_COMPANY_CONTACT_NUMBER`, `COUPANG_RETURN_CHARGE`, `COUPANG_OVERSEAS_PURCHASED`, `COUPANG_SEARCH_API_KEY`
- 스마트스토어(네이버 커머스): `NAVER_COMMERCE_CLIENT_ID`, `NAVER_COMMERCE_CLIENT_SECRET`, `NAVER_CHANNEL_ID`, `NAVER_COMMERCE_API_BASE`
- 11번가: `ELEVENST_API_KEY`, `ELEVENST_DISP_CTGR_NO`
- 아마존 SP-API(승인 시): `AMAZON_SP_CLIENT_ID`, `AMAZON_SP_CLIENT_SECRET`, `AMAZON_SP_REFRESH_TOKEN`, `AMAZON_SP_SELLER_ID`, `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY`, `AMAZON_PARTNER_TAG`
- 마켓 릴레이(고정 IP 경유): `MARKET_RELAY_URL`, `MARKET_RELAY_TOKEN`, `MARKET_RELAY_MARKETS`

**이미지 CDN**
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `CLOUDINARY_FOLDER`

**소셜 로그인 OAuth** (⚠️ 콜백 URL은 신규 도메인 확인 후 각 콘솔에 등록)
- 구글: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`
- 네이버: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
- 카카오: `KAKAO_CLIENT_ID`, `KAKAO_CLIENT_SECRET`, `KAKAO_REST_API_KEY`
- 애플: `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`

**검색·SEO·소싱**
- 네이버 검색/쇼핑: `NAVER_SEARCH_CLIENT_ID`, `NAVER_SEARCH_CLIENT_SECRET`, `NAVER_SHOPPING_SEARCH_CLIENT_ID`, `NAVER_SHOPPING_SEARCH_CLIENT_SECRET`
- 네이버 검색광고: `NAVER_SEARCHAD_API_KEY`, `NAVER_SEARCHAD_API_SECRET`, `NAVER_SEARCHAD_CUSTOMER_ID`

**알림·크론·결제·모바일**
- 텔레그램: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_BOT_WEBHOOK_SECRET`, `ORDER_ALERT_TELEGRAM_BOT_TOKEN`, `ORDER_ALERT_TELEGRAM_CHAT_ID`
- 크론: `CRON_SECRET`
- 토스페이먼츠: `TOSS_SECRET_KEY`, `TOSS_PAYMENTS_SECRET_KEY`
- 알리고 SMS: `ALIGO_API_KEY`, `ALIGO_USER_ID`, `ALIGO_SENDER`
- 모바일 스토어: `TWA_PACKAGE_NAME`, `TWA_SHA256_FINGERPRINTS`, `IOS_APP_ID`
- 관리자: `ADMIN_EMAILS`, `SELLER_CONSOLE_AUTH`

> **누락 방지 원칙**: 위 분류에 없더라도 현 서비스 Environment 탭에 있는 키는 **전부** 복사한다. 기능 플래그(예: `*_ENABLED`)는 코드 기본값이 있으나, 현 운영값과 맞추는 게 안전.

## 2. 신규 서비스 검증 (onrender.com 임시 URL)
신규 서비스의 `https://proxy-commerce-sg.onrender.com` 에서 순서대로 확인:
1. **`/health`** → 200, 부팅 로그에 `DB 연결: Supabase OK` 1줄.
2. **로그인** → 소셜/이메일 로그인 성공(SECRET_KEY 동일하면 기존 세션도 유지).
3. **수집 1건** → 확장/북마클릿으로 상품 1개 수집 → 수집 이력에 즉시 표시.
4. **드로어** → 수집 항목 클릭 → 편집 드로어 정상 로드(가격·이미지·상세).
5. **Server-Timing** → 개발자도구 네트워크 탭에서 `/seller/collect/history`의 `db;dur=`·`total;dur=` 확인(버지니아 대비 대폭 감소 기대).

## 3. 도메인 전환 (검증 통과 후에만)
1. Render 신규 서비스 → **Settings → Custom Domain** → `kohganepercentiii.com`(+`www`) 추가.
2. Render가 안내하는 **CNAME/A 레코드**를 DNS에 반영:
   - 기존 구 서비스를 가리키던 레코드를 **신규 서비스 값으로 교체**.
   - TTL이 크면 전파에 시간이 걸리므로, 전환 전 TTL을 낮춰두면 좋음(예: 300s).
3. HTTPS 인증서가 신규 서비스에 발급될 때까지 대기(Render 자동).
4. OAuth 콜백 URL이 도메인 기준이면 그대로(도메인 불변) — 도메인이 같으므로 콘솔 재등록 불필요. (onrender 임시 URL로 테스트했다면 그때만 임시 콜백 등록.)

## 4. 컷오버 확인 + 구 서비스 정리
1. 도메인 전파 후 `https://kohganepercentiii.com`에서 §2의 5개 항목 재확인.
2. 며칠간 문제 없으면 구 서비스(`proxy-commerce`, virginia)를 **Suspend**(삭제 아님 — 롤백 대비).
3. 완전 안정 확인 후에만 구 서비스 삭제(오너 판단, 서두르지 않음).

## 롤백
- 문제 시 DNS 레코드를 구 서비스 값으로 되돌리면 즉시 복귀(구 서비스 Suspend 해제).
- DB는 공유(같은 Supabase)라 데이터 유실 없음.
