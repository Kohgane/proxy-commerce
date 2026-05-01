# WordPress / WooCommerce 환경변수 매핑

> **규칙**: `WC_*` = **kohganemultishop.org** (Primary, 메인 판매 스토어)  
> **규칙**: `WOO_*` = **kohganewps.org** (Secondary / Legacy 스토어)

---

## 1. 환경변수 매핑 테이블

| 변수 접두사 | 대상 사이트 | 역할 | 비고 |
|-------------|-------------|------|------|
| `WC_URL` | `https://kohganemultishop.org` | Primary API 엔드포인트 | 메인 판매 |
| `WC_KEY` | kohganemultishop.org | Consumer Key | WooCommerce REST API |
| `WC_SECRET` | kohganemultishop.org | Consumer Secret | WooCommerce REST API |
| `WC_WEBHOOK_SECRET` | kohganemultishop.org | 웹훅 서명 검증 키 | |
| `WC_API_VERSION` | - | API 버전 (예: `wc/v3`) | 기본값 `wc/v3` |
| `WOO_BASE_URL` | `https://kohganewps.org` | Secondary/Legacy API 엔드포인트 | 보조 or 마이그레이션 소스 |
| `WOO_CK` | kohganewps.org | Consumer Key | |
| `WOO_CS` | kohganewps.org | Consumer Secret | |
| `WOO_WEBHOOK_SECRET` | kohganewps.org | 웹훅 서명 검증 키 | |
| `WOO_API_VERSION` | - | API 버전 (예: `wc/v3`) | 기본값 `wc/v3` |

---

## 2. `.env` 예시 스니펫

```dotenv
# =====================================================
# WooCommerce — Primary Store (kohganemultishop.org)
# =====================================================
WC_URL=https://kohganemultishop.org
WC_KEY=ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WC_SECRET=cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WC_WEBHOOK_SECRET=your-wc-webhook-secret
WC_API_VERSION=wc/v3

# =====================================================
# WooCommerce — Secondary / Legacy Store (kohganewps.org)
# =====================================================
WOO_BASE_URL=https://kohganewps.org
WOO_CK=ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WOO_CS=cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WOO_WEBHOOK_SECRET=your-woo-webhook-secret
WOO_API_VERSION=wc/v3

# =====================================================
# 런타임 스토어 선택
# =====================================================
WP_PRIMARY=WC        # 업로드 대상 기본 스토어 (WC or WOO)
WP_SECONDARY=WOO     # 폴백 / 레거시 스토어
```

---

## 3. 런타임 선택 전략

```python
import os

WP_PRIMARY   = os.getenv("WP_PRIMARY", "WC")   # 기본: WC (kohganemultishop.org)
WP_SECONDARY = os.getenv("WP_SECONDARY", "WOO") # 폴백: WOO (kohganewps.org)

STORE_CONFIG = {
    "WC": {
        "url":             os.getenv("WC_URL"),
        "consumer_key":    os.getenv("WC_KEY"),
        "consumer_secret": os.getenv("WC_SECRET"),
        "api_version":     os.getenv("WC_API_VERSION", "wc/v3"),
    },
    "WOO": {
        "url":             os.getenv("WOO_BASE_URL"),
        "consumer_key":    os.getenv("WOO_CK"),
        "consumer_secret": os.getenv("WOO_CS"),
        "api_version":     os.getenv("WOO_API_VERSION", "wc/v3"),
    },
}

def get_store_config(store: str = None) -> dict:
    """
    store=None  → WP_PRIMARY 스토어 반환
    store="WC"  → kohganemultishop.org
    store="WOO" → kohganewps.org
    """
    key = store or WP_PRIMARY
    cfg = STORE_CONFIG.get(key)
    if not cfg or not cfg["url"]:
        raise RuntimeError(f"Store config missing for: {key}")
    return cfg
```

---

## 4. 적용 가이드

### Primary 업로드 (기본)

```python
from config.wp_env import get_store_config

cfg = get_store_config()          # WC (kohganemultishop.org)
client = WooCommerceClient(**cfg)
client.create_product(product)
```

### Secondary / 마이그레이션용

```python
cfg = get_store_config("WOO")     # kohganewps.org
legacy_client = WooCommerceClient(**cfg)
products = legacy_client.list_products()
```

### 듀얼 퍼블리시 (두 스토어 동시)

```python
for store_key in [WP_PRIMARY, WP_SECONDARY]:
    cfg = get_store_config(store_key)
    WooCommerceClient(**cfg).create_product(product)
```

---

## 5. 주의사항

- 시크릿 값(`WC_KEY`, `WC_SECRET`, `WOO_CK`, `WOO_CS`)은 절대 코드/문서에 하드코딩 금지
- `.env` 파일은 `.gitignore`에 포함되어 있음 — `.env.example`만 커밋
- GitHub Actions에서는 **Secrets** 탭에 동일한 변수명으로 등록
- PortOne(`PORTONE_*`), 토스(`TOSS_*`) 등 결제 키는 별도 접두사 유지
