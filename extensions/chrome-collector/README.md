# 코가네 퍼센티 수집기 — 크롬 확장

한 클릭으로 쇼핑 페이지의 상품 정보를 코가네 퍼센티에 수집합니다.

## 설치 방법 (개발자 모드)

1. 크롬 브라우저에서 `chrome://extensions/` 접속
2. 우측 상단 **개발자 모드** 활성화
3. **압축 해제된 확장 프로그램 로드** 클릭
4. `extensions/chrome-collector/` 폴더 선택

## 설정

1. 확장 아이콘 우클릭 → **옵션** (또는 설정 팝업에서 ⚙️ 클릭)
2. **서버 URL** 입력: `https://kohganepercentiii.com`
3. **Personal Access Token** 입력
   - 서버 로그인 후 `/seller/me/tokens`에서 발급
   - `collect.write` 권한 필요

## 사용 방법

### 방법 1: 아이콘 클릭
1. 쇼핑 페이지에서 상품 페이지 접속
2. 확장 아이콘 클릭
3. **이 상품 수집하기** 버튼 클릭
4. 알림 + 텔레그램으로 결과 확인

### 방법 2: 우클릭 컨텍스트 메뉴
1. 상품 페이지에서 우클릭
2. **코가네 퍼센티에 보내기** 선택

## 지원 사이트

모든 사이트 지원 (범용 수집기).  
JSON-LD/OG 메타태그가 있는 사이트는 자동으로 더 정확하게 추출.

특화 지원:
- aloyoga.com
- lululemon.com
- marketstudio.com
- pleasuresnow.com
- yoshidakaban.com

## 트러블슈팅

### 토큰 오류
→ `/seller/me/tokens`에서 새 토큰 발급 후 옵션 페이지에서 업데이트

### 수집 실패
→ 서버 URL 확인 (기본: `https://kohganepercentiii.com`)  
→ 네트워크 연결 확인  
→ 서버 상태: `/health`

### CORS 오류
→ 확장은 content_script에서 직접 메타를 추출하므로 CORS 미발생  
→ 서버 API만 CORS 허용 필요 (기본 설정으로 허용됨)

## 웹스토어 등록 (향후)

1. `build.sh` 실행 → `dist/kohgane-chrome-collector-vX.X.X.zip` 생성
2. [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole) 접속
3. "새 항목" 업로드 → ZIP 파일 선택
4. 스크린샷, 설명 작성 후 제출
