# 도메인 구매 · Cloudflare 연결 가이드

> **대상**: `kohganepercenti.com` → Render 서비스 연결  
> **난이도**: 당나귀도 한 번 읽으면 따라할 수 있도록 매우 상세하게 작성

---

## 목차

1. [도메인 구매 (Cloudflare Registrar)](#1-도메인-구매)
2. [네임서버 확인](#2-네임서버-확인)
3. [Render 커스텀 도메인 추가](#3-render-커스텀-도메인-추가)
4. [Cloudflare DNS 설정](#4-cloudflare-dns-설정)
5. [SSL 인증서 발급 대기](#5-ssl-인증서-발급-대기)
6. [SSL/TLS 모드 설정](#6-ssltls-모드-설정)
7. [HTTPS 강제 리다이렉트 설정](#7-https-강제-리다이렉트)
8. [캐싱 정책](#8-캐싱-정책)
9. [WAF · Bot · Rate Limit 권장 설정](#9-waf--bot--rate-limit)
10. [검증 명령어](#10-검증-명령어)
11. [트러블슈팅 7종](#11-트러블슈팅)
12. [롤백 절차](#12-롤백-절차)

---

## 1. 도메인 구매

### Cloudflare Registrar에서 구매하는 이유

- **원가 판매** (마크업 없음): `.com` 약 $9.77/년
- 구매 즉시 Cloudflare DNS 관리 자동 연결
- 별도 네임서버 변경 불필요

### 단계별 구매 절차

1. 브라우저에서 [https://dash.cloudflare.com](https://dash.cloudflare.com) 접속
2. 로그인 (계정 없으면 우측 상단 **Sign Up**)
3. 좌측 메뉴 **Domain Registration** → **Register Domains** 클릭
4. 검색창에 `kohganepercenti` 입력 → **Search** 클릭
5. `kohganepercenti.com` 항목에서 **Purchase** 클릭

   > 📸 _[스크린샷: 도메인 검색 결과 화면]_

6. **Contact information** 입력 (WHOIS 정보)
   - 이름, 이메일, 주소, 전화번호
   - **Privacy Protection** 체크 (무료 제공 → 개인정보 보호)
7. **Payment** 탭 → 카드 정보 입력 → **Complete Purchase**
8. 구매 완료 이메일 확인

   > 📸 _[스크린샷: 구매 완료 확인 이메일]_

---

## 2. 네임서버 확인

Cloudflare Registrar를 통해 구매한 경우, **네임서버 변경이 자동으로 완료**됩니다.

1. Cloudflare 대시보드 → 좌측 **Websites** → `kohganepercenti.com` 클릭
2. **DNS** 탭에서 현재 네임서버 확인:
   ```
   ns1.cloudflare.com
   ns2.cloudflare.com
   ```
3. 상태가 **Active** 로 표시되면 준비 완료

   > ⏱️ 외부 등록기관(가비아 등)에서 Cloudflare로 이전한 경우 네임서버 전파에 최대 24시간 소요

---

## 3. Render 커스텀 도메인 추가

### Render 대시보드에서 수동 추가

1. [https://dashboard.render.com](https://dashboard.render.com) 접속 → **proxy-commerce** 서비스 클릭
2. 좌측 **Settings** → **Custom Domains** 섹션 클릭
3. **Add Custom Domain** 버튼 클릭
4. `kohganepercenti.com` 입력 → **Save** 클릭

   > 📸 _[스크린샷: Custom Domains 추가 화면]_

5. 동일하게 `www.kohganepercenti.com` 도 추가
6. 추가 완료 후 **DNS 레코드 값** 복사 (아래 단계에서 사용):
   - Render가 제공하는 CNAME 호스트명 (예: `kohganemultishop.onrender.com`)

   > 📸 _[스크린샷: Render가 제공하는 CNAME 값]_

### 자동화 스크립트로 추가 (선택)

```bash
export RENDER_API_TOKEN=<렌더_API_토큰>
python scripts/render_domain_attach.py \
    --service-id srv-d78d5rfkijhs73868f8g \
    --domains kohganepercenti.com www.kohganepercenti.com
```

---

## 4. Cloudflare DNS 설정

### 접속

1. [https://dash.cloudflare.com](https://dash.cloudflare.com) → `kohganepercenti.com` 클릭
2. 상단 **DNS** 탭 클릭 → **DNS Records** 섹션

### 레코드 추가

#### 루트 도메인 (`kohganepercenti.com`)

| 항목 | 값 |
|------|----|
| **Type** | `CNAME` |
| **Name** | `@` (또는 `kohganepercenti.com`) |
| **Target** | `kohganemultishop.onrender.com` |
| **Proxy status** | 🔴 **DNS only** (회색 구름) ← **Free tier 권장** |
| **TTL** | Auto |

> ✅ Cloudflare는 루트 도메인 CNAME을 **CNAME Flattening**으로 자동 처리합니다.

#### www 서브도메인 (`www.kohganepercenti.com`)

| 항목 | 값 |
|------|----|
| **Type** | `CNAME` |
| **Name** | `www` |
| **Target** | `kohganemultishop.onrender.com` |
| **Proxy status** | 🔴 **DNS only** (회색 구름) |
| **TTL** | Auto |

> 📸 _[스크린샷: DNS 레코드 입력 화면]_

### Proxy(주황 구름) ON vs OFF 결정

| 상황 | 설정 | 이유 |
|------|------|------|
| **Render Free tier (현재)** | 🔴 DNS only (OFF) | Render의 TLS 인증서와 Cloudflare의 SSL이 충돌하면 525 에러 발생 |
| **Render Pro + Cloudflare 프록시 활용** | 🟠 Proxied (ON) | DDoS 방어, CDN, WAF 등 Cloudflare 기능 사용 가능 |
| **항상 ON 원하는 경우** | 🟠 Proxied + SSL Full/Strict | Cloudflare Origin Certificate를 Render에 업로드 필요 |

---

## 5. SSL 인증서 발급 대기

DNS 레코드 저장 후 Render가 Let's Encrypt 인증서를 자동 발급합니다.

1. Render 대시보드 → **Settings** → **Custom Domains**
2. 각 도메인 옆 상태가 **Pending** → **Verified** 로 변경될 때까지 대기
3. 소요 시간: 보통 **5~30분** (DNS 전파 완료 후)

   > 📸 _[스크린샷: 도메인 검증 완료 상태]_

---

## 6. SSL/TLS 모드 설정

Cloudflare 대시보드에서 SSL 모드를 설정합니다.

1. `kohganepercenti.com` → **SSL/TLS** 탭 클릭
2. **Overview** → SSL/TLS encryption mode를 **Full** 선택

   > ⚠️ `Flexible`은 사용하지 마세요. 브라우저↔Cloudflare는 HTTPS이지만 Cloudflare↔Render 구간이 HTTP로 전송됩니다.

| 모드 | 브라우저↔CF | CF↔Render | 권장 여부 |
|------|------------|-----------|----------|
| Off | HTTP | HTTP | ❌ |
| Flexible | HTTPS | HTTP | ❌ (Mixed Content) |
| **Full** | HTTPS | HTTPS (인증서 미검증) | ✅ **권장** |
| Full (strict) | HTTPS | HTTPS (인증서 검증) | ✅ Pro 업그레이드 후 권장 |

---

## 7. HTTPS 강제 리다이렉트

1. **SSL/TLS** → **Edge Certificates** 탭
2. **Always Use HTTPS** → 토글 **ON**
3. **HTTP Strict Transport Security (HSTS)** → **Enable HSTS** 클릭
   - `max-age`: **6 months** (15768000)
   - **Include subdomains**: ✅ 체크
   - **Preload**: 선택사항 (한 번 등록하면 취소 어려움 — 신중하게)

---

## 8. 캐싱 정책

**Cache Rules** (또는 구 Page Rules)에서 경로별 캐시 정책을 설정합니다.

### Cache Rules 설정

Cloudflare 대시보드 → **Caching** → **Cache Rules** → **Create rule**

#### 규칙 1: Static 자산 캐시 ON

```
조건: URI Path 시작이 /static/ 또는 /admin/static/
동작: Cache Eligibility = Eligible for cache
      Browser TTL = Respect origin headers
      Edge Cache TTL = 1 day
```

#### 규칙 2: API 캐시 OFF

```
조건: URI Path 시작이 /api/ 또는 /health
동작: Cache Eligibility = Bypass cache
```

---

## 9. WAF · Bot · Rate Limit

### Bot Fight Mode (무료)

1. **Security** → **Bots** → **Bot Fight Mode** → **ON**

### Rate Limiting (유료 기능 — 참고용)

```
경로: /api/*
임계값: 100 req/min per IP
동작: Block (429)
```

### WAF 기본 규칙 (무료 Managed Rules)

1. **Security** → **WAF** → **Managed rules** 탭
2. **Cloudflare Free Managed Ruleset** → **Deploy** 클릭

---

## 10. 검증 명령어

배포 후 다음 명령어로 연결을 확인합니다.

```bash
# DNS 레코드 확인
dig kohganepercenti.com CNAME
dig www.kohganepercenti.com CNAME

# HTTPS 응답 확인
curl -I https://kohganepercenti.com/health
curl -I https://www.kohganepercenti.com/health

# 전체 스모크 테스트
python scripts/render_smoke.py https://kohganepercenti.com

# Cloudflare 자동 설정 스크립트
export CF_API_TOKEN=<토큰>
python scripts/cloudflare_setup.py --apex kohganepercenti.com --dry-run
```

---

## 11. 트러블슈팅

### 🔴 525 — SSL Handshake Failed

- **원인**: Cloudflare 프록시(주황 구름) ON 상태인데 Render 인증서가 아직 발급되지 않음
- **해결**:
  1. Cloudflare DNS 레코드에서 Proxy를 **DNS only(회색)** 로 변경
  2. Render 인증서 발급 완료 후 다시 ON

---

### 🔴 526 — Invalid SSL Certificate

- **원인**: SSL 모드를 `Full (strict)`로 설정했는데 Render 인증서가 유효하지 않음
- **해결**: SSL 모드를 `Full` 로 변경

---

### 🔴 ERR_TOO_MANY_REDIRECTS

- **원인**: Cloudflare SSL 모드가 `Flexible` 인데 앱에서 HTTP→HTTPS 리다이렉트 설정
- **해결**: SSL 모드를 `Full` 로 변경하거나, 앱의 강제 리다이렉트 비활성화

---

### 🔴 Mixed Content 경고

- **원인**: HTTPS 페이지에서 HTTP 리소스(이미지, JS, CSS) 로드
- **해결**:
  1. Cloudflare **SSL/TLS** → **Edge Certificates** → **Automatic HTTPS Rewrites** → ON
  2. 앱 내 하드코딩된 `http://` URL을 상대 경로 또는 `https://` 로 변경

---

### 🔴 인증서 미발급 (Pending 상태 지속)

- **원인**: DNS 전파 지연 또는 CAA 레코드 충돌
- **해결**:
  1. `dig kohganepercenti.com` 으로 DNS가 올바른지 확인
  2. 30분 이상 Pending이면 Render 지원 문의
  3. CAA 레코드 있으면 `0 issue "letsencrypt.org"` 추가

---

### 🔴 www 리다이렉트 안 됨

- **원인**: `www` DNS 레코드 누락
- **해결**: Cloudflare DNS에 `www CNAME → Render 호스트` 레코드 추가

---

### 🔴 도메인 접속 불가 (연결 시간 초과)

- **원인**: DNS 레코드 미설정 또는 Render 서비스 다운
- **해결**:
  1. `ping kohganepercenti.com` 으로 IP 확인
  2. Render 대시보드에서 서비스 상태 확인
  3. `curl https://kohganemultishop.onrender.com/health` 로 직접 접근 테스트

---

### 🔴 Render 도메인 검증 실패

- **원인**: DNS 레코드가 아직 Cloudflare에 전파되지 않음
- **해결**:
  ```bash
  python scripts/render_domain_attach.py --check-only
  ```
  상태가 `pending` 이면 30분 후 재확인

---

## 12. 롤백 절차

DNS만 되돌리면 즉시 복구됩니다 (보통 1~5분 내 TTL 만료 후 적용).

```bash
# Cloudflare DNS에서 CNAME 대상을 이전 도메인으로 변경
# 예: kohganemultishop.onrender.com (Render 기본 도메인)

# 확인
curl -I https://kohganemultishop.onrender.com/health
```

또는 스크립트로 되돌리기:

```bash
export CF_API_TOKEN=<토큰>
python scripts/cloudflare_setup.py \
    --apex kohganepercenti.com \
    --target kohganemultishop.onrender.com
```
