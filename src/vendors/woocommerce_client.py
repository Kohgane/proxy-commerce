import os, requests
from urllib.parse import urljoin

BASE = os.getenv('WOO_BASE_URL')
CK = os.getenv('WOO_CK')
CS = os.getenv('WOO_CS')

def _auth_params():
    return {"consumer_key": CK, "consumer_secret": CS}

def _find_by_sku(sku: str):
    r = requests.get(urljoin(BASE, "/wp-json/wc/v3/products"), params={**_auth_params(), 'sku': sku}, timeout=30)
    r.raise_for_status()
    lst = r.json()
    return lst[0] if lst else None

def upsert_product(prod: dict):
    sku = prod.get('sku') or ''
    found = _find_by_sku(sku)
    if found:
        pid = found['id']
        u = requests.put(urljoin(BASE, f"/wp-json/wc/v3/products/{pid}"), params=_auth_params(), json=prod, timeout=30)
        u.raise_for_status()
        return u.json()
    else:
        c = requests.post(urljoin(BASE, "/wp-json/wc/v3/products"), params=_auth_params(), json=prod, timeout=30)
        c.raise_for_status()
        return c.json()
