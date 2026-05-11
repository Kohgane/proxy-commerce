# ROUTE_REGISTRATION.md — Blueprint 등록 가이드 (Phase 144)

## 개요

Flask 앱(`src/order_webhook.py`)에 모든 Blueprint가 정상 등록되어야 라우트가 작동합니다.
Phase 143에서 sourcing/listing/media 라우트가 404를 반환한 원인과 해결 방법을 설명합니다.

---

## Phase 143 → 144 Hotfix

### 원인

Phase 143에서 `/seller/listing/history`, `/seller/media/queue` 라우트가 추가되지 않았고,
사이드바(`_base.html`)에 소싱/등록/이미지/광고 메뉴가 누락되었습니다.

### 수정 내용

1. `src/seller_console/views.py`에 추가된 라우트:
   - `GET /seller/listing/history` — 등록 이력
   - `GET /seller/media/queue` — 이미지 처리 큐
   - `GET /seller/ads/campaigns` — 광고 캠페인
   - `POST /seller/ads/recommend` — 추천 갱신 API

2. `src/seller_console/templates/_base.html`에 추가된 사이드바 메뉴:
   - 🔎 소싱 watches → `/seller/sourcing/watches`
   - 📥 후보 큐 → `/seller/sourcing/candidates`
   - 📦 등록 이력 → `/seller/listing/history`
   - 🖼️ 이미지 큐 → `/seller/media/queue`
   - 📣 광고 캠페인 → `/seller/ads/campaigns`

---

## Blueprint 등록 체계

모든 Blueprint는 `src/order_webhook.py`에서 `try/except`로 등록됩니다.

```python
try:
    from .seller_console.views import bp as seller_bp
    app.register_blueprint(seller_bp)
    logger.info("셀러 콘솔 Blueprint 등록 완료 (/seller/)")
except Exception as _seller_bp_exc:
    logger.warning("셀러 콘솔 Blueprint 등록 실패: %s", _seller_bp_exc)
```

등록 실패 시 로그에 `WARNING` 레벨로 기록됩니다.

### 주요 Blueprint 목록

| Blueprint | 네임스페이스 | URL Prefix | 추가 Phase |
|---|---|---|---|
| `seller_console` | `seller_console` | `/seller` | Phase 122 |
| `admin_panel` | `admin_panel` | `/admin` | Phase 136 |
| `auth` | `auth` | `/auth` | Phase 133 |
| `cs_bot` | `cs_bot` | `/admin/cs` | Phase 137 |
| `cron` | `cron` | `/cron` | Phase 136 |

---

## 새 라우트 추가 가이드

### 1. `src/seller_console/views.py`에 라우트 추가

```python
@bp.get("/new-feature")
def new_feature():
    """새 기능 페이지."""
    guard = _sourcing_require_admin()  # 관리자 권한 필요 시
    if guard is not None:
        return guard
    from src.dashboard.admin_views import _render
    from markupsafe import Markup
    body = Markup("<h4>새 기능</h4><p>내용</p>")
    return _render("새 기능", body)
```

### 2. 사이드바에 메뉴 추가 (`_base.html`)

```html
<li class="nav-item">
  <a class="nav-link text-secondary {% if page == 'new_feature' %}text-white fw-semibold{% endif %}"
     href="/seller/new-feature">🆕 새 기능</a>
</li>
```

### 3. 회귀 방지 테스트 추가 (`tests/test_route_registration.py`)

`CORE_ROUTES` 리스트에 새 라우트 URL을 추가합니다.

---

## 라우트 점검 — `/admin/diagnostics`

`/admin/diagnostics` → 섹션 13 "라우트 점검"에서:
- 등록된 핵심 라우트 매트릭스 확인
- 누락된 라우트 빨간 배지 표시
- 사이드바 링크 목록 표시

---

## 회귀 방지 테스트

```bash
python3 -m pytest tests/test_route_registration.py tests/test_sidebar_links.py -v
```

- `TestBlueprintRegistration` — 주요 Blueprint 등록 확인
- `TestCoreRoutesNotReturn404` — 핵심 라우트 404 아님 확인
- `TestPhase143RoutesFix` — Phase 143/144 hotfix 라우트 확인
- `TestSidebarLinksPresent` — 사이드바 링크 존재 확인
- `TestSidebarLinksMatchRoutes` — 사이드바 ↔ 라우트 매핑 일치 확인

---

## Phase 148.1 Hotfix 운영 규칙

- `src/order_webhook.py`의 `_auto_register_blueprints()`가 누락된 blueprint 등록을 보조합니다.
- 수동 `app.register_blueprint(...)`는 계속 유지하고, 자동 등록은 안전망으로만 사용합니다.
- `tests/test_sidebar_route_matrix.py`는 셀러 사이드바 템플릿의 `href`를 기준으로 404 회귀를 차단합니다.
- `tests/test_no_fstring_backslash.py`는 Python 3.11 이하에서 import 실패를 유발하는 f-string 표현식 백슬래시 패턴을 차단합니다.
