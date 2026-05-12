"""src/utils/env_catalog.py — 외부 API 환경변수 카탈로그 (Phase 133).

모든 외부 API 환경변수를 한 곳에서 관리.
- 누락 시 stub 모드로 자동 폴백
- /health/deep 에 어떤 키가 활성/누락인지 노출 (마스킹된 상태로)
- Phase 133: SendGrid → Resend, SweetTracker → TrackingMore 교체 (24개 유지)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Literal, Optional

ApiStatus = Literal["active", "missing"]


class ApiCategory(str, Enum):
    """외부 API 카테고리 분류."""

    MARKETPLACE = "marketplace"    # 쿠팡/스마트스토어/11번가
    SOURCING = "sourcing"          # Amazon/Rakuten
    AI = "ai"                      # OpenAI/DeepL
    PAYMENT = "payment"            # 토스/페이팔
    AUTH = "auth"                  # 카카오/구글/네이버 로그인
    NOTIFICATION = "notification"  # 텔레그램/SendGrid
    LOGISTICS = "logistics"        # 스윗트래커
    SELF_MALL = "self_mall"        # Shopify/WooCommerce
    UTILITY = "utility"            # 환율/이미지
    INFRA = "infra"                # Google Sheets
    CS_BOT = "cs_bot"              # CS 자동응답 봇
    ADS = "ads"                    # 광고 자동 운영
    WHOLESALE = "wholesale"        # B2B 도매 (Phase 148)
    SUBSCRIPTION = "subscription"  # 정기구독 상품 (Phase 148)


# ---------------------------------------------------------------------------
# 별칭 매핑 — 사용자 환경변수 이름 다양성 대응
# ---------------------------------------------------------------------------

ENV_ALIASES: Dict[str, List[str]] = {
    "NAVER_COMMERCE_CLIENT_ID": ["NAVER_COMMERCE_CLIENT_ID", "NAVER_API_CLIENT_ID"],
    "NAVER_COMMERCE_CLIENT_SECRET": ["NAVER_COMMERCE_CLIENT_SECRET", "NAVER_API_CLIENT_SECRET"],
    "WC_URL": ["WC_URL", "WOO_BASE_URL"],
    "WC_KEY": ["WC_KEY", "WOO_CK"],
    "WC_SECRET": ["WC_SECRET", "WOO_CS"],
}


def resolve_env(name: str) -> Optional[str]:
    """별칭 포함하여 환경변수 검색.

    Args:
        name: 기준 환경변수 이름

    Returns:
        최초로 발견된 값, 없으면 None
    """
    aliases = ENV_ALIASES.get(name, [name])
    for alias in aliases:
        val = os.getenv(alias)
        if val:
            return val
    return None


@dataclass
class ApiKey:
    """단일 외부 API 키 정보."""

    name: str
    env_vars: list  # 필요한 모든 환경변수
    purpose: str    # 한국어 용도
    docs_url: str
    category: ApiCategory = ApiCategory.UTILITY
    optional: bool = True

    @property
    def status(self) -> ApiStatus:
        """환경변수 존재 여부로 상태 판단 (별칭 포함)."""
        if all(resolve_env(v) for v in self.env_vars):
            return "active"
        return "missing"

    @property
    def masked_values(self) -> dict:
        """환경변수 값을 마스킹해 반환 (앞4***뒤4)."""
        result = {}
        for v in self.env_vars:
            val = resolve_env(v)
            if val:
                result[v] = val[:4] + "***" + val[-4:] if len(val) > 12 else "***"
            else:
                result[v] = None
        return result


# ---------------------------------------------------------------------------
# 전체 API 레지스트리 — 32개
# ---------------------------------------------------------------------------

API_REGISTRY: list = [
    # ── 마켓플레이스 ──────────────────────────────────────────────────────
    ApiKey(
        name="coupang_wing",
        env_vars=["COUPANG_VENDOR_ID", "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY"],
        purpose="쿠팡 윙 OpenAPI — 상품 등록/주문 조회",
        docs_url="https://wing.coupang.com",
        category=ApiCategory.MARKETPLACE,
    ),
    ApiKey(
        name="naver_commerce",
        env_vars=[
            "NAVER_COMMERCE_CLIENT_ID",
            "NAVER_COMMERCE_CLIENT_SECRET",
            "NAVER_COMMERCE_API_BASE",
            "MARKET_ADAPTER_DEFAULT",
        ],
        purpose="네이버 커머스 API — 스마트스토어",
        docs_url="https://commerce.naver.com",
        category=ApiCategory.MARKETPLACE,
    ),
    ApiKey(
        name="elevenst",
        env_vars=["ELEVENST_API_KEY"],
        purpose="11번가 셀러 API",
        docs_url="https://soffice.11st.co.kr",
        category=ApiCategory.MARKETPLACE,
    ),
    # ── 소싱 ─────────────────────────────────────────────────────────────
    ApiKey(
        name="amazon_paapi",
        env_vars=["AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG"],
        purpose="Amazon Product Advertising API 5.0 — 미국 소싱",
        docs_url="https://affiliate-program.amazon.com",
        category=ApiCategory.SOURCING,
    ),
    ApiKey(
        name="rakuten",
        env_vars=["RAKUTEN_APP_ID"],
        purpose="라쿠텐 Web Service — 일본 소싱",
        docs_url="https://webservice.rakuten.co.jp",
        category=ApiCategory.SOURCING,
    ),
    # ── AI / 번역 ─────────────────────────────────────────────────────────
    ApiKey(
        name="openai",
        env_vars=["OPENAI_API_KEY"],
        purpose="번역 + 광고 카피 자동 생성",
        docs_url="https://platform.openai.com",
        category=ApiCategory.AI,
    ),
    ApiKey(
        name="deepl",
        env_vars=["DEEPL_API_KEY"],
        purpose="번역 (OpenAI 대체, 더 저렴)",
        docs_url="https://www.deepl.com/pro-api",
        category=ApiCategory.AI,
    ),
    # ── 결제 ─────────────────────────────────────────────────────────────
    ApiKey(
        name="toss_payments",
        env_vars=["TOSS_CLIENT_KEY", "TOSS_SECRET_KEY"],
        purpose="토스페이먼츠 - 한국 결제(셀러 SaaS 또는 자체몰)",
        docs_url="https://app.tosspayments.com",
        category=ApiCategory.PAYMENT,
    ),
    ApiKey(
        name="paypal",
        env_vars=["PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"],
        purpose="PayPal - 해외 결제",
        docs_url="https://developer.paypal.com",
        category=ApiCategory.PAYMENT,
    ),
    # ── 인증 ─────────────────────────────────────────────────────────────
    ApiKey(
        name="kakao_login",
        env_vars=["KAKAO_REST_API_KEY", "KAKAO_CLIENT_SECRET"],
        purpose="카카오 로그인",
        docs_url="https://developers.kakao.com",
        category=ApiCategory.AUTH,
    ),
    ApiKey(
        name="google_oauth",
        env_vars=["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"],
        purpose="Google OAuth — 구글 로그인",
        docs_url="https://console.cloud.google.com",
        category=ApiCategory.AUTH,
    ),
    ApiKey(
        name="naver_login",
        env_vars=["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"],
        purpose="네이버 로그인 (커머스 API와 별개)",
        docs_url="https://developers.naver.com",
        category=ApiCategory.AUTH,
    ),
    ApiKey(
        name="admin_bootstrap",
        env_vars=["ADMIN_BOOTSTRAP_TOKEN"],
        purpose="비상 admin 로그인용 부트스트랩 토큰",
        docs_url="https://kohganepercentiii.com/docs/operations/EMERGENCY_ACCESS.md",
        category=ApiCategory.AUTH,
        optional=True,
    ),
    ApiKey(
        name="magic_link",
        env_vars=["BASE_URL", "MAGIC_LINK_TOKENS_PATH"],
        purpose="Magic Link 절대 URL + 토큰 저장 경로",
        docs_url="https://kohganepercentiii.com/docs/operations/EMERGENCY_ACCESS.md",
        category=ApiCategory.AUTH,
        optional=True,
    ),
    ApiKey(
        name="diagnostic_token",
        env_vars=["DIAGNOSTIC_REVEAL", "DIAGNOSTIC_TOKEN_PATH"],
        purpose="Diagnostic Token 화면 노출 동의 + 토큰 저장 경로",
        docs_url="https://kohganepercentiii.com/docs/operations/EMERGENCY_ACCESS.md",
        category=ApiCategory.AUTH,
        optional=True,
    ),
    # ── 알림 ─────────────────────────────────────────────────────────────
    ApiKey(
        name="telegram",
        env_vars=["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
        purpose="텔레그램 알림 - 주문/오류/이벤트",
        docs_url="https://core.telegram.org/bots",
        category=ApiCategory.NOTIFICATION,
    ),
    ApiKey(
        name="resend",
        env_vars=["RESEND_API_KEY"],
        purpose="Resend 이메일 발송 - 주문 확인/알림 (Phase 133+)",
        docs_url="https://resend.com",
        category=ApiCategory.NOTIFICATION,
    ),
    ApiKey(
        name="kakao_alimtalk",
        env_vars=["KAKAO_ALIMTALK_API_KEY", "KAKAO_ALIMTALK_SENDER_KEY"],
        purpose="카카오 알림톡 (한국 고객)",
        docs_url="https://business.kakao.com",
        category=ApiCategory.NOTIFICATION,
    ),
    ApiKey(
        name="line_notify",
        env_vars=["LINE_NOTIFY_TOKEN"],
        purpose="LINE Notify (일본 고객 운영자 알림)",
        docs_url="https://notify-bot.line.me",
        category=ApiCategory.NOTIFICATION,
    ),
    ApiKey(
        name="line_messaging",
        env_vars=["LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_SECRET"],
        purpose="LINE Messaging API (일본 고객 풀 메시징)",
        docs_url="https://developers.line.biz",
        category=ApiCategory.NOTIFICATION,
    ),
    ApiKey(
        name="whatsapp",
        env_vars=["META_WHATSAPP_TOKEN", "META_WHATSAPP_PHONE_ID"],
        purpose="WhatsApp Business (글로벌 고객)",
        docs_url="https://developers.facebook.com/docs/whatsapp",
        category=ApiCategory.NOTIFICATION,
    ),
    ApiKey(
        name="wechat",
        env_vars=["WECHAT_APP_ID", "WECHAT_APP_SECRET"],
        purpose="WeChat 공식계정 (중국 고객)",
        docs_url="https://mp.weixin.qq.com",
        category=ApiCategory.NOTIFICATION,
    ),
    ApiKey(
        name="twilio_sms",
        env_vars=["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"],
        purpose="Twilio SMS (글로벌)",
        docs_url="https://www.twilio.com",
        category=ApiCategory.NOTIFICATION,
    ),
    ApiKey(
        name="aligo_sms",
        env_vars=["ALIGO_API_KEY", "ALIGO_USER_ID", "ALIGO_SENDER"],
        purpose="Aligo SMS (한국, 카카오 알림톡 우회)",
        docs_url="https://smartsms.aligo.in",
        category=ApiCategory.NOTIFICATION,
    ),
    ApiKey(
        name="discord_webhook",
        env_vars=["DISCORD_WEBHOOK_URL"],
        purpose="Discord 운영자 알림",
        docs_url="https://discord.com",
        category=ApiCategory.NOTIFICATION,
    ),
    # ── 물류 ─────────────────────────────────────────────────────────────
    ApiKey(
        name="trackingmore",
        env_vars=["TRACKINGMORE_API_KEY"],
        purpose="TrackingMore 운송장 자동 추적 (Phase 133+)",
        docs_url="https://www.trackingmore.com",
        category=ApiCategory.LOGISTICS,
    ),
    # ── 자체몰 ───────────────────────────────────────────────────────────
    ApiKey(
        name="shopify",
        env_vars=["SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SHOP"],
        purpose="Shopify 자체몰",
        docs_url="https://partners.shopify.com",
        category=ApiCategory.SELF_MALL,
    ),
    ApiKey(
        name="woocommerce",
        env_vars=["WC_KEY", "WC_SECRET", "WC_URL"],
        purpose="WooCommerce 자체몰",
        docs_url="https://woocommerce.com",
        category=ApiCategory.SELF_MALL,
    ),
    # ── 유틸리티 ─────────────────────────────────────────────────────────
    ApiKey(
        name="exchange_rate",
        env_vars=["EXCHANGE_RATE_API_KEY"],
        purpose="실시간 환율 (USD/JPY/EUR/CNY)",
        docs_url="https://app.exchangerate-api.com",
        category=ApiCategory.UTILITY,
    ),
    ApiKey(
        name="pexels",
        env_vars=["PEXELS_API_KEY"],
        purpose="Pexels - 무료 보조 이미지",
        docs_url="https://www.pexels.com/api",
        category=ApiCategory.UTILITY,
    ),
    ApiKey(
        name="unsplash",
        env_vars=["UNSPLASH_ACCESS_KEY"],
        purpose="Unsplash - 무료 보조 이미지",
        docs_url="https://unsplash.com/developers",
        category=ApiCategory.UTILITY,
    ),
    # ── 인프라 ───────────────────────────────────────────────────────────
    ApiKey(
        name="google_sheets",
        env_vars=["GOOGLE_SHEET_ID", "GOOGLE_SERVICE_JSON_B64"],
        purpose="Google Sheets — 카탈로그/주문/재고 저장소",
        docs_url="https://console.cloud.google.com",
        category=ApiCategory.INFRA,
    ),
    # ── Shopify 추가 시크릿 (별도 노출) ──────────────────────────────────
    ApiKey(
        name="shopify_webhook",
        env_vars=["SHOPIFY_CLIENT_SECRET"],
        purpose="Shopify 웹훅 서명 검증",
        docs_url="https://partners.shopify.com",
        category=ApiCategory.SELF_MALL,
    ),
    # ── WooCommerce 별칭 그룹 ─────────────────────────────────────────────
    ApiKey(
        name="woocommerce_alt",
        env_vars=["WOO_CK", "WOO_CS", "WOO_BASE_URL"],
        purpose="WooCommerce 자체몰 (WOO_* 별칭)",
        docs_url="https://woocommerce.com",
        category=ApiCategory.SELF_MALL,
    ),
    # ── 미래 예약 ─────────────────────────────────────────────────────────
    ApiKey(
        name="portone",
        env_vars=["PORTONE_API_KEY", "PORTONE_API_SECRET"],
        purpose="PortOne(아임포트) — 통합 PG (Phase 132)",
        docs_url="https://portone.io",
        category=ApiCategory.PAYMENT,
    ),
    # ── Phase 135: Discovery + Scraper 설정 ──────────────────────────────
    ApiKey(
        name="discovery",
        env_vars=["DISCOVERY_KEYWORDS"],
        purpose="수집 자동 발견 봇 키워드 (Sheets 우선, env 폴백)",
        docs_url="https://kohganepercentiii.com/seller/discovery",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    ApiKey(
        name="scraper",
        env_vars=["SCRAPER_USER_AGENT", "SCRAPER_TIMEOUT_SEC"],
        purpose="수집기 공통 설정 (미설정 시 기본값 사용)",
        docs_url="https://kohganepercentiii.com/docs/operations/COLLECTING.md",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    # ── Phase 136: 자동 가격 조정 엔진 설정 ─────────────────────────────
    ApiKey(
        name="pricing_engine",
        env_vars=[
            "PRICING_MIN_MARGIN_PCT",
            "PRICING_FX_TRIGGER_PCT",
            "PRICING_DRY_RUN",
            "PRICING_NOTIFY_THRESHOLD_PCT",
            "PRICING_CRON_HOUR",
            "PRICING_AUTO_APPLY",
            "PRICING_AUTO_APPLY_THRESHOLD_PCT",
            "PRICING_FX_ALERT_THRESHOLD_PCT",
            "PRICING_MONITOR_INTERVAL_MINUTES",
            "PRICING_MONITOR_ENABLED",
            "COMPETITOR_SCRAPE_FALLBACK_PATH",
        ],
        purpose="자동 가격 조정 엔진 설정 (미설정 시 안전한 기본값 사용)",
        docs_url="https://kohganepercentiii.com/docs/operations/PRICING.md",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    ApiKey(
        name="cs_bot",
        env_vars=[
            "CS_FAQ_FALLBACK_PATH",
            "CS_INBOX_FALLBACK_PATH",
            "CS_AUTO_TRANSLATE",
            "CS_TRANSLATE_PROVIDER",
            "CS_MULTICHANNEL_ENABLED",
            "CS_AUTO_SEND",
            "CS_AUTO_SEND_CATEGORIES",
            "CS_AUTO_SEND_CONFIDENCE_THRESHOLD",
            "CS_AUTO_SEND_DAILY_LIMIT",
            "CS_TELEGRAM_WEBHOOK_SECRET",
        ],
        purpose="CS 자동응답 봇 저장소/번역/다채널/자동발송/웹훅 시크릿 설정",
        docs_url="https://kohganepercentiii.com/docs/operations/CS_BOT.md",
        category=ApiCategory.CS_BOT,
        optional=True,
    ),
    ApiKey(
        name="cs_sla",
        env_vars=[
            "CS_SLA_REFUND_HOURS",
            "CS_SLA_SHIPPING_HOURS",
            "CS_SLA_SIZE_HOURS",
            "CS_SLA_GENERAL_HOURS",
        ],
        purpose="CS SLA 카테고리별 응답 시간 정책",
        docs_url="https://kohganepercentiii.com/docs/operations/CS_BOT.md",
        category=ApiCategory.CS_BOT,
        optional=True,
    ),
    ApiKey(
        name="cs_scheduler",
        env_vars=[
            "CS_SCHEDULER_ENABLED",
            "CS_POLL_INTERVAL_MINUTES",
            "CS_SLA_CHECK_INTERVAL_MINUTES",
            "SCHEDULER_LEADER_TTL_SECONDS",
            "SCHEDULER_HEARTBEAT_SECONDS",
        ],
        purpose="CS 자동 cron 스케줄러 (APScheduler, 멀티워커 잠금)",
        docs_url="https://kohganepercentiii.com/docs/operations/CS_SCHEDULER.md",
        category=ApiCategory.CS_BOT,
        optional=True,
    ),
    ApiKey(
        name="analytics_bi",
        env_vars=["ANALYTICS_CACHE_TTL_SECONDS", "ANALYTICS_FALLBACK_PATH"],
        purpose="셀러 BI 대시보드 캐시 설정",
        docs_url="https://kohganepercentiii.com/docs/operations/ANALYTICS.md",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    ApiKey(
        name="cs_email_imap",
        env_vars=["CS_EMAIL_IMAP_HOST", "CS_EMAIL_IMAP_USER", "CS_EMAIL_IMAP_PASS"],
        purpose="CS 이메일 IMAP 인바운드 채널",
        docs_url="https://kohganepercentiii.com/docs/operations/CS_CHANNELS.md",
        category=ApiCategory.CS_BOT,
        optional=True,
    ),
    ApiKey(
        name="cs_embedding",
        env_vars=["CS_EMBEDDING_PROVIDER", "CS_EMBEDDING_MODEL"],
        purpose="CS FAQ 임베딩 매칭 (OpenAI text-embedding-3-small)",
        docs_url="https://kohganepercentiii.com/docs/operations/CS_CHANNELS.md",
        category=ApiCategory.CS_BOT,
        optional=True,
    ),
    # Phase 144: 광고 자동 운영
    ApiKey(
        name="ads_auto_campaign",
        env_vars=[
            "ADS_AUTO_CAMPAIGN_ENABLED",
            "ADS_AUTO_CAMPAIGN_AUTO_LAUNCH",
            "ADS_DAILY_BUDGET_KRW",
            "ADS_TARGET_ROAS",
            "ADS_BID_ADJUST_MAX_PCT",
        ],
        purpose="광고 자동 운영 — SKU 추출/캠페인 생성/입찰가 조정 (Phase 144)",
        docs_url="https://kohganepercentiii.com/docs/operations/ADS_AUTOMATION.md",
        category=ApiCategory.ADS,
        optional=True,
    ),
    ApiKey(
        name="keyword_optimizer",
        env_vars=["KEYWORD_OPT_PROVIDER"],
        purpose="키워드 입찰 최적화 공급자 (mock | naver_searchad | coupang_ads)",
        docs_url="https://kohganepercentiii.com/docs/operations/KEYWORD_OPTIMIZATION.md",
        category=ApiCategory.ADS,
        optional=True,
    ),
    # Phase 145: 사이드바/주문/CS/배송 자동화
    ApiKey(
        name="sidebar_grouping",
        env_vars=["SIDEBAR_GROUPED"],
        purpose="셀러 콘솔 사이드바 그룹 표시 여부",
        docs_url="https://kohganepercentiii.com/docs/operations/SIDEBAR.md",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    ApiKey(
        name="order_auto_processing",
        env_vars=["ORDER_AUTO_PROCESS_ENABLED", "ORDER_AUTO_PLACE_PO"],
        purpose="주문 자동 검수/발주 자동화 설정 (기본 OFF)",
        docs_url="https://kohganepercentiii.com/docs/operations/ORDER_AUTOMATION.md",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    ApiKey(
        name="shipping_tracker",
        env_vars=["SHIPPING_TRACKER_PROVIDER", "SHIPPING_DELAY_ALERT_HOURS"],
        purpose="배송 모니터링 공급자/지연 알림 임계값",
        docs_url="https://kohganepercentiii.com/docs/operations/SHIPPING_TRACKING.md",
        category=ApiCategory.LOGISTICS,
        optional=True,
    ),
    ApiKey(
        name="cs_unified_inbox",
        env_vars=["CS_UNIFIED_INBOX_ENABLED", "CS_AI_DRAFT_PROVIDER"],
        purpose="CS 통합 인박스 + AI 초안 설정",
        docs_url="https://kohganepercentiii.com/docs/operations/CS_UNIFIED_INBOX.md",
        category=ApiCategory.CS_BOT,
        optional=True,
    ),
    # Phase 146: 반품/정산 자동화
    ApiKey(
        name="returns_automation",
        env_vars=[
            "RETURNS_AUTO_APPROVE_ENABLED",
            "RETURNS_AUTO_APPROVE_MAX_KRW",
            "RETURNS_AUTO_APPROVE_REASONS",
        ],
        purpose="반품/환불 자동 승인 토글 + 금액 한도 + 사유 화이트리스트",
        docs_url="https://kohganepercentiii.com/docs/operations/RETURNS_AUTOMATION.md",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    ApiKey(
        name="settlement_report",
        env_vars=["SETTLEMENT_TAX_RATE_PCT", "SETTLEMENT_REPORT_EMAIL"],
        purpose="정산 리포트 세율/발송 이메일 설정",
        docs_url="https://kohganepercentiii.com/docs/operations/SETTLEMENT.md",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    # Phase 147: PWA + Web Push + 옴니 재고 + 잡 큐
    ApiKey(
        name="pwa",
        env_vars=["PWA_ENABLED", "PWA_APP_NAME"],
        purpose="PWA 활성화 여부 + 앱 이름 (기본: Proxy Commerce)",
        docs_url="https://kohganepercentiii.com/docs/operations/MOBILE_PWA.md",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    ApiKey(
        name="web_push_vapid",
        env_vars=["WEB_PUSH_VAPID_PUBLIC", "WEB_PUSH_VAPID_PRIVATE", "WEB_PUSH_CONTACT_EMAIL"],
        purpose="Web Push VAPID 키쌍 + 관리자 연락처 이메일",
        docs_url="https://kohganepercentiii.com/docs/operations/WEB_PUSH.md",
        category=ApiCategory.NOTIFICATION,
        optional=True,
    ),
    ApiKey(
        name="inventory_omni_sync",
        env_vars=[
            "INVENTORY_OMNI_SYNC_MODE",
            "INVENTORY_OMNI_SYNC_INTERVAL_SEC",
            "INVENTORY_OMNI_SYNC_ENABLED",
        ],
        purpose="옴니채널 재고 동기화 모드/주기/활성화 (기본 OFF)",
        docs_url="https://kohganepercentiii.com/docs/operations/INVENTORY_OMNI.md",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    ApiKey(
        name="job_queue",
        env_vars=[
            "JOB_QUEUE_BACKEND",
            "JOB_QUEUE_MAX_RETRIES",
            "JOB_QUEUE_DEAD_LETTER_DAYS",
        ],
        purpose="멀티워커 잡 큐 백엔드/재시도/데드레터 보관 설정",
        docs_url="https://kohganepercentiii.com/docs/operations/JOB_QUEUE.md",
        category=ApiCategory.UTILITY,
        optional=True,
    ),
    # Phase 148 — B2B 도매
    ApiKey(
        name="wholesale",
        env_vars=[
            "WHOLESALE_ENABLED",
            "WHOLESALE_REQUIRE_BUSINESS_CERT",
            "WHOLESALE_APPLICATIONS_PATH",
        ],
        purpose="B2B 도매 기능 활성화/사업자등록증 필수 여부/신청 저장 경로",
        docs_url="https://kohganepercentiii.com/docs/operations/WHOLESALE.md",
        category=ApiCategory.WHOLESALE,
        optional=True,
    ),
    # Phase 148 — 정기구독 상품
    ApiKey(
        name="product_subscription",
        env_vars=[
            "SUBSCRIPTION_ENABLED",
            "SUBSCRIPTION_PG_PROVIDER",
            "SUBSCRIPTION_RETRY_DAYS",
            "PRODUCT_SUBSCRIPTIONS_PATH",
        ],
        purpose="정기구독 기능 활성화/PG 제공사/재시도 간격/데이터 저장 경로",
        docs_url="https://kohganepercentiii.com/docs/operations/SUBSCRIPTIONS.md",
        category=ApiCategory.SUBSCRIPTION,
        optional=True,
    ),
    # Phase 148 — VAPID 자동 생성
    ApiKey(
        name="vapid_auto_generate",
        env_vars=[
            "VAPID_AUTO_GENERATE",
        ],
        purpose="VAPID 키 자동 생성 허용 여부 (1=허용, 0=수동 설정만)",
        docs_url="https://kohganepercentiii.com/docs/operations/WEB_PUSH.md",
        category=ApiCategory.NOTIFICATION,
        optional=True,
    ),
    # Phase 149 — AI 상품등록 자동화
    ApiKey(
        name="ai_listing",
        env_vars=[
            "AI_LISTING_ENABLED",
            "AI_LISTING_VISION_PROVIDER",
            "AI_LISTING_VISION_MODEL",
            "AI_LISTING_MAX_IMAGES_PER_REQUEST",
            "AI_LISTING_MAX_DAILY_PER_USER",
            "AI_LISTING_CACHE_TTL_HOURS",
            "AI_LISTING_MARKETS_DEFAULT",
            "AI_LISTING_LANG_DEFAULT",
            "AI_LISTING_PRICE_MODE",
            "AI_LISTING_URL_HEAD_CHECK",
            "AI_LISTING_URL_HEAD_CHECK_GET_FALLBACK",
            "AI_LISTING_FORCE_REFRESH_ALLOWED",
            "AI_LISTING_DEBUG_PANEL",
            "AI_LISTING_PROMPT_VERSION",
            "AI_LISTING_CACHE_INCLUDE_PHASE",
            "AI_LISTING_CACHE_INCLUDE_PROMPT_VERSION",
            "AI_LISTING_FORCE_REFRESH_INVALIDATE_ANALYSIS",
            "AI_LISTING_JSONLD_PRIORITY",
            "AI_LISTING_VARIANT_AUTO_EXTRACT",
            "AI_LISTING_PRICE_USE_JSONLD",
            "AI_LISTING_TRANSLATE_DESCRIPTION",
            "FALLBACK_USD_KRW",
            "FALLBACK_JPY_KRW",
            "FALLBACK_EUR_KRW",
            "FALLBACK_CNY_KRW",
        ],
        purpose="AI 상품등록 자동화 — JSON-LD 우선순위/변형 추출/환율 반영 + 캐시 키 정상화 (Phase 151.1)",
        docs_url="https://kohganepercentiii.com/docs/operations/AI_LISTING.md",
        category=ApiCategory.AI,
        optional=True,
    ),
]


# ---------------------------------------------------------------------------
# 공개 조회 함수
# ---------------------------------------------------------------------------


def get_api_status() -> dict:
    """전체 API 상태 반환 — 카테고리별 그루핑 + 요약 통계.

    반환 구조 (백워드 호환: apis 목록 필드 유지):
    {
      "categories": [...],
      "apis": [...],
      "summary": {"total": N, "active": N, "missing": N, "by_category": {...}},
      "render_env_note": "..."
    }
    """
    apis = []
    by_category: dict = {}

    for k in API_REGISTRY:
        cat = k.category.value
        status = k.status
        apis.append(
            {
                "name": k.name,
                "category": cat,
                "status": status,
                "purpose": k.purpose,
                "env_vars": k.masked_values,
                "docs_url": k.docs_url,
                "hint": (
                    f"{k.docs_url} 에서 API 발급 후 "
                    f"{', '.join(k.env_vars)} 등록"
                    if status == "missing"
                    else None
                ),
                "last_ping_at": None,
                "ping_status": None,
            }
        )
        if cat not in by_category:
            by_category[cat] = {"total": 0, "active": 0}
        by_category[cat]["total"] += 1
        if status == "active":
            by_category[cat]["active"] += 1

    total = len(apis)
    active_count = sum(1 for a in apis if a["status"] == "active")
    missing_count = total - active_count

    return {
        "categories": [c.value for c in ApiCategory],
        "apis": apis,
        "summary": {
            "total": total,
            "active": active_count,
            "missing": missing_count,
            "by_category": by_category,
        },
        "render_env_note": (
            "환경변수는 Render Dashboard → proxy-commerce → Environment에 등록해야 합니다. "
            "GitHub Secrets는 인식하지 않습니다."
        ),
    }


def get_api_key(name: str) -> Optional[ApiKey]:
    """이름으로 ApiKey 인스턴스 조회."""
    for k in API_REGISTRY:
        if k.name == name:
            return k
    return None


def is_active(name: str) -> bool:
    """특정 API 활성 여부 확인."""
    k = get_api_key(name)
    return k is not None and k.status == "active"
