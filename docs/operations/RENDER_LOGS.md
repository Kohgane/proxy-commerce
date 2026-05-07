# Render 로그 점검 가이드

## Gunicorn stdout/stderr

Render 배포 스크립트는 아래 옵션으로 표준 출력 로그를 활성화합니다.

```text
--access-logfile -
--error-logfile -
--log-level info
```

`gunicorn.conf.py`에서도 `accesslog='-'`, `errorlog='-'`를 사용합니다.

## Diagnostic Token 로그 검색

검색 키워드:

```text
DIAGNOSTIC TOKEN
```

발급 시 아래 로그가 출력됩니다.

```text
🆘 DIAGNOSTIC TOKEN URL: https://.../auth/diagnostic-token/redeem?token=...
```

## 트러블슈팅

1. 로그가 안 보이면 `GUNICORN_LOG_LEVEL=info` 확인
2. `/auth/diagnostic-token/issue?reveal_safe=1&format=html`로 화면 표시 우선 사용
3. 안정화 후 `DIAGNOSTIC_REVEAL=0`으로 되돌리기
