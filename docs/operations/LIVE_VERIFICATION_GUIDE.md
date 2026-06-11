# 🚦 마켓 연동 라이브 검증 가이드

> **이 문서 하나로** 쿠팡 · 스마트스토어 · 11번가 · Shopify · WooCommerce를
> 실제로 연결하고, 진짜로 상품이 올라가는지까지 확인할 수 있습니다.
> 처음 보는 사람도 위에서 아래로 순서대로만 따라 하면 됩니다.

---

## 0. 큰 그림 (3단계만 기억하세요)

```
①  열쇠 받기          ②  열쇠 꽂기              ③  문 열리는지 확인
   (API 키 발급)   →     (환경변수 등록)     →    (검증 도구 실행)
   각 마켓 사이트         Render 대시보드          python -m scripts.verify_market_connections
```

- **① 열쇠 받기**: 각 마켓 판매자센터에서 API 키(=열쇠)를 발급받습니다.
- **② 열쇠 꽂기**: 받은 키를 Render의 환경변수(Environment)에 넣습니다.
- **③ 확인**: 검증 도구를 돌려서 `✅ 연결됨`이 뜨는지 봅니다. 그 다음 테스트 상품을 한 개 올려봅니다.

> 💡 키를 넣기 전에는 모든 마켓이 `🪪 자격증명 없음(token_missing)`으로 나옵니다. **정상입니다.**

---

## 1. 검증 도구 사용법 (제일 먼저 익히기)

연결 상태를 한 번에 보여주는 명령어입니다. Render 셸(Shell) 또는 로컬 터미널에서 실행하세요.

```bash
# 전체 마켓 한 번에 확인
python -m scripts.verify_market_connections

# 특정 마켓만 확인 (예: 쿠팡)
python -m scripts.verify_market_connections coupang

# 기계용 JSON으로 받기 (자동화/로그용)
python -m scripts.verify_market_connections --json
```

### 출력 예시 (키를 넣기 전)

```
■ Coupang (coupang)
   연결 상태 : 🪪 자격증명 없음
   업로드준비: ⚠️ token_missing — 필수 환경변수 미설정: COUPANG_ACCESS_KEY, ...
   해결 방법 : https://wing.coupang.com 에서 API 키 발급
   필요 환경변수: COUPANG_VENDOR_ID, COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY
   가이드    : docs/operations/COUPANG.md

요약: 전체 5개 중 ✅ 연결됨 0개 · 미연결 5개
```

### 어디서 실행하나요? (쉬운 순서)

#### 방법 A. 웹 화면 — **셸 필요 없음, 가장 쉬움** ⭐
브라우저에서 로그인 후 아래 주소를 열기만 하면 됩니다. 명령어를 칠 필요가 없어요.

- **`https://(내도메인)/seller/markets/connect`** — 마켓별로 키 입력 + **[연결 테스트]** 버튼
- **`https://(내도메인)/seller/markets`** — 마켓 현황 한눈에
- **`https://(내도메인)/admin/diagnostics`** — 운영자용 종합 진단

> 👉 키를 막 넣고 바로 확인하려면 **`/seller/markets/connect`** 에서 키를 넣고 **[연결 테스트]** 를 누르세요.

#### 방법 B. Render Shell — 명령어로 한 번에 전체 확인
1. [Render 대시보드](https://dashboard.render.com) → 해당 **웹 서비스** 클릭
2. 상단/좌측 탭에서 **Shell** 클릭 (실행 중인 서비스에서 열림)
3. 까만 터미널이 열리면 그대로 입력:
   ```bash
   python -m scripts.verify_market_connections
   ```
4. 5개 마켓 상태가 표로 출력됩니다. (환경변수는 Render 서비스에 이미 들어있어 자동 적용)

> ⚠️ **Shell 탭이 안 보이면**: Render의 일부 무료 플랜은 Shell이 없습니다. 이때는 **방법 A(웹 화면)** 를 쓰세요. 결과는 동일합니다.
> 📁 Shell은 기본적으로 프로젝트 루트(`scripts/` 폴더가 있는 위치)에서 열립니다. 혹시 아니면 `cd ~/project/src` 가 아니라 레포 최상위로 이동 후 실행하세요.

#### 방법 C. 내 PC(로컬)
레포를 받아둔 PC에서도 됩니다. 단, **로컬에는 키가 없으니** 같은 키들을 로컬 환경변수/`.env`에 넣어야 실제 검증이 됩니다(보통 방법 A·B를 권장).

> 세 방법 모두 **같은 결과**를 보여줍니다. 편한 걸 쓰세요.

---

## 2. 연결 상태 한눈에 읽기

| 표시 | 뜻 | 무엇을 해야 하나 |
|------|----|----------------|
| ✅ `connected` | 정상 연결됨 | 끝! 테스트 업로드로 넘어가세요 |
| 🪪 `token_missing` | 키(환경변수)가 없음 | 아래 마켓별 안내대로 키를 등록 |
| ⏰ `token_expired` | 토큰 만료됨 | 마켓 판매자센터에서 토큰 재발급 |
| 🔒 `scope_insufficient` | 권한 부족 | API 앱의 권한(상품 등록 등)을 추가 |
| ❌ `api_error` | API 호출 실패 | 키 오타/네트워크/마켓 점검 여부 확인 |

> **검증 도구는 운영 데이터를 절대 바꾸지 않습니다.** 읽기 연결 + 안전한 "빈 쓰기 시험(dry-run)"만 합니다.

---

## 3. Render에 환경변수 넣는 법 (공통)

1. [Render 대시보드](https://dashboard.render.com) 접속 → 해당 서비스 클릭
2. 왼쪽 메뉴 **Environment** 클릭
3. **Add Environment Variable** 버튼
4. **Key**(변수 이름)와 **Value**(키 값)를 입력 → **Save Changes**
5. 저장하면 서비스가 자동으로 재배포됩니다(1~2분). 재배포 후 검증 도구를 다시 실행하세요.

> ⚠️ 값을 붙여넣을 때 **앞뒤 공백/줄바꿈이 섞이지 않게** 주의하세요. 가장 흔한 실패 원인입니다.

### 🔐 (중요) 암호화 키 `MARKET_CRED_ENC_KEY` 만들고 넣기

셀러가 `/seller/markets/connect` 화면에서 입력한 마켓 키들은 **이 암호화 키로 잠가서** 저장됩니다.
키가 없으면 평문 저장(개발용)이라, **운영에서는 반드시 넣어주세요.**

**① 키 만들기** — 아무 데서나 1줄 실행 (Render Shell 또는 내 PC):
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
출력 예시(↓ 이건 예시일 뿐, **본인이 직접 생성한 값**을 쓰세요):
```
jiVxNw0coK-kfePqWIJfOnaUeCSOcsXkEl4FVSk12BM=
```
- 끝이 `=` 로 끝나는 **44글자** 문자열이면 정상입니다.

**② 키 넣기** — Render 환경변수 등록(3번 섹션과 동일):
- **Key**: `MARKET_CRED_ENC_KEY`
- **Value**: 위에서 생성한 44글자 키
- Save → 자동 재배포

> 💡 별도 사이트에서 "받는" 게 아니라 **직접 생성**하는 값입니다(비밀번호처럼).
> ⚠️ **한 번 정하면 바꾸지 마세요.** 키를 바꾸면 그 전에 저장된 셀러 키들을 복호화할 수 없습니다.
> 안 넣어도 당장은 동작하지만(SECRET_KEY로 대체), 운영에서는 전용 키를 권장합니다.

---

## 4. 마켓별 상세 안내

각 마켓은 ① 키 발급 → ② 환경변수 → ③ 연결 확인 → ④ 테스트 업로드 순서입니다.

### 🛒 4-1. 쿠팡 (Coupang)

| 항목 | 내용 |
|------|------|
| ① 키 발급 | [쿠팡 윙(Wing)](https://wing.coupang.com) → 판매자 정보 → **오픈 API 키 발급** |
| ② 환경변수 | `COUPANG_ACCESS_KEY` · `COUPANG_SECRET_KEY` · `COUPANG_VENDOR_ID` |
| 필요 권한 | 상품 조회 / 상품 등록·수정 / 주문 조회 / 배송 처리 |
| 상세 문서 | `docs/operations/COUPANG.md` |

```bash
# ③ 연결 확인
python -m scripts.verify_market_connections coupang   # → ✅ 연결됨 이면 성공
```

### 🟢 4-2. 스마트스토어 (네이버 커머스)

| 항목 | 내용 |
|------|------|
| ① 키 발급 | [네이버 커머스 API 센터](https://commerce.naver.com) → 애플리케이션 등록 → 클라이언트 ID/Secret |
| ② 환경변수 | `NAVER_CLIENT_ID` · `NAVER_CLIENT_SECRET` (선택: `NAVER_CHANNEL_ID`) |
| 🔁 별칭 허용 | `NAVER_COMMERCE_CLIENT_ID` · `NAVER_COMMERCE_CLIENT_SECRET` 로 넣어도 동작합니다 |
| 필요 권한 | 상품 조회 / 상품 등록·수정 / 주문 조회 / 발송 처리 |
| 상세 문서 | `docs/operations/NAVER_SMARTSTORE.md` |

> 📌 **네이버 주의**: 같은 자격증명을 코드가 두 이름으로 받습니다. 둘 중 **아무 한 쌍**만 넣으면 됩니다.
> 헷갈리면 `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` 한 쌍만 넣으세요.

```bash
python -m scripts.verify_market_connections smartstore
```

### 🔴 4-3. 11번가 (11st)

| 항목 | 내용 |
|------|------|
| ① 키 발급 | [11번가 셀러오피스](https://soffice.11st.co.kr) → 오픈 API → **API 키 발급** |
| ② 환경변수 | `ELEVENST_API_KEY` (선택: `ELEVENST_DISP_CTGR_NO` = 기본 카테고리 번호) |
| 필요 권한 | 상품 조회 / 상품 등록·수정 / 주문 조회 / 배송 처리 |
| 상세 문서 | `docs/operations/ELEVENST.md` |

> ⚠️ 11번가는 **카테고리·배송 템플릿**이 셀러 계정마다 다릅니다. 첫 업로드가 카테고리 오류로 막히면
> 셀러오피스에서 본인 카테고리 번호를 확인해 `ELEVENST_DISP_CTGR_NO` 에 넣으세요.

```bash
python -m scripts.verify_market_connections 11st
```

### 🛍️ 4-4. Shopify

| 항목 | 내용 |
|------|------|
| ① 키 발급 | Shopify Admin → **Apps → Develop apps** → 앱 생성 → Admin API access token(`shpat_...`) |
| ② 환경변수 | `SHOPIFY_SHOP`(=`내상점.myshopify.com`) · `SHOPIFY_AUTO_TOKEN`(`atk_...` 우선) · `SHOPIFY_CLIENT_SECRET` |
| 🔁 별칭 허용 | `SHOPIFY_AUTO_TOKEN` 없으면 `SHOPIFY_ACCESS_TOKEN`(레거시)도 동작 |
| 필요 권한(scope) | `read_products`, `write_products`, `read_inventory`, `write_inventory`, `read_orders`, `write_orders` |
| 상세 문서 | `docs/operations/SHOPIFY_MARKET.md` |

```bash
python -m scripts.verify_market_connections shopify
```

### 🟣 4-5. WooCommerce (코가네멀티샵 자체몰)

| 항목 | 내용 |
|------|------|
| ① 키 발급 | WordPress 관리자 → **WooCommerce → 설정 → 고급 → REST API** → 키 생성(권한: Read/Write) |
| ② 환경변수 | `WC_URL` · `WC_KEY` · `WC_SECRET` |
| 🔁 별칭 허용 | `WOO_BASE_URL` · `WOO_CK` · `WOO_CS` 로 넣어도 동작합니다 |
| 상세 문서 | `docs/operations/WOOCOMMERCE_MARKET.md` |

```bash
python -m scripts.verify_market_connections woocommerce
```

---

## 5. 첫 테스트 업로드 (진짜로 올라가는지 확인)

연결이 `✅ 연결됨`으로 바뀌면, 실제 상품을 1개만 올려서 끝까지 확인합니다.

1. 셀러 콘솔에서 **상품 수집** → `/seller/collect` 에서 아무 상품이나 한 개 수집
2. **미리보기 화면**에서 **📤 마켓에 등록** 버튼 클릭
3. 모달 3단계를 따릅니다:
   - **마켓 선택 + 마진율** 지정
   - **🔍 사전검증** → `✅ 통과` 가 떠야 다음 단계로 갑니다
     - 여기서 막히면 화면의 **💡 조치** 문구대로 해결 (대부분 키/가격/이미지 문제)
   - **업로드 실행** → 성공하면 **"상품 페이지 열기"** 링크가 생깁니다. 눌러서 실제 등록을 눈으로 확인!
4. 실패하면 화면에 **오류코드 + 💡 조치**가 정직하게 표시됩니다. 표(2번 섹션)를 참고해 해결하세요.

> ✅ **"상품 페이지 열기" 링크가 열리고 실제 마켓에 상품이 보이면 라이브 연동 완료입니다.**

---

## 6. 자주 막히는 곳 (트러블슈팅)

| 증상 | 원인 | 해결 |
|------|------|------|
| 키 넣었는데 계속 `token_missing` | 재배포 전 / 변수 이름 오타 / 값에 공백 | Render 재배포 대기 후 재실행, 변수명·값 재확인 |
| `api_error` 가 뜸 | 키 오타, 권한 부족, 마켓 점검 중 | 키 재발급, 앱 권한(scope) 추가, 잠시 후 재시도 |
| 사전검증에서 `image_inaccessible` | 이미지 URL이 외부 접근 불가 | 공개적으로 열리는 이미지 URL 사용 |
| 사전검증에서 `missing_field` | 상품명/판매가 비어있음 | 상품명 입력 또는 마진 계산기로 판매가 산정 |
| 11번가만 카테고리 오류 | 셀러별 카테고리 번호 불일치 | `ELEVENST_DISP_CTGR_NO` 에 본인 카테고리 번호 설정 |
| 네이버가 안 됨 | 변수 이름 두 종류 혼동 | `NAVER_CLIENT_ID/SECRET` **한 쌍**만 정확히 |

---

## 7. 최종 체크리스트

- [ ] 각 마켓 판매자센터에서 API 키 발급 완료
- [ ] Render 환경변수에 키 등록 + 재배포 완료
- [ ] `python -m scripts.verify_market_connections` → 목표 마켓 `✅ 연결됨`
- [ ] 테스트 상품 1개 업로드 → **"상품 페이지 열기"** 링크로 실제 등록 확인
- [ ] (운영 기록) `docs/HANDOFF.md` 에 마지막 라이브 검증 날짜/결과 남기기

---

## 부록. 환경변수 한눈에 보기

| 마켓 | 필수 환경변수 | 별칭(있으면 이것도 가능) |
|------|--------------|------------------------|
| 쿠팡 | `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY`, `COUPANG_VENDOR_ID` | — |
| 스마트스토어 | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | `NAVER_COMMERCE_CLIENT_ID`, `NAVER_COMMERCE_CLIENT_SECRET` |
| 11번가 | `ELEVENST_API_KEY` | `ELEVENST_DISP_CTGR_NO`(선택, 기본 카테고리) |
| Shopify | `SHOPIFY_SHOP`, `SHOPIFY_AUTO_TOKEN`, `SHOPIFY_CLIENT_SECRET` | `SHOPIFY_ACCESS_TOKEN`(레거시 토큰) |
| WooCommerce | `WC_URL`, `WC_KEY`, `WC_SECRET` | `WOO_BASE_URL`, `WOO_CK`, `WOO_CS` |
