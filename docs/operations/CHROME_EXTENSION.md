# CHROME_EXTENSION.md — 크롬 확장 설치 가이드 (Phase 135)

코가네 퍼센티 수집기 크롬 확장 설치 및 사용 가이드.

---

## 설치 방법 (개발자 모드)

1. 크롬 브라우저에서 `chrome://extensions/` 접속
2. 우측 상단 **개발자 모드** 활성화
3. **압축 해제된 확장 프로그램 로드** 클릭
4. 리포지토리의 `extensions/chrome-collector/` 폴더 선택
5. "코가네 퍼센티 수집기" 확장이 목록에 나타남

---

## 토큰 발급

1. 서버 로그인: `https://kohganepercentiii.com/auth/login`
2. 메뉴: **마이페이지 → API 토큰** (`/seller/me/tokens`)
3. **새 토큰 발급** 클릭
4. 권한 스코프 선택: `collect.write` (최소 필요)
5. 생성된 토큰을 복사 (이후 다시 볼 수 없음)

---

## 설정

1. 확장 아이콘 우클릭 → **옵션** 클릭
2. **서버 URL** 입력: `https://kohganepercentiii.com`
3. **Personal Access Token** 입력 (발급한 토큰 붙여넣기)
4. **저장** 클릭

---

## 사용 방법

### 방법 1: 팝업 클릭
1. 쇼핑몰 상품 페이지 접속
2. 확장 아이콘 클릭
3. **이 상품 수집하기** 버튼 클릭
4. 완료 알림 + 텔레그램 알림 확인

### 방법 2: 우클릭 메뉴
1. 상품 페이지에서 우클릭
2. **코가네 퍼센티에 보내기** 선택

---

## 트러블슈팅

### "토큰이 설정되지 않았습니다" 오류
→ 옵션 페이지에서 Personal Access Token 입력

### 수집 실패
- 서버 URL 확인 (`https://kohganepercentiii.com`)
- 서버 상태 확인: `https://kohganepercentiii.com/health`
- 토큰 유효 기간 확인 (`/seller/me/tokens`)

### CORS 오류 없음
확장은 content_script에서 직접 메타를 추출 → CORS 미발생.

---

## 수집 동작 원리

```
사용자 클릭
    ↓
content_script: JSON-LD/OG 메타 추출 (브라우저 컨텍스트)
    ↓
background.js: 서버로 POST /api/v1/collect/extension
    ↓
서버: ScrapedProduct 생성 → catalog upsert → 텔레그램 알림
    ↓
팝업: 결과 표시 (✅ / ❌)
```

---

## 웹스토어 등록 절차 (향후)

1. `extensions/chrome-collector/build.sh` 실행
2. `dist/kohgane-chrome-collector-vX.X.X.zip` 생성됨
3. [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole) 접속
4. "새 항목" → ZIP 업로드
5. 스크린샷, 설명, 개인정보처리방침 URL 등록
6. 검토 제출 (보통 3~7일 소요)

---

## 지원 사이트

| 사이트 | 어댑터 | 특이사항 |
|---|---|---|
| aloyoga.com | AloAdapter | JSON-LD 우선 |
| lululemon.com | LululemonAdapter | OG 메타 |
| marketstudio.com | MarketStudioAdapter | JSON-LD + CSS 폴백 |
| pleasuresnow.com | PleasuresAdapter | Shopify /products/*.json |
| yoshidakaban.com | YoshidaKabanAdapter | 일본어 번역 + 엔화 변환 |
| 그 외 모든 사이트 | UniversalScraper | JSON-LD → OG → Microdata → Heuristic |
