"""
KOHGANE - 메모파리 50개 카테고리 재정렬
=========================================
기존 카테고리 (Living/Limited/Curated 등) → 신규 (Fragrance > Memo Paris)
"""

import os
import requests
import time
from typing import List, Optional

WC_URL = os.environ.get('WC_URL', '').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')

if not WC_KEY:
    print("❌ WC_KEY required")
    exit(1)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
}

session = requests.Session()
session.auth = (WC_KEY, WC_SECRET)
session.headers.update(HEADERS)


def get_or_find_category(name: str, parent_id: int = 0) -> Optional[int]:
    """카테고리 검색 (이미 만든 거 가정)"""
    try:
        resp = session.get(
            f"{WC_URL}/wp-json/wc/v3/products/categories",
            params={'search': name, 'per_page': 100},
            timeout=15
        )
        if resp.status_code == 200:
            for cat in resp.json():
                if cat.get('name') == name and cat.get('parent') == parent_id:
                    return cat['id']
    except Exception:
        pass
    return None


def get_memo_products() -> List[dict]:
    """SKU가 MP-로 시작하는 모든 상품"""
    products = []
    page = 1
    while True:
        try:
            resp = session.get(
                f"{WC_URL}/wp-json/wc/v3/products",
                params={
                    'per_page': 100,
                    'page': page,
                    'status': 'publish',
                },
                timeout=30
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            
            # SKU 필터
            for p in data:
                sku = p.get('sku', '')
                if sku.startswith('MP-'):
                    products.append(p)
            
            page += 1
            if len(data) < 100:
                break
        except Exception as e:
            print(f"Error: {e}")
            break
    return products


def update_product_categories(product_id: int, new_cat_ids: List[int]) -> bool:
    """상품의 카테고리 교체 (기존 다 제거하고 새로 설정)"""
    payload = {
        'categories': [{'id': cid} for cid in new_cat_ids]
    }
    try:
        resp = session.put(
            f"{WC_URL}/wp-json/wc/v3/products/{product_id}",
            json=payload,
            timeout=30
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


def main():
    print("=" * 70)
    print("📂 KOHGANE Memo Paris Recategorization")
    print("=" * 70)
    
    # Find target categories
    fragrance_id = get_or_find_category('Fragrance')
    if not fragrance_id:
        print("❌ 'Fragrance' 카테고리 없음 — 먼저 만드세요")
        return
    
    memo_id = get_or_find_category('Memo Paris', parent_id=fragrance_id)
    
    if memo_id:
        target_cats = [fragrance_id, memo_id]
        print(f"✅ 대상: Fragrance ({fragrance_id}) > Memo Paris ({memo_id})")
    else:
        target_cats = [fragrance_id]
        print(f"✅ 대상: Fragrance ({fragrance_id}) 만 (Memo Paris 하위 없음)")
    
    # Get all memo products
    products = get_memo_products()
    print(f"\n메모파리 상품 {len(products)}개 발견\n")
    
    success = 0
    failed = []
    
    for p in products:
        sku = p.get('sku')
        name = p.get('name', '')[:50]
        old_cats = [c.get('name') for c in p.get('categories', [])]
        
        print(f"[{sku}] {name}")
        print(f"  기존: {old_cats}")
        
        if update_product_categories(p['id'], target_cats):
            print(f"  ✅ → Fragrance > Memo Paris")
            success += 1
        else:
            print(f"  ❌ 실패")
            failed.append(sku)
        
        time.sleep(1)
    
    print("\n" + "=" * 70)
    print(f"✅ 성공: {success}/{len(products)}")
    print(f"❌ 실패: {len(failed)}")


if __name__ == '__main__':
    main()
