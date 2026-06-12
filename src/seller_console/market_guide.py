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
            "404 오류가 나면 Vendor ID(A+숫자) 형식이 맞는지 가장 먼저 확인하세요.",
            "오픈API 사용은 일부 계정에서 사전 신청/승인이 필요할 수 있습니다.",
        ],
    },
    {
        "key": "smartstore",
        "label": "스마트스토어 (네이버)",
        "icon": "🟢",
        "official_url": "https://commerce.naver.com",
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
            "‘토큰 발급 실패’가 뜨면 ID/Secret 오타·공백을 확인하세요.",
        ],
    },
    {
        "key": "elevenst",
        "label": "11번가",
        "icon": "🔴",
        "official_url": "https://soffice.11st.co.kr",
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
            {"t": "‘API credentials’에서 Admin API access token 발급", "d": "‘shpat_…’ 형태 토큰입니다. 한 번만 보이니 복사하세요."},
            {"t": "상점 도메인 + 토큰을 아래 입력칸에 붙여넣고 저장", "d": "상점 도메인은 ‘내상점.myshopify.com’ 형태."},
        ],
        "fields": [
            {"env": "SHOPIFY_SHOP", "label": "상점 도메인", "where": "내상점.myshopify.com"},
            {"env": "SHOPIFY_AUTO_TOKEN", "label": "Admin API Token", "where": "‘shpat_…’ 액세스 토큰"},
            {"env": "SHOPIFY_CLIENT_SECRET", "label": "Client Secret(선택)", "where": "웹훅 검증용(있으면 입력)"},
        ],
        "tips": [
            "‘Invalid API key or access token’이 뜨면 토큰을 재발급해 다시 붙여넣으세요.",
            "토큰은 한 번만 노출됩니다. 못 봤으면 새로 발급하면 됩니다.",
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
]


def get_guide() -> List[Dict[str, Any]]:
    return MARKET_GUIDE
