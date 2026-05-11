# CODING_GUIDELINES.md

## Python f-string 안전 규칙

- f-string `{ ... }` 표현식 내부에 백슬래시(`\n`, `\t`, `\"` 등)를 직접 넣지 않습니다.
- 줄바꿈/이스케이프가 필요하면 표현식 밖으로 분리된 상수나 변수로 처리합니다.
- Python 3.11 이하 호환을 위해 본 규칙을 항상 적용합니다.

## 라우트 추가 시 필수 체크

1. 사이드바에 링크를 추가하면 실제 라우트도 반드시 등록합니다.
2. `/admin/diagnostics`의 라우트 매트릭스에서 깨진 링크 0건을 확인합니다.
3. `tests/test_sidebar_route_matrix.py`와 `tests/test_no_fstring_backslash.py`를 실행해 회귀를 차단합니다.
