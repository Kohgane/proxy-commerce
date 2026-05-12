# VERSIONING.md — Phase 버전 자동화 가드

## 개요

Proxy Commerce는 화면 템플릿에 `"Phase NNN"`을 하드코딩하지 않습니다.
모든 페이지는 `current_phase` 변수를 사용해 동적으로 렌더링합니다.

## 구조

```
src/version.py
  CURRENT_PHASE = ...       ← Phase PR마다 이 줄만 변경
  APP_VERSION = ...
  get_current_phase()       ← CURRENT_PHASE_OVERRIDE env 우선
  get_version_string()      ← 'Phase N · x.y.z' 형식
```

## 템플릿 사용

`src/templates/landing.html` 푸터:

```html
<span>Phase {{ current_phase }}</span>
```

## 라우트 주입

`src/order_webhook.py` 랜딩 뷰:

```python
from src.version import get_current_phase
return render_template('landing.html', version=version, current_phase=get_current_phase())
```

## CI 빌드 주입

CI 파이프라인에서 ROADMAP.md 최신 Phase를 자동 추출하여 주입:

```bash
export CURRENT_PHASE_OVERRIDE=$(grep -oP '## Phase \K\d+' ROADMAP.md | sort -n | tail -1)
```

## 회귀 방지 (Phase 하드코딩 금지) — Phase 151.1 3차 강화

`tests/test_version_display.py`:
- `current_phase` 동적 렌더 사용 확인

`tests/test_no_hardcoded_phase.py`:
- seller/admin AI 템플릿 영역에 특정 `Phase NNN` 하드코딩 문자열이 남아있으면 실패

`tests/test_no_hardcoded_phase_strict.py` (Phase 151.1 신규):
- `templates/` HTML 파일 전체: HTML 주석 외 `Phase NNN` 하드코딩 금지
- `src/ai_listing/` Python 파일: 따옴표 안 `Phase NNN` 문자열 리터럴 금지
- `src/ai_listing/routes.py` API 응답 문자열 검사
- `src/dashboard/admin_views.py` AI 카드 섹션 검사

화이트리스트 (검사 제외):
- `ROADMAP.md`, `CHANGELOG.md`, `src/version.py` (파일)
- `docs/` (디렉터리)
- Python docstring/주석 라인
- `{{ current_phase }}` 동적 템플릿 변수

## Phase 업데이트 절차

1. `src/version.py`의 `CURRENT_PHASE` 값을 새 Phase 번호로 변경
2. `tests/test_version_display.py`의 `test_current_phase_is_148()` 테스트 업데이트
3. `ROADMAP.md`에 새 Phase 섹션 추가
4. PR 병합 → 배포 → 푸터 확인
