"""인앱 마켓 API 키 발급 가이드 콘텐츠.

각 마켓별로 "어디서 키를 받아 → 어떤 칸에 넣는지"를 누구나 한눈에 따라할 수 있게
시각 흐름(flow) + 단계별 설명 + 필드 매핑으로 구조화한다.
화면 렌더는 markets_guide.html 이 담당한다.
"""
from __future__ import annotations

from typing import Any, Dict, List

# 마켓별 발급 가이드. flow = 상단 시각 다이어그램용 짧은 단계 라벨.
MARKET_GUIDE: List[Dict[str, Any]] = [
    {
        "key": "coupang",
        "label": "쿠팡",
        "icon": "🛒",
        "official_url": "https://wing.coupang.com",
        "official_label": "쿠팡 윙(Wing) 열기",
        "flow": ["쿠팡 윙 로그인", "업체정보 → 오픈API", "키 3개 발급/복사", "여기에 붙여넣기"],
        "steps": [
            {"t": "쿠팡 윙(Wing)에 판매자 계정으로 로그인", "d": "wing.coupang.com 접속 후 로그인합니다."},
            {"t": "오른쪽 위 ‘업체정보’ → ‘추가판매정보’ → ‘오픈API 키 발급/관리’ 이동", "d": "메뉴 이름은 계정에 따라 약간 다를 수 있어요. ‘오픈API’ 단어를 찾으세요."},
            {"t": "‘발급’ 버튼을 눌러 Access Key / Secret Key 생성", "d": "Secret Key는 발급 시 한 번만 보입니다. 꼭 복사해 두세요."},
            {"t": "업체코드(Vendor ID) 확인", "d": "‘A’로 시작하는 숫자 코드입니다(예: A00012345). 업체정보 화면에 있습니다."},
            {"t": "복사한 3개 값을 아래 입력칸에 붙여넣고 저장", "d": "[연결 테스트] → ✅ 연결됨 이면 완료."},
        ],
        "fields": [
            {"env": "COUPANG_ACCESS_KEY", "label": "Access Key", "where": "오픈API 발급 화면의 ACCESS KEY"},
            {"env": "COUPANG_SECRET_KEY", "label": "Secret Key", "where": "발급 시 1회만 보이는 SECRET KEY"},
            {"env": "COUPANG_VENDOR_ID", "label": "Vendor ID(업체코드)", "where": "업체정보의 A+숫자 코드"},
        ],
        "tips": [
            "‘your ip address … is not allowed(403)’가 뜨면 서버 IP가 허용목록에 없는 것입니다. "
            "쿠팡 Wing → 오픈API 발급/관리 → ‘API 호출 허용 IP’에 우리 서버 IP를 등록하세요(키는 정상).",
            "‘Invalid signature(401)’가 뜨면 ACCESS KEY/SECRET KEY 값이 정확한지(공백·뒤바뀜 없이) 확인하세요.",
            "404가 나면 Vendor ID(A+숫자) 형식이 맞는지 확인하세요.",
            "‘반품지센터코드를 입력하세요’·‘반품지주소/연락처 값을 확인’ 등 등록 오류가 무더기로 뜨면 "
            "아래 ‘출고지·반품지 정보’ 7칸을 채우세요(키 3개만으론 상품 등록이 안 됩니다).",
        ],
        # 📦 상품 등록 필수 — 키 3개와 별개로 출고지/반품지 정보가 반드시 필요.
        "shipping": {
            "title": "📦 출고지·반품지 정보 — 상품 등록에 꼭 필요해요",
            "why": "쿠팡은 상품을 올릴 때 ‘어디서 보내고(출고지) · 반품을 어디서 받는지(반품지)’를 "
                   "반드시 요구합니다. 이게 없으면 키가 정상이어도 ‘반품지센터코드를 입력하세요’ 같은 "
                   "오류로 등록이 거부돼요. 한 번만 입력하면 이후 모든 상품 등록에 자동으로 쓰입니다.",
            "where_steps": [
                "쿠팡 윙(wing.coupang.com)에 로그인",
                "우측 상단 ‘판매자정보(업체정보)’ 클릭",
                "‘배송정보 관리 / 출고지·반품지 관리’ 메뉴 열기",
                "출고지·반품지가 없으면 먼저 ‘출고지 추가’·‘반품지 추가’로 1개씩 등록",
                "등록된 출고지/반품지를 클릭 → ‘코드(번호)’와 주소·우편번호·연락처를 그대로 복사",
            ],
            "fields": [
                {"env": "COUPANG_VENDOR_USER_ID", "label": "Wing 로그인 ID",
                 "where": "쿠팡 윙에 로그인할 때 쓰는 아이디(이메일/ID). Vendor ID(A+숫자)와 다름", "ex": "mystore@example.com"},
                {"env": "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE", "label": "출고지 코드",
                 "where": "배송정보 관리 → ‘출고지’의 코드(숫자)", "ex": "7437895"},
                {"env": "COUPANG_RETURN_CENTER_CODE", "label": "반품지센터코드",
                 "where": "배송정보 관리 → ‘반품지’의 센터코드(숫자)", "ex": "1000274592"},
                {"env": "COUPANG_RETURN_ZIP_CODE", "label": "반품지 우편번호",
                 "where": "반품지 주소의 우편번호(5자리)", "ex": "06236"},
                {"env": "COUPANG_RETURN_ADDRESS", "label": "반품지 주소",
                 "where": "반품을 받을 기본주소", "ex": "서울특별시 강남구 테헤란로 123"},
                {"env": "COUPANG_RETURN_CHARGE_NAME", "label": "반품지 담당자명",
                 "where": "반품을 받는 담당자명 또는 상호", "ex": "코가네CS"},
                {"env": "COUPANG_COMPANY_CONTACT_NUMBER", "label": "반품지 연락처",
                 "where": "반품 문의 전화번호", "ex": "02-123-4567"},
            ],
            "optional_note": "선택: ‘반품지 상세주소(COUPANG_RETURN_ADDRESS_DETAIL)’와 "
                             "‘반품배송비(COUPANG_RETURN_CHARGE, 기본 5000원)’는 비워둬도 됩니다.",
            "tips": [
                "출고지/반품지 ‘코드(숫자)’가 화면에 안 보이면, 해당 출고지·반품지를 클릭해 상세를 열어보세요. "
                "상세 화면 또는 주소창(URL)에 번호가 표시됩니다.",
                "코드를 도저히 못 찾겠으면, ‘출고지 추가’·‘반품지 추가’로 새로 1개씩 만들면 코드가 바로 생깁니다.",
            ],
        },
    },
    {
        "key": "smartstore",
        "label": "스마트스토어 (네이버)",
        "icon": "🟢",
        "official_url": "https://apicenter.commerce.naver.com/ko/basic/main",
        "official_label": "네이버 커머스 API센터 열기",
        "flow": ["커머스 API센터 로그인", "애플리케이션 등록", "ID/Secret 발급", "여기에 붙여넣기"],
        "steps": [
            {"t": "네이버 커머스 API센터(commerce.naver.com) 로그인", "d": "스마트스토어 계정으로 로그인합니다."},
            {"t": "‘애플리케이션 관리’ → ‘애플리케이션 등록’", "d": "판매자용 애플리케이션을 새로 만듭니다."},
            {"t": "애플리케이션 ID(Client ID)와 시크릿(Client Secret) 확인", "d": "Client Secret은 ‘$2a$…’로 시작하는 긴 문자열입니다(전자서명용)."},
            {"t": "필요한 권한(상품 등록/수정, 주문 조회 등) 체크", "d": "권한이 부족하면 등록은 되지만 일부 기능이 막힙니다."},
            {"t": "ID/Secret을 아래 입력칸에 붙여넣고 저장", "d": "[연결 테스트] → ✅ 연결됨 이면 완료."},
        ],
        "fields": [
            {"env": "NAVER_CLIENT_ID", "label": "Client ID", "where": "애플리케이션 정보의 클라이언트 ID"},
            {"env": "NAVER_CLIENT_SECRET", "label": "Client Secret", "where": "‘$2a$…’로 시작하는 클라이언트 시크릿"},
        ],
        "tips": [
            "Client Secret은 반드시 ‘$2a$…’ 형태 전체를 복사하세요(전자서명 생성에 사용).",
            "‘호출이 허용되지 않은 IP(GW.IP_NOT_ALLOWED)’가 뜨면 네이버 커머스 API센터 → 애플리케이션 설정 → "
            "‘허용 IP’에 우리 서버 고정 IP를 등록하세요. (Render 고정 아웃바운드 IP를 추가)",
            "‘토큰 발급 실패’가 뜨면 ID/Secret 오타·공백을 확인하세요.",
        ],
    },
    {
        "key": "elevenst",
        "label": "11번가",
        "icon": "🔴",
        "official_url": "https://openapi.11st.co.kr/",
        "official_label": "11번가 셀러오피스 열기",
        "flow": ["셀러오피스 로그인", "오픈API 신청", "API Key 발급", "여기에 붙여넣기"],
        "steps": [
            {"t": "11번가 셀러오피스(soffice.11st.co.kr) 로그인", "d": "판매자 계정으로 로그인합니다."},
            {"t": "‘오픈API’ 메뉴에서 사용 신청", "d": "11번가는 OpenAPI 사용 신청/승인이 필요합니다(미승인 시 500 오류)."},
            {"t": "승인 후 API Key 발급/확인", "d": "발급된 키 한 개를 복사합니다."},
            {"t": "API Key를 아래 입력칸에 붙여넣고 저장", "d": "[연결 테스트] → ✅ 연결됨 이면 완료."},
        ],
        "fields": [
            {"env": "ELEVENST_API_KEY", "label": "API Key", "where": "오픈API 발급 화면의 키"},
            {"env": "ELEVENST_DISP_CTGR_NO", "label": "기본 카테고리 번호(선택)", "where": "셀러 카테고리 번호(첫 등록 오류 시 입력)"},
        ],
        "tips": [
            "HTTP 500이 뜨면 OpenAPI 사용이 ‘승인’되었는지 먼저 확인하세요.",
            "상품 등록 시 카테고리 오류가 나면 ELEVENST_DISP_CTGR_NO에 본인 카테고리 번호를 넣으세요.",
        ],
    },
    {
        "key": "shopify",
        "label": "Shopify",
        "icon": "🛍️",
        "official_url": "https://www.shopify.com/admin",
        "official_label": "Shopify Admin 열기",
        "flow": ["Admin → Apps", "앱 생성/Develop apps", "Admin API 토큰 발급", "여기에 붙여넣기"],
        "steps": [
            {"t": "Shopify Admin → ‘Settings’ → ‘Apps and sales channels’ → ‘Develop apps’", "d": "커스텀 앱 개발 화면으로 들어갑니다."},
            {"t": "‘Create an app’으로 앱 생성", "d": "이름은 자유(예: ProxyCommerce)."},
            {"t": "‘Configuration’에서 Admin API 권한 부여", "d": "read/write products·inventory·orders 체크."},
            {"t": "토큰 발급/복사", "d": "개발자 대시보드 앱이면 ‘앱 자동화 토큰(atkn_…)’, Admin 커스텀앱이면 ‘Admin API access token(shpat_…)’. 둘 다 동작합니다. ⚠️ ‘Client secret(shpss_…)’이나 ‘API key’가 아닙니다."},
            {"t": "토큰을 발급한 앱이 ‘판매할 상점’에 설치되어 있는지 확인", "d": "토큰은 그 앱이 설치된 상점에서만 동작합니다. 다른 상점 도메인을 넣으면 401."},
            {"t": "상점 도메인 + 토큰을 아래 입력칸에 붙여넣고 저장", "d": "상점 도메인은 ‘내상점.myshopify.com’ 형태."},
        ],
        "fields": [
            {"env": "SHOPIFY_SHOP", "label": "상점 도메인", "where": "내상점.myshopify.com (앱이 설치된 그 상점)"},
            {"env": "SHOPIFY_AUTO_TOKEN", "label": "토큰", "where": "앱 자동화 토큰 atkn_… 또는 shpat_… (secret/API key 아님)"},
            {"env": "SHOPIFY_CLIENT_SECRET", "label": "Client Secret(선택)", "where": "shpss_… 웹훅 검증용(있으면 입력)"},
        ],
        "tips": [
            "개발자 대시보드 앱은 ‘앱 자동화 토큰(atkn_)’이 Admin API에서 401납니다. 대신 Client ID/Secret을 넣으면 "
            "시스템이 client_credentials로 shpat_ 토큰을 자동 발급해 사용합니다(권장).",
            "Shopify는 IP 허용목록이 없습니다 → 401은 IP가 아니라 토큰/상점 문제입니다.",
            "여전히 실패하면 → 그 앱이 ‘상점 도메인’의 상점에 설치돼 있는지, 도메인이 정확한지 확인하세요.",
        ],
    },
    {
        "key": "woocommerce",
        "label": "WooCommerce (자체몰)",
        "icon": "🟣",
        "official_url": "https://kohganemultishop.org/wp-admin",
        "official_label": "WordPress 관리자 열기",
        "flow": ["WP 관리자 로그인", "WooCommerce → 설정 → 고급 → REST API", "키 생성(Read/Write)", "여기에 붙여넣기"],
        "steps": [
            {"t": "WordPress 관리자(wp-admin) 로그인", "d": "사이트 관리자 계정으로 로그인합니다."},
            {"t": "‘WooCommerce → 설정 → 고급 → REST API’ 이동", "d": "REST API 키 관리 화면입니다."},
            {"t": "‘키 추가(Add key)’ → 권한을 ‘읽기/쓰기(Read/Write)’로 생성", "d": "Consumer key/secret가 생성됩니다."},
            {"t": "사이트 URL + key/secret을 아래 입력칸에 붙여넣고 저장", "d": "[연결 테스트] → ✅ 연결됨 이면 완료."},
        ],
        "fields": [
            {"env": "WC_URL", "label": "사이트 URL", "where": "https://내사이트주소"},
            {"env": "WC_KEY", "label": "Consumer Key", "where": "‘ck_…’ 키"},
            {"env": "WC_SECRET", "label": "Consumer Secret", "where": "‘cs_…’ 시크릿"},
        ],
        "tips": [
            "HTTP 406이 뜨면 사이트 보안(WAF) 때문일 수 있습니다. URL이 https로 정확한지 확인하세요.",
            "권한을 꼭 ‘Read/Write’로 생성하세요(읽기 전용이면 등록 불가).",
        ],
    },
    # ── 글로벌 확장 (어댑터 구현 예정) ─────────────────────────────────────────
    {
        "key": "amazon",
        "label": "Amazon (SP-API)",
        "icon": "🟧",
        "status": "planned",
        "official_url": "https://sellercentral.amazon.com",
        "official_label": "Amazon 셀러 센트럴 열기",
        "flow": ["셀러 가입/개발자 등록", "SP-API 앱 생성", "LWA + Refresh Token 발급", "여기에 저장"],
        "steps": [
            {"t": "Amazon 셀러 센트럴 가입 + 개발자 등록", "d": "Professional 셀러 계정과 개발자 등록이 필요합니다."},
            {"t": "SP-API 애플리케이션 생성(자가 인증 앱)", "d": "App registration에서 SP-API 앱을 만듭니다."},
            {"t": "LWA(클라이언트 ID/Secret) + Refresh Token 발급", "d": "OAuth 인증으로 Refresh Token을 받습니다."},
            {"t": "판매 마켓플레이스(US/JP 등) ID 확인", "d": "마켓플레이스마다 ID가 다릅니다."},
        ],
        "fields": [
            {"env": "AMAZON_LWA_CLIENT_ID", "label": "LWA Client ID", "where": "SP-API 앱의 LWA 클라이언트 ID"},
            {"env": "AMAZON_LWA_CLIENT_SECRET", "label": "LWA Client Secret", "where": "LWA 클라이언트 시크릿"},
            {"env": "AMAZON_REFRESH_TOKEN", "label": "Refresh Token", "where": "OAuth로 발급된 리프레시 토큰"},
            {"env": "AMAZON_MARKETPLACE_ID", "label": "Marketplace ID", "where": "예: US=ATVPDKIKX0DER"},
        ],
        "tips": [
            "Amazon SP-API는 자가 인증 앱 + Refresh Token 방식이 가장 단순합니다.",
            "리스팅 등록은 카탈로그 매칭(GTIN/ASIN) 규칙이 까다로워 사전 준비가 필요합니다.",
        ],
    },
    {
        "key": "ebay",
        "label": "eBay",
        "icon": "🔵",
        "status": "planned",
        "official_url": "https://developer.ebay.com",
        "official_label": "eBay 개발자 포털 열기",
        "flow": ["개발자 가입", "앱 키셋 생성", "User OAuth 토큰 발급", "여기에 저장"],
        "steps": [
            {"t": "eBay 개발자 계정 가입", "d": "developer.ebay.com에서 가입합니다."},
            {"t": "애플리케이션 키셋(App ID/Cert ID) 생성", "d": "Production 키셋을 만듭니다."},
            {"t": "User OAuth 토큰(액세스/리프레시) 발급", "d": "RuName으로 사용자 동의 후 토큰을 받습니다."},
        ],
        "fields": [
            {"env": "EBAY_CLIENT_ID", "label": "App ID (Client ID)", "where": "Production App ID"},
            {"env": "EBAY_CLIENT_SECRET", "label": "Cert ID (Client Secret)", "where": "Production Cert ID"},
            {"env": "EBAY_REFRESH_TOKEN", "label": "Refresh Token", "where": "User OAuth 리프레시 토큰"},
        ],
        "tips": [
            "eBay는 Sandbox/Production 키가 분리되어 있습니다. Production 키를 사용하세요.",
        ],
    },
    {
        "key": "shopee",
        "label": "Shopee",
        "icon": "🟠",
        "status": "planned",
        "official_url": "https://open.shopee.com",
        "official_label": "Shopee Open Platform 열기",
        "flow": ["오픈플랫폼 가입", "앱 생성(partner_id/key)", "샵 인증(shop_id)", "여기에 저장"],
        "steps": [
            {"t": "Shopee Open Platform 가입", "d": "open.shopee.com에서 파트너 등록을 합니다."},
            {"t": "앱 생성 → Partner ID / Partner Key 확인", "d": "앱마다 partner_id와 partner_key가 발급됩니다."},
            {"t": "샵 인증(OAuth) → Shop ID 확인", "d": "판매하려는 샵을 앱에 연결합니다."},
        ],
        "fields": [
            {"env": "SHOPEE_PARTNER_ID", "label": "Partner ID", "where": "오픈플랫폼 앱의 partner_id"},
            {"env": "SHOPEE_PARTNER_KEY", "label": "Partner Key", "where": "앱의 partner_key(서명용)"},
            {"env": "SHOPEE_SHOP_ID", "label": "Shop ID", "where": "샵 인증 후 발급된 shop_id"},
        ],
        "tips": [
            "Shopee는 지역(SG/TH/VN 등)마다 도메인/규정이 다릅니다. 진출 지역을 먼저 정하세요.",
        ],
    },
]


def get_guide() -> List[Dict[str, Any]]:
    return MARKET_GUIDE


def guide_map():
    """key → {official_url, official_label} 빠른 조회(연동 카드 딥링크용)."""
    return {g.get("key"): {"official_url": g.get("official_url", ""),
                            "official_label": g.get("official_label", "발급 페이지 열기")}
            for g in MARKET_GUIDE}
