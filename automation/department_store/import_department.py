"""
KOHGANE 백화점 - 1,080개 자동 임포트
======================================
스마트스토어 1,080개 → 멀티샵 8개 층 카테고리

기능:
- SKU 기반 중복 체크 (기존 191개는 자동 대체)
- 카테고리별 마진 자동 적용
- 8개 백화점 층 자동 생성
- 자식 카테고리 (중분류) 자동 생성
- 진행률 텔레그램 알림 (10%마다)

환경변수 (GitHub Secrets):
- WC_URL, WC_KEY, WC_SECRET (WooCommerce REST API)
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (선택)
"""

import os
import sys
import csv
import time
import requests
from collections import defaultdict
from urllib.parse import quote

# ===== 환경 변수 =====
WC_URL = os.environ.get('WC_URL', '').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT = os.environ.get('TELEGRAM_CHAT_ID', '')
CSV_PATH = os.environ.get('CSV_PATH', 'store.csv')

if not all([WC_URL, WC_KEY, WC_SECRET]):
    print("❌ WC credentials missing")
    sys.exit(1)

# ===== 백화점 매핑 규칙 =====
DEPARTMENT_FLOORS = {
    '1F Fragrance Hall': {
        'slug': 'fragrance-hall',
        'description': '여행과 장소의 기억. 향으로 담은 한 시간.',
        'margin': 1.20,  # +20%
    },
    '2F Living Hall': {
        'slug': 'living-hall',
        'description': '일상의 결을 만드는 가구와 인테리어.',
        'margin': 1.12,
    },
    '3F Tabletop': {
        'slug': 'tabletop',
        'description': '식탁 위의 작은 의식. 디자이너의 주방.',
        'margin': 1.15,
    },
    '4F Tech': {
        'slug': 'tech',
        'description': '미니멀과 럭셔리의 만남. 손에 닿는 디자인.',
        'margin': 1.05,
    },
    '5F Wear & Et Cetera': {
        'slug': 'wear-etc',
        'description': '한 켤레의 핸드메이드. 한 손의 헤리티지.',
        'margin': 1.10,
    },
    '6F Active & Outdoor': {
        'slug': 'active-outdoor',
        'description': '자연과 함께. 모험과 함께.',
        'margin': 1.10,
    },
    'B1F Body & Beauty': {
        'slug': 'body-beauty',
        'description': '느린 일상을 위한 의례.',
        'margin': 1.12,
    },
    'BF Food Hall': {
        'slug': 'food-hall',
        'description': '한 입의 행복.',
        'margin': 1.08,
    },
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


# ===== HTTP =====
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/json',
}

session = requests.Session()
session.auth = (WC_KEY, WC_SECRET)
session.headers.update(HEADERS)


def telegram_send(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            'chat_id': TELEGRAM_CHAT,
            'text': msg,
            'parse_mode': 'HTML',
        }, timeout=10)
    except Exception:
        pass


# ===== 카테고리 관리 =====
category_cache = {}

def get_or_create_category(name, parent_id=0, slug=None, description=''):
    cache_key = f"{name}__{parent_id}"
    if cache_key in category_cache:
        return category_cache[cache_key]
    
    # 기존 카테고리 검색
    try:
        resp = session.get(
            f"{WC_URL}/wp-json/wc/v3/products/categories",
            params={'search': name, 'parent': parent_id, 'per_page': 50},
            timeout=30
        )
        if resp.status_code == 200:
            for cat in resp.json():
                if cat['name'] == name and cat['parent'] == parent_id:
                    category_cache[cache_key] = cat['id']
                    return cat['id']
    except Exception as e:
        print(f"  카테고리 검색 실패: {e}")
    
    # 새 카테고리 생성
    payload = {
        'name': name,
        'parent': parent_id,
    }
    if slug:
        payload['slug'] = slug
    if description:
        payload['description'] = description
    
    try:
        resp = session.post(
            f"{WC_URL}/wp-json/wc/v3/products/categories",
            json=payload, timeout=30
        )
        if resp.status_code in (200, 201):
            cat_id = resp.json()['id']
            category_cache[cache_key] = cat_id
            print(f"  ✅ 카테고리 생성: {name} (ID: {cat_id})")
            return cat_id
    except Exception as e:
        print(f"  카테고리 생성 실패 ({name}): {e}")
    
    return None


# ===== 상품 관리 =====
def find_product_by_sku(sku):
    try:
        resp = session.get(
            f"{WC_URL}/wp-json/wc/v3/products",
            params={'sku': sku}, timeout=30
        )
        if resp.status_code == 200:
            products = resp.json()
            if products:
                return products[0]['id']
    except Exception:
        pass
    return None


def upsert_product(product_data):
    sku = product_data.get('sku', '')
    
    existing_id = find_product_by_sku(sku) if sku else None
    
    try:
        if existing_id:
            # 업데이트
            resp = session.put(
                f"{WC_URL}/wp-json/wc/v3/products/{existing_id}",
                json=product_data, timeout=60
            )
            return resp.status_code == 200, 'updated'
        else:
            # 생성
            resp = session.post(
                f"{WC_URL}/wp-json/wc/v3/products",
                json=product_data, timeout=60
            )
            return resp.status_code in (200, 201), 'created'
    except Exception as e:
        print(f"  상품 처리 실패 ({sku}): {e}")
        return False, 'error'


# ===== 매핑 로직 =====
def map_to_floor(big, mid):
    floor = MID_TO_FLOOR.get(mid)
    if not floor:
        floor = BIG_FALLBACK.get(big)
    return floor


def calculate_price(original_price_str, margin):
    try:
        price = int(original_price_str.replace(',', '').replace('원', '').strip())
        new_price = int(price * margin)
        # 천원 단위 반올림
        new_price = round(new_price / 1000) * 1000
        return str(new_price)
    except (ValueError, AttributeError):
        return original_price_str


# ===== 메인 =====
def main():
    print("=" * 60)
    print("🏬 KOHGANE Department Store - 1,080개 임포트")
    print("=" * 60)
    
    telegram_send("🏬 KOHGANE 백화점 임포트 시작 (1,080개)")
    
    # 1. CSV 읽기
    if not os.path.exists(CSV_PATH):
        print(f"❌ CSV 없음: {CSV_PATH}")
        sys.exit(1)
    
    with open(CSV_PATH, 'r', encoding='cp949') as f:
        rows = list(csv.DictReader(f))
    
    print(f"\n📦 총 상품: {len(rows)}개")
    
    # 2. 백화점 층 카테고리 미리 생성
    print("\n🏛️ 백화점 층 카테고리 생성 중...")
    floor_ids = {}
    for floor_name, info in DEPARTMENT_FLOORS.items():
        cat_id = get_or_create_category(
            name=floor_name,
            parent_id=0,
            slug=info['slug'],
            description=info['description']
        )
        floor_ids[floor_name] = cat_id
        time.sleep(0.5)
    
    # 3. 상품별 임포트
    print(f"\n🚀 상품 임포트 시작...")
    
    stats = defaultdict(int)
    
    for i, row in enumerate(rows, 1):
        big = row.get('대분류', '').strip()
        mid = row.get('중분류', '').strip()
        sub = row.get('소분류', '').strip()
        name = row.get('상품명', '').strip()
        sku_code = row.get('판매자상품코드', '').strip()
        price_str = row.get('판매가', '0')
        image_url = row.get('대표이미지 URL', '').strip()
        stock = row.get('재고수량', '0')
        
        if not name or not sku_code:
            stats['skipped'] += 1
            continue
        
        # 백화점 층
        floor = map_to_floor(big, mid)
        if not floor:
            stats['unmapped'] += 1
            continue
        
        floor_id = floor_ids.get(floor)
        margin = DEPARTMENT_FLOORS[floor]['margin']
        
        # 자식 카테고리 (중분류)
        category_ids = []
        if floor_id:
            category_ids.append({'id': floor_id})
        
        if mid:
            sub_id = get_or_create_category(name=mid, parent_id=floor_id)
            if sub_id:
                category_ids.append({'id': sub_id})
        
        # 가격 계산
        new_price = calculate_price(price_str, margin)
        
        # 재고
        try:
            stock_qty = int(stock)
        except:
            stock_qty = 0
        
        # SKU
        sku = f"KGN-{sku_code[:20]}"
        
        # 상품 데이터
        product_data = {
            'name': name,
            'sku': sku,
            'type': 'simple',
            'regular_price': new_price,
            'description': f'<p>{name}</p>',
            'short_description': f'{floor.split(" ", 1)[1] if " " in floor else floor}',
            'manage_stock': True,
            'stock_quantity': stock_qty,
            'stock_status': 'instock' if stock_qty > 0 else 'outofstock',
            'categories': category_ids,
            'status': 'publish',
        }
        
        if image_url and image_url.startswith('http'):
            product_data['images'] = [{'src': image_url}]
        
        # 임포트
        success, action = upsert_product(product_data)
        if success:
            stats[action] += 1
        else:
            stats['failed'] += 1
        
        # 진행률
        if i % 10 == 0:
            percent = i * 100 // len(rows)
            print(f"  [{i:4d}/{len(rows)}] {percent}% - {floor[:25]:<25} | {name[:40]}")
        
        # 10%마다 텔레그램
        if i % 108 == 0:
            telegram_send(f"📊 진행률: {i}/{len(rows)} ({i*100//len(rows)}%)")
        
        time.sleep(0.3)  # API rate limit
    
    # 4. 결과
    print("\n" + "=" * 60)
    print("✅ 임포트 완료")
    print("=" * 60)
    print(f"  생성: {stats['created']}개")
    print(f"  업데이트: {stats['updated']}개")
    print(f"  스킵: {stats['skipped']}개")
    print(f"  매핑실패: {stats['unmapped']}개")
    print(f"  실패: {stats['failed']}개")
    
    summary = (
        f"🏬 KOHGANE 백화점 임포트 완료\n\n"
        f"✅ 생성: {stats['created']}\n"
        f"🔄 업데이트: {stats['updated']}\n"
        f"⏭️ 스킵: {stats['skipped']}\n"
        f"❌ 실패: {stats['failed']}"
    )
    telegram_send(summary)


if __name__ == '__main__':
    main()
