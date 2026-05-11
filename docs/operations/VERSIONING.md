# VERSIONING.md — Phase 버전 자동화 (Phase 148)

## 개요

Phase 148부터 Proxy Commerce는 푸터 버전 번호를 자동으로 관리합니다.
더 이상 `landing.html`에 "Phase NNN"을 하드코딩하지 않습니다.

## 구조

```
src/version.py
  CURRENT_PHASE = 148      ← Phase PR마다 이 줄만 변경
  APP_VERSION = ...         ← APP_VERSION 환경변수 또는 'dev'
  get_current_phase()       ← CURRENT_PHASE_OVERRIDE env 우선
  get_version_string()      ← 'Phase 148 · 1.0.0' 형식
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

## 회귀 방지

`tests/test_version_display.py`:
- `CURRENT_PHASE == 148` 확인
- `landing.html`에 "Phase 123" 하드코딩 없음 확인
- 랜딩 페이지 응답에 "Phase 148" 표시 확인

## Phase 업데이트 절차

1. `src/version.py`의 `CURRENT_PHASE` 값을 새 Phase 번호로 변경
2. `tests/test_version_display.py`의 `test_current_phase_is_148()` 테스트 업데이트
3. `ROADMAP.md`에 새 Phase 섹션 추가
4. PR 병합 → 배포 → 푸터 확인
