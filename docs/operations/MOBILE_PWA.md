# 모바일 반응형 + PWA 운영 가이드 (Phase 147)

## 개요

Phase 147에서 셀러 콘솔이 모바일 반응형 및 PWA(Progressive Web App)를 지원합니다.

## 모바일 반응형

### 개선 사항
- **햄버거 메뉴**: 모바일(768px 이하)에서 사이드바가 drawer로 변환됩니다
- **테이블 스크롤**: 모든 테이블에 `overflow-x: auto` 래퍼가 적용됩니다
- **터치 영역**: 버튼 최소 44px 터치 영역 보장
- **숫자 입력**: `input[type="number"]` 에 numeric keyboard 속성 추가

### 동작
- **데스크톱 (769px+)**: 사이드바 항상 표시
- **모바일 (768px 이하)**: 햄버거(☰) 버튼 탭 → 사이드바 drawer 슬라이드

## PWA 설정

### manifest.json 위치
```
/seller/static/manifest.json  (→ /seller/seller/static/manifest.json)
```

### 주요 설정값

| 항목 | 값 |
|---|---|
| name | Proxy Commerce |
| short_name | Percentiii |
| start_url | /seller/dashboard |
| display | standalone |
| theme_color | #1a1a2e |

### 환경변수

```env
PWA_ENABLED=1          # PWA 활성화 (기본: 1)
PWA_APP_NAME=Proxy Commerce  # 앱 이름 (manifest.json은 정적 파일로 별도 수정 필요)
```

### 아이콘 교체
운영자가 아이콘 교체 시 아래 경로에 파일을 업로드하세요:
- `src/seller_console/static/icon-192.png` (192×192px)
- `src/seller_console/static/icon-512.png` (512×512px)

## Service Worker

### 위치
```
src/seller_console/static/sw.js → /seller/seller/static/sw.js
```

### 캐시 전략
- 정적 자산 (CSS, JS, manifest): 캐시 우선
- 동적 API 요청: 캐시 안 함
- 오프라인 fallback: `/seller/dashboard`

### 보안 고려사항
- 백그라운드 fetch **비활성** (민감 데이터 캐시 방지)
- 같은 origin 요청만 인터셉트

## 홈 화면 추가 방법

1. 스마트폰 Chrome/Safari에서 `https://kohganepercentiii.com/seller/dashboard` 접속
2. 브라우저 메뉴 → "홈 화면에 추가" 또는 "앱 설치"
3. "Proxy Commerce" 아이콘이 홈 화면에 생성됩니다

## 진단

`/admin/diagnostics` → "📱 모바일/PWA (Phase 147)" 섹션에서 상태 확인

## 관련 파일

- `src/seller_console/templates/_base.html` — manifest 링크, SW 등록, hamburger
- `src/seller_console/static/seller.css` — 반응형 CSS
- `src/seller_console/static/manifest.json` — PWA 매니페스트
- `src/seller_console/static/sw.js` — Service Worker
