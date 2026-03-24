"""src/config/schema.py — 설정 스키마 정의.

각 환경변수의 타입, 기본값, 필수 여부, 설명, 그룹을 정의한다.
"""

_CONFIG_SCHEMA = [
    # Google
    {
        "name": "GOOGLE_SERVICE_JSON_B64",
        "type": str,
        "default": "",
        "required": True,
        "description": "Google 서비스 계정 JSON (base64 인코딩)",
        "group": "google",
    },
    {
        "name": "GOOGLE_SHEET_ID",
        "type": str,
        "default": "",
        "required": True,
        "description": "Google Sheets ID",
        "group": "google",
    },
    # Shopify
    {
        "name": "SHOPIFY_SHOP",
        "type": str,
        "default": "",
        "required": False,
        "description": "Shopify 스토어 도메인 (예: mystore.myshopify.com)",
        "group": "shopify",
    },
    {
        "name": "SHOPIFY_ACCESS_TOKEN",
        "type": str,
        "default": "",
        "required": False,
        "description": "Shopify Admin API 액세스 토큰",
        "group": "shopify",
    },
    {
        "name": "SHOPIFY_CLIENT_SECRET",
        "type": str,
        "default": "",
        "required": False,
        "description": "Shopify 웹훅 HMAC 검증용 클라이언트 시크릿",
        "group": "shopify",
    },
    # WooCommerce
    {
        "name": "WOO_BASE_URL",
        "type": str,
        "default": "",
        "required": False,
        "description": "WooCommerce 스토어 기본 URL",
        "group": "woocommerce",
    },
    {
        "name": "WOO_CK",
        "type": str,
        "default": "",
        "required": False,
        "description": "WooCommerce Consumer Key",
        "group": "woocommerce",
    },
    {
        "name": "WOO_CS",
        "type": str,
        "default": "",
        "required": False,
        "description": "WooCommerce Consumer Secret",
        "group": "woocommerce",
    },
    {
        "name": "WOO_WEBHOOK_SECRET",
        "type": str,
        "default": "",
        "required": False,
        "description": "WooCommerce 웹훅 서명 검증 시크릿",
        "group": "woocommerce",
    },
    # Telegram
    {
        "name": "TELEGRAM_BOT_TOKEN",
        "type": str,
        "default": "",
        "required": False,
        "description": "Telegram Bot API 토큰",
        "group": "telegram",
    },
    {
        "name": "TELEGRAM_CHAT_ID",
        "type": str,
        "default": "",
        "required": False,
        "description": "Telegram 채팅 ID",
        "group": "telegram",
    },
    # Translation
    {
        "name": "DEEPL_API_KEY",
        "type": str,
        "default": "",
        "required": False,
        "description": "DeepL 번역 API 키",
        "group": "translation",
    },
    # Server
    {
        "name": "PORT",
        "type": int,
        "default": 8000,
        "required": False,
        "description": "서버 포트 (1-65535)",
        "group": "server",
    },
    {
        "name": "APP_ENV",
        "type": str,
        "default": "development",
        "required": False,
        "description": "애플리케이션 환경 (development | staging | production)",
        "group": "server",
    },
    {
        "name": "APP_VERSION",
        "type": str,
        "default": "dev",
        "required": False,
        "description": "애플리케이션 버전",
        "group": "server",
    },
    # Rate Limiting
    {
        "name": "RATE_LIMIT_ENABLED",
        "type": bool,
        "default": True,
        "required": False,
        "description": "요청 속도 제한 활성화 여부",
        "group": "rate_limiting",
    },
    # Audit
    {
        "name": "AUDIT_LOG_ENABLED",
        "type": bool,
        "default": True,
        "required": False,
        "description": "감사 로그 활성화 여부",
        "group": "audit",
    },
    # Config Management
    {
        "name": "CONFIG_HOT_RELOAD_ENABLED",
        "type": bool,
        "default": False,
        "required": False,
        "description": "설정 파일 변경 시 자동 재로드 활성화 여부",
        "group": "config",
    },
    {
        "name": "CONFIG_CHECK_INTERVAL",
        "type": int,
        "default": 60,
        "required": False,
        "description": "설정 파일 변경 감지 주기 (초)",
        "group": "config",
    },
    {
        "name": "CONFIG_STRICT_VALIDATION",
        "type": bool,
        "default": False,
        "required": False,
        "description": "엄격한 설정 유효성 검증 활성화 여부",
        "group": "config",
    },
    # FX
    {
        "name": "FX_USDKRW",
        "type": float,
        "default": 1350.0,
        "required": False,
        "description": "USD→KRW 환율",
        "group": "fx",
    },
    {
        "name": "FX_JPYKRW",
        "type": float,
        "default": 9.0,
        "required": False,
        "description": "JPY→KRW 환율",
        "group": "fx",
    },
    {
        "name": "FX_EURKRW",
        "type": float,
        "default": 1470.0,
        "required": False,
        "description": "EUR→KRW 환율",
        "group": "fx",
    },
    # Pricing
    {
        "name": "TARGET_MARGIN_PCT",
        "type": float,
        "default": 22.0,
        "required": False,
        "description": "목표 마진율 (%)",
        "group": "pricing",
    },
    {
        "name": "MIN_MARGIN_PCT",
        "type": float,
        "default": 10.0,
        "required": False,
        "description": "최소 마진율 (%)",
        "group": "pricing",
    },
    # Inventory
    {
        "name": "LOW_STOCK_THRESHOLD",
        "type": int,
        "default": 3,
        "required": False,
        "description": "재고 부족 임계값",
        "group": "inventory",
    },
    # Dashboard
    {
        "name": "DASHBOARD_API_ENABLED",
        "type": bool,
        "default": True,
        "required": False,
        "description": "대시보드 API 활성화 여부",
        "group": "dashboard",
    },
    {
        "name": "DASHBOARD_API_KEY",
        "type": str,
        "default": "",
        "required": False,
        "description": "대시보드 API 인증 키",
        "group": "dashboard",
    },
]


def get_all_config_schema() -> list:
    """전체 설정 스키마 목록을 반환한다."""
    return list(_CONFIG_SCHEMA)


def get_schema_by_name(name: str) -> dict:
    """이름으로 스키마 항목을 반환한다. 없으면 None."""
    for entry in _CONFIG_SCHEMA:
        if entry["name"] == name:
            return entry
    return None
