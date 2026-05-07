"""
KOHGANE - 기존 카테고리 정리 도구
=================================
사용자 확인 후 기존 카테고리 삭제 또는 보관.
"""

import os
import requests

WC_URL = os.environ.get('WC_URL', '').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
}

session = requests.Session()
session.auth = (WC_KEY, WC_SECRET)
session.headers.update(HEADERS)


# 새 구조 카테고리 (보호)
NEW_STRUCTURE = {
    'Fragrance', 'Home', 'Body & Care', 'Tech', 'Footwear',
    'Kids & Baby', 'Bags & Accessories', 'Workspace',
    'Tabletop', 'Candles', 'Bath & Shower', 'Skincare', 'Deodorant',
    'Phone Cases', 'Stand & Wallet',
    'Memo Paris', 'Alessi', 'Molton Brown', 'CASETiFY', 'Rainbow Sandals',
    'Diptyque', 'Yankee Candle', 'Borotalco', 'Bioderma', 'Eucerin',
    'HomeLights', 'La Jolie Muse', 'La Corvette', 'MOFT',
    'Uncategorized',  # 기본
}


def get_all_categories():
    cats = []
    page = 1
    while True:
        resp = session.get(
            f"{WC_URL}/wp-json/wc/v3/products/categories",
            params={'per_page': 100, 'page': page},
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


def main():
    print("=" * 70)
    print("🗑️  KOHGANE Category Cleanup Inspector")
    print("=" * 70)
    
    cats = get_all_categories()
    print(f"전체 카테고리: {len(cats)}개\n")
    
    keep = []
    consider_delete = []
    
    for cat in cats:
        name = cat.get('name', '')
        cat_id = cat.get('id')
        count = cat.get('count', 0)
        
        if name in NEW_STRUCTURE:
            keep.append(cat)
        else:
            consider_delete.append(cat)
    
    print("=" * 70)
    print("✅ 보존 (새 구조)")
    print("=" * 70)
    for cat in sorted(keep, key=lambda x: x.get('name', '')):
        print(f"  [{cat['id']:>4}] {cat['name']:<25} ({cat.get('count', 0)}개 상품)")
    
    print("\n" + "=" * 70)
    print("⚠️  삭제/통합 검토 필요")
    print("=" * 70)
    if not consider_delete:
        print("  (없음)")
    else:
        for cat in sorted(consider_delete, key=lambda x: x.get('name', '')):
            count = cat.get('count', 0)
            warning = "  ⚠️  상품 있음" if count > 0 else "  (비어있음 - 안전 삭제 가능)"
            print(f"  [{cat['id']:>4}] {cat['name']:<25} ({count}개){warning}")
    
    print("\n" + "=" * 70)
    print("💡 처리 방법")
    print("=" * 70)
    print("""
1. 비어있는 카테고리 → 워드프레스에서 직접 삭제
   Products → Categories → 호버 → Delete

2. 상품 있는 카테고리 → 먼저 상품을 새 카테고리로 이동
   - 메모파리 상품: recategorize_memo.py 실행
   - 기타: 수동으로 이동 또는 별도 스크립트

3. 자동 삭제는 신중! 이 스크립트는 진단만 함.
""")


if __name__ == '__main__':
    main()
