import os, requests

SHOP = os.getenv('SHOPIFY_SHOP')
TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')
API = f"https://{SHOP}/admin/api/2024-07"

def _headers():
    return {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

def _find_by_sku(sku: str):
    # 간단한 MVP: 제품 전체 조회 후 sku 매칭
    r = requests.get(f"{API}/products.json?limit=250", headers=_headers(), timeout=30)
    r.raise_for_status()
    for p in r.json().get('products', []):
        for v in p.get('variants', []):
            if v.get('sku') == sku:
                return p
    return None

def upsert_product(prod: dict):
    sku = prod['variants'][0]['sku']
    current = _find_by_sku(sku)
    if current:
        pid = current['id']
        u = requests.put(f"{API}/products/{pid}.json", json={"product": prod}, headers=_headers(), timeout=30)
        u.raise_for_status()
        return u.json()['product']
    else:
        c = requests.post(f"{API}/products.json", json={"product": prod}, headers=_headers(), timeout=30)
        c.raise_for_status()
        return c.json()['product']
