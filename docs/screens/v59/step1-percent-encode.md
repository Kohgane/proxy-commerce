# v59 — 북마클릿 엔티티 사망 종결 (percent-encode·zero-entity)

## 근원 (오너 콘솔 캡처)
testpage 북마클릿 클릭 시 `Uncaught SyntaxError: Unexpected token '&'` ×3 — 저장된 북마크 URL에
HTML 엔티티(`&#x27;` 등) 미디코드 잔존. 파일 원본은 구문 정상(파서 통과) → **가져오기·저장 경로의
엔티티 디코드 미보장**이 근원. 엔티티 의존을 제거한다.

## STEP1 — 파일 생성기 퍼센트 인코딩 전환
- `_percent_encode_js(js)`: `%`(최우선)·`& < > " ' +`·모든 비ASCII(한글 토스트)를 %XX(UTF-8)로.
  결과 HREF에 HTML 특수문자 **0개** → 이스케이프·디코드 의존 소멸. 브라우저가 javascript: 실행 시 퍼센트 디코드.
- `_bookmarklet_file_href()`: 동일 페이로드 소스(`_bookmarklet_js`)의 본문만 인코딩(`javascript:` 접두어 리터럴).
- `bookmarklet_file`이 이 HREF 사용. `_netscape_bookmark`의 html.escape는 실질 no-op(엔티티 잔존 0).

### BEFORE → AFTER (진단)
```
BEFORE(html.escape): S=&#x27;...&#x27;   '&' 136개  ← 미디코드 시 Unexpected token '&'
AFTER (percent):     S=%27...%27        '&' 0개 · HTML특수문자 0개 · 디코드==원본 JS ✓
```

### 계약 테스트 (CI 게이트) — test_v59_bookmarklet_percent
- (a) 생성 파일 HREF unescape 없이 추출 → `&` 0개, `< > " '` 0개.
- (b) URI 디코드 → **node --check 구문 통과**.
- (c) 디코드 == 원본 JS **바이트 동일**.
- run.js 로더·ICON v182·PERSONAL_TOOLBAR_FOLDER·빈 앵커·`/bookmarklet/code` 동일 소스 공유 유지.

## STEP2 — 부수 정리
- **favicon-512.png 404 수리**: `bookmarklet_testpage.html`이 존재하지 않는 `favicon-512.png`(og:image·JSON-LD·img)
  참조 → 실존 `icon-512.png`(오너 공식 마크)로 교체(404 소멸).
- v58 규약 '기존 북마크 삭제 후 재설치' 경고 유지(북마클릿 페이지 최상단).

## 오너 검증 (배포 후 실기기)
① 재설치→testpage 초록+버전 토스트 ② 일반몰 1곳 수집 완료 토스트 ③ favicon-512 404 소멸(네트워크 탭).
