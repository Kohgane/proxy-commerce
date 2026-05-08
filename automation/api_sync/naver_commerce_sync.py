"""
KOHGANE - 네이버 커머스 API 직접 연동
======================================
스마트스토어 → 멀티샵 완전 자동 동기화 (CSV 불필요)

네이버 커머스 API 사용:
- POST /external/v1/oauth2/token (인증)
- GET /external/v1/products (상품 목록)
- GET /external/v1/products/{productNo} (상세)

환경변수:
- NAVER_COMMERCE_CLIENT_ID
- NAVER_COMMERCE_CLIENT_SECRET
- WC_URL, WC_KEY, WC_SECRET
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- DRY_RUN (true/false)
"""

import os
import sys
import time
import hashlib
import bcrypt
import base64
import requests
from datetime import datetime
from collections import defaultdict

# ===== 인증 정보 =====
NAVER_CLIENT_ID = os.environ.get('NAVER_COMMERCE_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_COMMERCE_CLIENT_SECRET', '')
WC_URL = os.environ.get('WC_URL', '').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT = os.environ.get('TELEGRAM_CHAT_ID', '')
DRY_RUN = os.environ.get('DRY_RUN', 'true').lower() == 'true'

if not all([NAVER_CLIENT_ID, NAVER_CLIENT_SECRET]):
    print("❌ NAVER_COMMERCE 인증 정보 없음")
    sys.exit(1)

if not all([WC_URL, WC_KEY, WC_SECRET]):
    print("❌ WC credentials missing")
    sys.exit(1)

print(f"📍 DRY_RUN: {DRY_RUN}")

# ===== 백화점 매핑 =====
DEPARTMENT_FLOORS = {
    '1F Fragrance Hall': {'slug': 'fragrance-hall', 'margin': 1.12},
    '2F Living Hall': {'slug': 'living-hall', 'margin': 1.12},
    '3F Tabletop': {'slug': 'tabletop', 'margin': 1.18},
    '4F Tech': {'slug': 'tech', 'margin': 1.05},
    '5F Wear & Et Cetera': {'slug': 'wear-etc', 'margin': 1.12},
    '6F Active & Outdoor': {'slug': 'active-outdoor', 'margin': 1.10},
    'B1F Body & Beauty': {'slug': 'body-beauty', 'margin': 1.18},
    'BF Food Hall': {'slug': 'food-hall', 'margin': 1.08},
}

BRAND_MARGIN = {
    'memo paris': 1.12, '메모파리': 1.12,
    'alessi': 1.18,
    'molton brown': 1.20,
    'casetify': 1.05,
    'rainbow sandals': 1.15,
    'bialetti': 1.18,
    'joseph joseph': 1.18,
    'wmf': 1.18,
    'bodum': 1.15,
    'stelton': 1.20,
    'borotalco': 1.12,
    'la corvette': 1.20,
}

MID_TO_FLOOR = {
    '향수': '1F Fragrance Hall',
    '바디케어': 'B1F Body & Beauty', '스킨케어': 'B1F Body & Beauty',
    '메이크업': 'B1F Body & Beauty', '클렌징': 'B1F Body & Beauty',
    '헤어케어': 'B1F Body & Beauty', '네일케어': 'B1F Body & Beauty',
    '미용도구': 'B1F Body & Beauty', '미용소품': 'B1F Body & Beauty',
    '구강용품': 'B1F Body & Beauty', '욕실용품': 'B1F Body & Beauty',
    '면도/제모용품': 'B1F Body & Beauty', '뷰티소품': 'B1F Body & Beauty',
    '인테리어소품': '2F Living Hall', '홈데코': '2F Living Hall',
    '거실가구': '2F Living Hall', '침실가구': '2F Living Hall',
    '서재/사무용가구': '2F Living Hall', '수납가구': '2F Living Hall',
    '수납/정리용품': '2F Living Hall', '생활용품': '2F Living Hall',
    '청소용품': '2F Living Hall', '침구단품': '2F Living Hall',
    '쿠션/방석': '2F Living Hall', '커튼': '2F Living Hall',
    '카펫/러그': '2F Living Hall', '시계/조명': '2F Living Hall',
    '문구/사무용품': '2F Living Hall', '수집품': '2F Living Hall',
    '공구': '2F Living Hall', '유아용품': '2F Living Hall',
    '주방용품': '3F Tabletop', '주방가구': '3F Tabletop',
    '휴대폰액세서리': '4F Tech', '태블릿PC액세서리': '4F Tech',
    '주변기기': '4F Tech', '음향가전': '4F Tech',
    '주방가전': '4F Tech', '생활가전': '4F Tech',
    '계절가전': '4F Tech', 'PC구성품': '4F Tech',
    '태블릿PC': '4F Tech', '컴퓨터': '4F Tech',
    '스마트폰': '4F Tech', '스마트워치': '4F Tech',
    '카메라': '4F Tech', '자동차기기': '4F Tech',
    '게임': '4F Tech', 'PC액세서리': '4F Tech',
    '노트북액세서리': '4F Tech',
    '남성가방': '5F Wear & Et Cetera', '여성가방': '5F Wear & Et Cetera',
    '여행용가방/소품': '5F Wear & Et Cetera', '지갑': '5F Wear & Et Cetera',
    '여성신발': '5F Wear & Et Cetera', '남성신발': '5F Wear & Et Cetera',
    '주얼리': '5F Wear & Et Cetera', '시계': '5F Wear & Et Cetera',
    '패션소품': '5F Wear & Et Cetera', '벨트': '5F Wear & Et Cetera',
    '모자': '5F Wear & Et Cetera', '남성의류': '5F Wear & Et Cetera',
    '여성의류': '5F Wear & Et Cetera', '아동의류': '5F Wear & Et Cetera',
    '속옷': '5F Wear & Et Cetera', '신발용품': '5F Wear & Et Cetera',
    '캠핑': '6F Active & Outdoor', '자전거': '6F Active & Outdoor',
    '낚시': '6F Active & Outdoor', '등산': '6F Active & Outdoor',
    '수영': '6F Active & Outdoor', '자동차용품': '6F Active & Outdoor',
    '반려동물': '6F Active & Outdoor', '헬스': '6F Active & Outdoor',
    '요가/필라테스': '6F Active & Outdoor', '골프': '6F Active & Outdoor',
    '기타스포츠용품': '6F Active & Outdoor',
    '건강식품': 'BF Food Hall', '음료': 'BF Food Hall',
    '스낵/과자': 'BF Food Hall', '커피': 'BF Food Hall',
    '차': 'BF Food Hall', '간편식': 'BF Food Hall',
    '조미료': 'BF Food Hall', '젤리/사탕/초콜릿': 'BF Food Hall',
    '잼/시럽': 'BF Food Hall', '다이어트식품': 'BF Food Hall',
    '라면/면류': 'BF Food Hall', '냉동/간편조리식품': 'BF Food Hall',
    '빵/베이커리': 'BF Food Hall',
}

BIG_FALLBACK = {
    '생활/건강': '2F Living Hall',
    '디지털/가전': '4F Tech',
    '가구/인테리어': '2F Living Hall',
    '패션잡화': '5F Wear & Et Cetera',
    '화장품/미용': 'B1F Body & Beauty',
    '스포츠/레저': '6F Active & Outdoor',
    '식품': 'BF Food Hall',
    '패션의류': '5F Wear & Et Cetera',
    '출산/육아': '2F Living Hall',
}

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'


# ============================================
# 네이버 커머스 API
# ============================================

NAVER_API_BASE = 'https://api.commerce.naver.com'


def get_naver_token():
    """
    네이버 커머스 API OAuth2 인증
    bcrypt 시그니처 생성
    """
    timestamp = str(int(time.time() * 1000))
    
    # 시그니처: bcrypt(client_id + "_" + timestamp, client_secret)
    password = f"{NAVER_CLIENT_ID}_{timestamp}".encode('utf-8')
    secret = NAVER_CLIENT_SECRET.encode('utf-8')
    hashed = bcrypt.hashpw(password, secret)
    signature = base64.b64encode(hashed).decode('utf-8')
    
    url = f"{NAVER_API_BASE}/external/v1/oauth2/token"
    
    data = {
        'client_id': NAVER_CLIENT_ID,
        'timestamp': timestamp,
        'client_secret_sign': signature,
        'grant_type': 'client_credentials',
        'type': 'SELF',  # 본인 스토어
    }
    
    try:
        resp = requests.post(url, data=data, timeout=15)
        if resp.status_code == 200:
            token_data = resp.json()
            return token_data.get('access_token')
        else:
            print(f"❌ 토큰 발급 실패: {resp.status_code}")
            print(f"   응답: {resp.text[:300]}")
    except Exception as e:
        print(f"❌ 토큰 요청 에러: {e}")
    
    return None


def get_naver_products(token, page=1, size=100):
    """스마트스토어 상품 목록 조회"""
    url = f"{NAVER_API_BASE}/external/v1/products/search"
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    
    payload = {
        'searchKeywordType': 'CHANNEL_PRODUCT_NO',
        'productStatusTypes': ['SALE'],
        'page': page,
        'size': size,
        'orderType': 'NO',
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"❌ 상품 조회 에러: {e}")
    
    return None


def get_naver_product_detail(token, channel_product_no):
    """상품 상세 조회"""
    url = f"{NAVER_API_BASE}/external/v2/products/channel-products/{channel_product_no}"
    
    headers = {
        'Authorization': f'Bearer {token}',
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    
    return None


# ============================================
# WooCommerce
# ============================================

session = requests.Session()
session.auth = (WC_KEY, WC_SECRET)
session.headers.update({
    'User-Agent': UA,
    'Content-Type': 'application/json',
})

category_cache = {}
sku_cache = set()


def telegram_send(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={'chat_id': TELEGRAM_CHAT, 'text': msg, 'parse_mode': 'HTML'},
            timeout=10
        )
    except Exception:
        pass


def preload_wc_categories():
    print("📂 WC 카테고리 캐시...")
    page = 1
    while True:
        try:
            resp = session.get(
                f"{WC_URL}/wp-json/wc/v3/products/categories",
                params={'per_page': 100, 'page': page}, timeout=30
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            for cat in data:
                key = f"{cat['name']}__{cat['parent']}"
                category_cache[key] = cat['id']
            page += 1
            if len(data) < 100:
                break
        except Exception:
            break
    print(f"  {len(category_cache)}개")


def preload_wc_skus():
    print("📦 WC SKU 캐시...")
    page = 1
    while True:
        try:
            resp = session.get(
                f"{WC_URL}/wp-json/wc/v3/products",
                params={'per_page': 100, 'page': page, '_fields': 'id,sku'},
                timeout=30
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            for prod in data:
                if prod.get('sku'):
                    sku_cache.add(prod['sku'])
            page += 1
            if len(data) < 100:
                break
        except Exception:
            break
    print(f"  {len(sku_cache)}개")


def get_or_create_wc_category(name, parent_id=0, slug=None):
    cache_key = f"{name}__{parent_id}"
    if cache_key in category_cache:
        return category_cache[cache_key]
    
    payload = {'name': name, 'parent': parent_id}
    if slug:
        payload['slug'] = slug
    
    try:
        resp = session.post(
            f"{WC_URL}/wp-json/wc/v3/products/categories",
            json=payload, timeout=15
        )
        if resp.status_code in (200, 201):
            cat_id = resp.json()['id']
            category_cache[cache_key] = cat_id
            return cat_id
    except Exception:
        pass
    return None


def detect_brand(name):
    name_lower = name.lower()
    for brand_key in BRAND_MARGIN:
        if brand_key in name_lower:
            return brand_key
    return None


def get_margin(big, mid, name):
    brand = detect_brand(name)
    if brand:
        return BRAND_MARGIN[brand], brand
    
    floor = MID_TO_FLOOR.get(mid) or BIG_FALLBACK.get(big)
    if floor:
        return DEPARTMENT_FLOORS[floor]['margin'], 'floor'
    
    return 1.10, 'default'


def map_to_floor(big, mid):
    return MID_TO_FLOOR.get(mid) or BIG_FALLBACK.get(big)


def calc_price(price_int, margin):
    new_price = int(price_int * margin)
    return str(round(new_price / 1000) * 1000)


def create_wc_product(product_data):
    try:
        resp = session.post(
            f"{WC_URL}/wp-json/wc/v3/products",
            json=product_data, timeout=30
        )
        if resp.status_code in (200, 201):
            return True, resp.json().get('id')
    except Exception as e:
        print(f"  생성 에러: {e}")
    return False, None


# ============================================
# 메인 동기화
# ============================================

def main():
    print("=" * 60)
    print("🔄 KOHGANE 네이버 커머스 API 직접 동기화")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   DRY_RUN: {DRY_RUN}")
    print("=" * 60)
    
    # 1. 네이버 토큰
    print("\n🔑 네이버 토큰 발급...")
    token = get_naver_token()
    if not token:
        print("❌ 토큰 발급 실패")
        sys.exit(1)
    print(f"  ✅ 토큰 획득 (길이: {len(token)})")
    
    # 2. WC 캐시
    preload_wc_categories()
    preload_wc_skus()
    
    # 3. 백화점 층 확인/생성
    floor_ids = {}
    for floor_name, info in DEPARTMENT_FLOORS.items():
        cat_id = get_or_create_wc_category(
            name=floor_name, parent_id=0, slug=info['slug']
        )
        floor_ids[floor_name] = cat_id
    
    # 4. 네이버 상품 조회 (페이지네이션)
    print("\n📥 스마트스토어 상품 가져오는 중...")
    
    naver_products = []
    page = 1
    
    while True:
        result = get_naver_products(token, page=page, size=100)
        if not result:
            break
        
        contents = result.get('contents', []) or result.get('items', [])
        if not contents:
            break
        
        naver_products.extend(contents)
        print(f"  페이지 {page}: {len(contents)}개 (누적: {len(naver_products)})")
        
        total_elements = result.get('totalElements', 0)
        if len(naver_products) >= total_elements:
            break
        
        page += 1
        time.sleep(0.5)
    
    print(f"\n📦 총 {len(naver_products)}개 가져옴")
    
    # 5. 신규 상품만 필터링 + 동기화
    print("\n🚀 신규 상품 동기화...")
    
    stats = defaultdict(int)
    brand_stats = defaultdict(int)
    new_items = []
    
    for i, item in enumerate(naver_products, 1):
        # 네이버 응답에서 정보 추출
        channel_no = item.get('channelProductNo') or item.get('originProductNo', '')
        seller_code = item.get('sellerManagementCode', '') or str(channel_no)
        name = item.get('name', '').strip()
        sale_price = item.get('salePrice', 0)
        stock = item.get('stockQuantity', 0)
        big = item.get('wholeCategoryName', '').split('>')[0].strip() if item.get('wholeCategoryName') else ''
        category_path = item.get('wholeCategoryName', '').split('>')
        mid = category_path[1].strip() if len(category_path) > 1 else ''
        image_url = item.get('representativeImage', {}).get('url', '') if isinstance(item.get('representativeImage'), dict) else ''
        
        if not name or not seller_code:
            stats['skipped'] += 1
            continue
        
        sku = f"KGN-{seller_code[:20]}"
        
        # 이미 있으면 스킵
        if sku in sku_cache:
            stats['exists'] += 1
            continue
        
        # 백화점 층
        floor = map_to_floor(big, mid)
        if not floor:
            stats['unmapped'] += 1
            continue
        
        floor_id = floor_ids.get(floor)
        
        # 마진
        margin, source = get_margin(big, mid, name)
        brand_stats[source] += 1
        
        # 카테고리
        category_ids = []
        if floor_id:
            category_ids.append({'id': floor_id})
        if mid:
            sub_id = get_or_create_wc_category(name=mid, parent_id=floor_id)
            if sub_id:
                category_ids.append({'id': sub_id})
        
        new_price = calc_price(sale_price, margin)
        
        product_data = {
            'name': name,
            'sku': sku,
            'type': 'simple',
            'regular_price': new_price,
            'description': f'<p>{name}</p>',
            'short_description': floor.split(' ', 1)[1] if ' ' in floor else floor,
            'manage_stock': True,
            'stock_quantity': int(stock) if stock else 0,
            'stock_status': 'instock' if stock else 'outofstock',
            'categories': category_ids,
            'status': 'publish',
        }
        
        if image_url and image_url.startswith('http'):
            product_data['images'] = [{'src': image_url}]
        
        new_items.append({
            'name': name, 'floor': floor, 'price': new_price, 'source': source,
        })
        
        if not DRY_RUN:
            success, new_id = create_wc_product(product_data)
            if success:
                stats['created'] += 1
                sku_cache.add(sku)
            else:
                stats['failed'] += 1
            time.sleep(0.1)
        else:
            stats['would_create'] += 1
    
    # 6. 결과
    print("\n" + "=" * 60)
    if DRY_RUN:
        print(f"🔵 DRY RUN 미리보기")
        print(f"   기존: {stats['exists']}개")
        print(f"   신규(예정): {stats['would_create']}개")
        print(f"   매핑실패: {stats['unmapped']}개")
    else:
        print(f"✅ 완료")
        print(f"   기존: {stats['exists']}개")
        print(f"   신규: {stats['created']}개")
        print(f"   실패: {stats['failed']}개")
    
    print(f"\n[브랜드 마진 분포]")
    for src, c in brand_stats.items():
        print(f"   {src}: {c}개")
    
    if new_items:
        print(f"\n[신규 - 처음 10개]")
        for item in new_items[:10]:
            print(f"   {item['floor'][:25]:<25} | {item['name'][:50]} | ₩{item['price']} | {item['source']}")
    
    # 텔레그램
    if not DRY_RUN and stats['created'] > 0:
        msg = (
            f"🔄 KOHGANE 동기화 (네이버 API)\n\n"
            f"✅ 신규: {stats['created']}\n"
            f"⏭️ 기존: {stats['exists']}\n"
            f"❌ 실패: {stats['failed']}\n"
        )
        if new_items:
            msg += "\n신규 상품:\n"
            for item in new_items[:5]:
                msg += f"• {item['name'][:40]}\n"
        telegram_send(msg)


if __name__ == '__main__':
    main()
