# CSP 정책 가이드 (Content Security Policy)

Phase 124에서 경로별 CSP 분기가 도입됐습니다.

## 경로별 CSP 정책 표

| 경로 패턴 | 정책 타입 | CDN 허용 | 인라인 JS/CSS |
|---|---|---|---|
| `/admin/*` | HTML 페이지 | ✅ cdn.jsdelivr.net | ✅ |
| `/seller/*` | HTML 페이지 | ✅ cdn.jsdelivr.net | ✅ |
| `/api/docs` | HTML 페이지 | ✅ cdn.jsdelivr.net | ✅ |
| `/` (루트 및 기타) | HTML 페이지 | ✅ cdn.jsdelivr.net | ✅ |
| `/api/v1/*` | API JSON 응답 | ❌ strict | ❌ |
| `/api/dashboard/*` | API JSON 응답 | ❌ strict | ❌ |
| `/webhook/*` | 웹훅 응답 | ❌ strict | ❌ |
| `/health/*` | 헬스체크 응답 | ❌ strict | ❌ |

## 정책 상수 (src/middleware/security.py)

### HTML 페이지용 (_CSP_HTML_PAGES)
```
default-src 'self';
style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;
script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;
font-src 'self' https://cdn.jsdelivr.net data:;
img-src 'self' data: https:;
connect-src 'self';
object-src 'none';
frame-ancestors 'none'
```

### API 응답용 (_CSP_API)
```
default-src 'none';
frame-ancestors 'none'
```

## 새로운 외부 리소스 추가 시

새로운 CDN이나 외부 도메인을 추가해야 하는 경우:

1. `src/middleware/security.py` 파일 열기
2. `_CSP_HTML_PAGES` 상수에서 해당 디렉티브에 도메인 추가

예시 — Google Fonts 추가:
```python
_CSP_HTML_PAGES = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com data:; "
    ...
)
```

3. `tests/test_security_middleware.py`의 `test_csp_html_page_allows_cdn` 테스트 업데이트

## 보안 원칙

- **API/웹훅 응답**: 브라우저에서 직접 렌더링되지 않으므로 `default-src 'none'` 유지
- **HSTS, X-Frame-Options, X-Content-Type-Options**: 모든 경로에 공통 적용 (변경 불가)
- `unsafe-eval` 은 허용하지 않음 (필요한 경우 nonce 방식으로 전환 검토)
