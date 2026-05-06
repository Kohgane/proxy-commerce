# 코가네 퍼센티 수집기 — 크롬 확장

한 클릭으로 쇼핑 페이지의 상품 정보를 코가네 퍼센티에 수집합니다.

---

## 🚀 설치 방법 (개발자 모드 — 당나귀도 할 수 있어)

**준비물**: 크롬 브라우저 + GitHub에서 다운받은 리포 ZIP

1. `chrome://extensions/` 주소창에 입력 → 엔터
2. 우측 상단 **개발자 모드** 토글 → 파란색으로 켜기
3. **압축해제된 확장 프로그램 로드** 버튼 클릭
4. 폴더 선택 창에서 `extensions/chrome-collector/` 폴더 선택 (이 폴더 자체를!)
5. "코가네 퍼센티 수집기" 카드가 나타나면 ✅ 설치 완료

> **주의**: 폴더 안의 파일이 아니라 `chrome-collector/` **폴더 자체**를 선택해야 함.

---

## 🔑 토큰 발급 방법

확장이 서버에 연결하려면 Personal Access Token이 필요합니다.

1. `https://kohganepercentiii.com/auth/login` 접속 → 로그인
2. 사이드바 **🔐 API 토큰** 클릭 (또는 직접 `/seller/me/tokens` 접속)
3. **＋ 새 토큰 발급** 클릭
4. 스코프: `collect.write` 체크 (크롬 확장 필수)
5. 만료: 기본 1년 권장
6. **발급하기** 클릭 → `tok_...` 로 시작하는 64자 토큰이 표시됨
7. **지금 바로 복사** — 이 화면을 벗어나면 영영 다시 볼 수 없음!
8. 1Password, 노트 등 안전한 곳에 붙여넣기

---

## ⚙️ 설정

1. 확장 아이콘 **우클릭** → **옵션** 클릭
   (또는 확장 관리 페이지에서 "세부정보" → "확장 프로그램 옵션")
2. **서버 URL** 입력: `https://kohganepercentiii.com`
3. **Personal Access Token** 입력: 발급한 `tok_...` 토큰 붙여넣기
4. **저장** 클릭 → "✅ 저장되었습니다" 메시지 확인

---

## 📦 사용 방법

### 방법 1: 아이콘 클릭
1. 쇼핑몰 상품 페이지 접속
2. 주소창 오른쪽 **🛒 코가네 아이콘** 클릭
3. **이 상품 수집하기** 버튼 클릭
4. 팝업에 ✅ 표시 + 텔레그램 알림 도착 = 성공

### 방법 2: 우클릭 메뉴
1. 상품 페이지에서 마우스 **우클릭**
2. **코가네 퍼센티에 보내기** 선택
3. 수집 완료 알림 확인

---

## 🏪 지원 사이트

모든 쇼핑몰 지원 (범용 수집기 자동 시도).

특화 지원 (더 정확):

| 사이트 | 특이사항 |
|---|---|
| aloyoga.com | JSON-LD 우선 파싱 |
| lululemon.com | OG 메타 파싱 |
| marketstudio.com | JSON-LD + CSS 폴백 |
| pleasuresnow.com | Shopify `/products/*.json` API |
| yoshidakaban.com | 일본어 → 한국어 자동 번역 + 엔화 변환 |
| 그 외 전체 | JSON-LD → OG → Microdata → Heuristic 순 자동 시도 |

---

## 🛠 트러블슈팅

### ❌ "확장 프로그램을 로드하지 못함. icons/16.png 없음"
> 구버전 `chrome-collector/` 폴더를 사용 중입니다.
> **해결**: GitHub에서 최신 리포 ZIP을 다시 다운로드 → `chrome-collector/` 폴더에 `icons/` 디렉터리가 있는지 확인 → 확장 삭제 후 재설치.

### ❌ "토큰이 설정되지 않았습니다"
> 확장 옵션 페이지에서 Personal Access Token을 입력하지 않았습니다.
> **해결**: [토큰 발급 방법](#-토큰-발급-방법) 참고 → 옵션 페이지에서 토큰 입력 → 저장.

### ❌ "인증 오류 (401)" / "토큰이 유효하지 않습니다"
> 토큰이 만료되었거나 회수된 것입니다.
> **해결**: `/seller/me/tokens`에서 새 토큰 발급 → 옵션 페이지 업데이트.

### ❌ 수집 버튼 눌렀는데 반응 없음
> 1. 서버 URL 확인 (`https://kohganepercentiii.com`, 끝에 `/` 없어야 함)
> 2. 서버 상태 확인: `https://kohganepercentiii.com/health`
> 3. 크롬 확장 콘솔 확인: `chrome://extensions/` → 오류 클릭

### ❌ CORS 오류
> 확장의 content_script가 브라우저 컨텍스트에서 직접 메타를 추출하므로 일반적으로 CORS가 발생하지 않습니다.
> 서버 API(`/api/v1/collect/extension`)는 기본적으로 CORS 허용 설정 포함.

---

## 🗂 파일 구조

```
chrome-collector/
├── manifest.json        # Manifest V3
├── background.js        # Service Worker
├── content_script.js    # 페이지 메타 추출
├── popup.html / popup.js
├── options.html / options.js
├── icons/
│   ├── 16.png
│   ├── 32.png
│   ├── 48.png
│   └── 128.png
├── build.sh             # ZIP 패키징 스크립트
└── README.md
```

---

## 🏗 웹스토어 등록 (향후)

1. `build.sh` 실행 → `dist/kohgane-chrome-collector-vX.X.X.zip` 생성
2. [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole) 접속
3. "새 항목" 업로드 → ZIP 파일 선택
4. 스크린샷, 설명, 개인정보처리방침 URL 입력 후 검토 제출
