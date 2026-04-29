"""
KOHGANE - WooCommerce API 진단 스크립트
=========================================
어디서 막히는지 정확히 파악하기 위한 디버그 도구.
"""
import os
import requests

WC_URL = os.environ.get('WC_URL', '').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')

print("=" * 70)
print("🔍 WooCommerce API Diagnostic")
print("=" * 70)

# Test 1: 환경 변수 확인
print(f"\n[Test 1] Environment variables:")
print(f"  WC_URL exists: {bool(WC_URL)}")
print(f"  WC_URL value: '{WC_URL}'")
print(f"  WC_URL length: {len(WC_URL)}")
print(f"  WC_KEY exists: {bool(WC_KEY)}")
print(f"  WC_KEY length: {len(WC_KEY) if WC_KEY else 0}")
print(f"  WC_KEY starts with 'ck_': {WC_KEY.startswith('ck_') if WC_KEY else False}")
print(f"  WC_SECRET exists: {bool(WC_SECRET)}")
print(f"  WC_SECRET length: {len(WC_SECRET) if WC_SECRET else 0}")
print(f"  WC_SECRET starts with 'cs_': {WC_SECRET.startswith('cs_') if WC_SECRET else False}")

# Test 2: 사이트 접근 가능성 (인증 X)
print(f"\n[Test 2] Site accessibility (no auth):")
try:
    resp = requests.get(WC_URL, timeout=10)
    print(f"  Status: {resp.status_code}")
    print(f"  Final URL after redirects: {resp.url}")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Test 3: REST API endpoint 존재 여부
print(f"\n[Test 3] REST API endpoint:")
try:
    resp = requests.get(f"{WC_URL}/wp-json/wc/v3/", timeout=10)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 401:
        print(f"  → API 엔드포인트 존재. 인증 필요 (정상)")
    elif resp.status_code == 404:
        print(f"  → API 엔드포인트 못 찾음. WooCommerce REST API 활성화 안 됨")
    elif resp.status_code == 200:
        print(f"  → API 엔드포인트 응답")
        print(f"  Response preview: {resp.text[:200]}")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Test 4: 인증된 API 호출
print(f"\n[Test 4] Authenticated API call (list products):")
try:
    resp = requests.get(
        f"{WC_URL}/wp-json/wc/v3/products",
        params={'per_page': 5},
        auth=(WC_KEY, WC_SECRET),
        timeout=15
    )
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        products = resp.json()
        print(f"  ✅ SUCCESS — {len(products)} products returned")
        if products:
            print(f"  First product:")
            p = products[0]
            print(f"    ID: {p.get('id')}")
            print(f"    Name: {p.get('name', '')[:60]}")
            print(f"    SKU: '{p.get('sku', '')}'")
            print(f"    Status: {p.get('status')}")
    elif resp.status_code == 401:
        print(f"  ❌ AUTH FAILED — Consumer Key/Secret 문제")
        print(f"  Response: {resp.text[:300]}")
    elif resp.status_code == 404:
        print(f"  ❌ 404 — REST API 비활성화됐거나 URL 다름")
    else:
        print(f"  ⚠️ Unexpected: {resp.text[:300]}")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Test 5: 검색 가능한 SKU 조회
print(f"\n[Test 5] Test SKU search (MP-EAU-DE-MEMO):")
try:
    resp = requests.get(
        f"{WC_URL}/wp-json/wc/v3/products",
        params={'sku': 'MP-EAU-DE-MEMO'},
        auth=(WC_KEY, WC_SECRET),
        timeout=15
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        results = resp.json()
        print(f"  Results count: {len(results)}")
        if results:
            print(f"  ✅ Found product: {results[0].get('name', '')[:60]}")
        else:
            print(f"  ⚠️ SKU search returned empty.")
            print(f"  → Try listing all products to see actual SKUs")
except Exception as e:
    print(f"  ❌ Error: {e}")

# Test 6: 모든 상품 SKU 확인 (처음 10개)
print(f"\n[Test 6] List all SKUs (first 10):")
try:
    resp = requests.get(
        f"{WC_URL}/wp-json/wc/v3/products",
        params={'per_page': 10},
        auth=(WC_KEY, WC_SECRET),
        timeout=15
    )
    if resp.status_code == 200:
        products = resp.json()
        print(f"  Total products in this batch: {len(products)}")
        for p in products[:10]:
            sku = p.get('sku', '(empty)')
            name = p.get('name', '')[:50]
            print(f"    SKU: '{sku}' | Name: {name}")
    else:
        print(f"  Status: {resp.status_code}")
except Exception as e:
    print(f"  ❌ Error: {e}")

print("\n" + "=" * 70)
print("✅ Diagnostic complete")
print("=" * 70)
