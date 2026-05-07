"""
KOHGANE - 카테고리 진단 도구
==========================
카테고리별 상품 수 확인 + 문제점 진단.
실제 카테고리에 상품이 어떻게 들어가있는지 보여줌.
"""

import os
import requests

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


def get_all_categories():
    cats = []
    page = 1
    while True:
        resp = session.get(
            f"{WC_URL}/wp-json/wc/v3/products/categories",
            params={'per_page': 100, 'page': page, 'orderby': 'name'},
            timeout=15
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        cats.extend(data)
        page += 1
        if len(data) < 100:
            break
    return cats


def get_products_in_category(cat_id):
    """카테고리에 있는 실제 상품 수 (실시간)"""
    try:
        resp = session.get(
            f"{WC_URL}/wp-json/wc/v3/products",
            params={'category': cat_id, 'per_page': 100, 'status': 'publish'},
            timeout=15
        )
        if resp.status_code == 200:
            return len(resp.json())
    except Exception:
        pass
    return -1


def get_all_products():
    """모든 상품의 카테고리 분포"""
    products = []
    page = 1
    while True:
        try:
            resp = session.get(
                f"{WC_URL}/wp-json/wc/v3/products",
                params={'per_page': 100, 'page': page, 'status': 'publish'},
                timeout=30
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            products.extend(data)
            page += 1
            if len(data) < 100:
                break
        except Exception as e:
            print(f"Error: {e}")
            break
    return products


def main():
    print("=" * 70)
    print("🔍 KOHGANE 카테고리 진단")
    print("=" * 70)
    
    # 1. 모든 카테고리
    cats = get_all_categories()
    print(f"\n[전체 카테고리: {len(cats)}개]\n")
    
    cat_by_id = {c['id']: c for c in cats}
    
    # 2. 카테고리 트리 출력 (parent-child)
    print("=" * 70)
    print("📁 카테고리 트리")
    print("=" * 70)
    
    # 부모 카테고리 (parent=0)
    parents = [c for c in cats if c.get('parent') == 0]
    
    def print_tree(parent_id, indent=0):
        children = [c for c in cats if c.get('parent') == parent_id]
        for c in sorted(children, key=lambda x: x.get('name', '')):
            count = c.get('count', 0)
            real_count = get_products_in_category(c['id'])
            mark = "✅" if count == real_count and count > 0 else ("⚠️" if count != real_count else "  ")
            print(f"{'  ' * indent}{mark} [{c['id']:>4}] {c.get('name', ''):<25} count={count} real={real_count}")
            print_tree(c['id'], indent + 1)
    
    for p in sorted(parents, key=lambda x: x.get('name', '')):
        count = p.get('count', 0)
        real_count = get_products_in_category(p['id'])
        mark = "✅" if count == real_count and count > 0 else ("⚠️" if count != real_count else "  ")
        print(f"{mark} [{p['id']:>4}] {p.get('name', ''):<25} count={count} real={real_count}")
        print_tree(p['id'], 1)
    
    # 3. 상품 분포
    print("\n" + "=" * 70)
    print("🛍️  상품 카테고리 분포")
    print("=" * 70)
    
    products = get_all_products()
    print(f"\n전체 상품: {len(products)}개\n")
    
    cat_to_products = {}
    no_category = []
    
    for p in products:
        prod_cats = p.get('categories', [])
        if not prod_cats:
            no_category.append(p)
        for c in prod_cats:
            cat_id = c.get('id')
            if cat_id not in cat_to_products:
                cat_to_products[cat_id] = []
            cat_to_products[cat_id].append(p)
    
    if no_category:
        print(f"⚠️  카테고리 없는 상품: {len(no_category)}개")
        for p in no_category[:5]:
            print(f"   - {p.get('sku', 'N/A')}: {p.get('name', '')[:60]}")
    
    # SKU prefix별 분포
    sku_prefix_count = {}
    for p in products:
        sku = p.get('sku', '')
        if '-' in sku:
            prefix = sku.split('-')[0]
        else:
            prefix = '(no-prefix)'
        if prefix not in sku_prefix_count:
            sku_prefix_count[prefix] = []
        sku_prefix_count[prefix].append(p)
    
    print(f"\n[SKU prefix별 분포]")
    for prefix, ps in sorted(sku_prefix_count.items(), key=lambda x: -len(x[1])):
        print(f"  {len(ps):4d}  {prefix}")
    
    # 4. 추천 액션
    print("\n" + "=" * 70)
    print("💡 진단 결과")
    print("=" * 70)
    
    issues = []
    for c in cats:
        count = c.get('count', 0)
        real = get_products_in_category(c['id'])
        if count != real:
            issues.append((c, count, real))
    
    if issues:
        print(f"\n⚠️  {len(issues)}개 카테고리에서 count 불일치:")
        for c, count, real in issues[:10]:
            print(f"   - {c.get('name')}: count={count}, 실제={real}")
        print("\n   → 워드프레스 캐시 갱신 필요")
        print("   → WP-Admin → Tools → Site Health → Info → 또는")
        print("   → Settings → Permalinks → Save (재생성)")
    
    duplicates = {}
    for c in cats:
        name = c.get('name', '')
        if name not in duplicates:
            duplicates[name] = []
        duplicates[name].append(c)
    
    dup_found = [(name, lst) for name, lst in duplicates.items() if len(lst) > 1]
    if dup_found:
        print(f"\n⚠️  중복 카테고리 이름 발견:")
        for name, lst in dup_found:
            print(f"   - '{name}': {len(lst)}개 (IDs: {[c['id'] for c in lst]})")
        print("\n   → 같은 이름 카테고리가 여러 개 → 통합 필요")


if __name__ == '__main__':
    main()
