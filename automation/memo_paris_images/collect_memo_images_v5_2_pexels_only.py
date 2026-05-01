"""
KOHGANE - v5.2 RETRY (Pexels Only)
==========================================
Unsplash URL은 워드프레스가 .jpg 인식 못 해서 거부.
Pexels는 URL에 .jpeg 명시되어 있어서 통과.

→ Unsplash 빼고 Pexels만 사용 (3장)
→ 18개 실패한 상품 재처리
"""

import os
import re
import time
import requests
from typing import List, Dict, Optional

WC_URL = os.environ.get('WC_URL', '').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')
PEXELS_KEY = os.environ.get('PEXELS_API_KEY', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

if not WC_KEY or not WC_SECRET:
    print("❌ WC_KEY and WC_SECRET required")
    exit(1)

if not PEXELS_KEY:
    print("❌ PEXELS_API_KEY required")
    exit(1)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
}

session = requests.Session()
session.headers.update(HEADERS)
session.auth = (WC_KEY, WC_SECRET)


# ============================================================
# 18개 + Russian Leather (위에서 빠진 거)
# ============================================================
FAILED_PRODUCTS = [
    ("MP-EAU-DE-MEMO", "Eau de Memo", "eau-de-memo-eau-de-parfum",
        ["birds flying sky", "freedom travel", "vintage notebook"], []),
    ("MP-ODEON", "Odeon", "odeon-eau-de-parfum",
        ["paris rooftops night", "patchouli flower", "rose garden"], []),
    ("MP-ODEON-ROSEBUD", "Odeon Rosebud", "odeon-rosebud-eau-de-parfum",
        ["pink rose petals", "paris romantic", "soft rose"], []),
    ("MP-ODON-X-JEAN-JULLIEN", "Odon X Jean Jullien", "odeon-eau-de-parfum-jean-jullien",
        ["clouds sunset", "abstract art clouds", "paris sky"], []),
    ("MP-QUARTIERLATIN", "Quartier Latin", "quartier-latin-eau-de-parfum",
        ["paris bookshop", "vintage cafe", "old books"], []),
    ("MP-AFRICAN-LEATHER", "African Leather", "african-leather-eau-de-parfum",
        ["african sunset", "leather texture", "saffron"], []),
    ("MP-ITALIAN-LEATHER", "Italian Leather", "italian-leather-eau-de-parfum",
        ["italian leather", "tomato leaves", "italy countryside"], []),
    ("MP-FRENCH-LEATHER", "French Leather", "french-leather-eau-de-parfum",
        ["french leather", "rose suede", "paris atelier"], []),
    ("MP-IRISH-LEATHER", "Irish Leather", "irish-leather-eau-de-parfum",
        ["irish countryside", "juniper berries", "irish forest"], []),
    ("MP-RUSSIAN-LEATHER", "Russian Leather", "russian-leather-eau-de-parfum",
        ["russian forest snow", "northern wood", "siberian taiga"],
        ["russian-leather"]),
    ("MP-IBERIANLEATHER", "Iberian Leather", "iberian-leather-eau-de-parfum",
        ["spanish leather", "iberian peninsula", "spanish horse"], []),
    ("MP-OCEAN-LEATHER", "Ocean Leather", "ocean-leather-eau-de-parfum",
        ["ocean waves", "salt spray", "sea spray dark"], []),
    ("MP-INDIAN-LEATHER", "Indian Leather", "indian-leather-eau-de-parfum",
        ["india spice", "leather craft", "saffron threads"], []),
    ("MP-ORIENTAL-LEATHER", "Oriental Leather", "oriental-leather-eau-de-parfum",
        ["oriental textile", "asian leather", "silk road"], []),
    ("MP-MOROCCAN-LEATHER", "Moroccan Leather", "moroccan-leather-eau-de-parfum",
        ["moroccan tannery", "marrakech", "morocco souk"], []),
    ("MP-SICILIAN-LEATHER", "Sicilian Leather", "sicilian-leather-eau-de-parfum",
        ["sicily landscape", "sicilian cypress", "italian sun"], []),
    ("MP-INLE", "Inle", "inle-eau-de-parfum",
        ["inle lake myanmar", "floating gardens", "burma sunset"], []),
]


def is_brand_asset(url: str) -> bool:
    bad = ['/m-memoparis', '/memoparislogo', '/octogon', '/octagon',
           '/memo-box', '/logo-', '/placeholder']
    return any(kw in url.lower() for kw in bad)


def fetch_memo_bottles(handle: str, alts: List[str]) -> List[str]:
    handles = [handle] + alts
    for h in handles:
        url = f"https://www.memoparis.com/products/{h}"
        try:
            resp = requests.get(url, headers={'User-Agent': HEADERS['User-Agent']}, timeout=30)
            if resp.status_code != 200:
                continue
            
            html = resp.text
            patterns = [
                r'https://www\.memoparis\.com/cdn/shop/files/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
                r'//www\.memoparis\.com/cdn/shop/files/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
            ]
            
            all_matches = []
            for p in patterns:
                all_matches.extend(re.findall(p, html))
            
            unique = []
            seen = set()
            for img in all_matches:
                full = 'https:' + img if img.startswith('//') else img
                clean = re.sub(r'(\?|&)v=\d+', '', full).rstrip('?&')
                if clean not in seen and not is_brand_asset(clean):
                    seen.add(clean)
                    unique.append(clean)
            
            return unique[:2]
        except Exception:
            continue
    return []


def fetch_pexels(keywords: List[str], count: int = 3) -> List[str]:
    """Pexels — URL에 .jpeg 명시되어 워드프레스 호환"""
    images = []
    for keyword in keywords[:count]:
        try:
            resp = requests.get(
                'https://api.pexels.com/v1/search',
                params={
                    'query': keyword,
                    'per_page': 1,
                    'orientation': 'portrait',
                },
                headers={'Authorization': PEXELS_KEY},
                timeout=15
            )
            
            if resp.status_code == 200:
                data = resp.json()
                photos = data.get('photos', [])
                if photos:
                    # large = 약 1280px (좋은 퀄리티)
                    img_url = photos[0].get('src', {}).get('large', '')
                    if img_url:
                        images.append(img_url)
            
            time.sleep(1)
        except Exception as e:
            print(f"    Pexels error: {e}")
    
    return images


def find_product_by_sku(sku: str) -> Optional[Dict]:
    variations = [sku, sku.replace('×', 'X'), sku.replace('-X-', '-x-')]
    for var in variations:
        try:
            resp = session.get(
                f"{WC_URL}/wp-json/wc/v3/products",
                params={'sku': var},
                timeout=30
            )
            if resp.status_code == 200:
                results = resp.json()
                if results:
                    return results[0]
        except Exception:
            continue
    return None


def update_images(product_id: int, image_urls: List[str]) -> bool:
    if not image_urls:
        return False
    images = [{'src': url, 'position': i} for i, url in enumerate(image_urls)]
    try:
        resp = session.put(
            f"{WC_URL}/wp-json/wc/v3/products/{product_id}",
            json={'images': images},
            timeout=180
        )
        if resp.status_code in (200, 201):
            return True
        else:
            print(f"    [debug] Status: {resp.status_code}")
            print(f"    [debug] {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"    Update error: {e}")
        return False


def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'},
            timeout=10
        )
    except Exception:
        pass


def main():
    print("=" * 70)
    print("🚀 KOHGANE v5.2 (Pexels Only)")
    print("=" * 70)
    print(f"Strategy: Memo bottle 2장 + Pexels 3장 (Unsplash 제외)")
    print(f"Failed retry: {len(FAILED_PRODUCTS)}\n")
    
    # Pre-flight
    try:
        resp = session.get(f"{WC_URL}/wp-json/wc/v3/products", params={'per_page': 1}, timeout=15)
        if resp.status_code != 200:
            print(f"❌ WC API: {resp.status_code}")
            return
        print(f"✅ WC API OK\n")
    except Exception as e:
        print(f"❌ {e}")
        return
    
    success = []
    failed = []
    
    for i, item in enumerate(FAILED_PRODUCTS, 1):
        sku, name, handle, keywords, alts = item
        print(f"[{i}/{len(FAILED_PRODUCTS)}] {name}")
        
        bottles = fetch_memo_bottles(handle, alts)
        print(f"  📦 Bottles: {len(bottles)}")
        
        atmosphere = fetch_pexels(keywords, count=3)
        print(f"  🎨 Pexels: {len(atmosphere)}")
        
        all_images = bottles + atmosphere
        
        if not all_images:
            print(f"  ❌ No images")
            failed.append({'sku': sku, 'reason': 'no images'})
            continue
        
        product = find_product_by_sku(sku)
        if not product:
            print(f"  ⚠️ SKU not found")
            failed.append({'sku': sku, 'reason': 'no SKU'})
            time.sleep(3)
            continue
        
        if update_images(product['id'], all_images):
            print(f"  ✅ Updated #{product['id']}: {len(all_images)} images")
            success.append({'sku': sku, 'count': len(all_images)})
        else:
            print(f"  ❌ Update failed")
            failed.append({'sku': sku, 'reason': 'update failed'})
        
        time.sleep(3)
    
    print("\n" + "=" * 70)
    print(f"✅ Success: {len(success)}/{len(FAILED_PRODUCTS)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"📦 Total: {sum(s['count'] for s in success)} images")
    
    if failed:
        print("\nStill failed:")
        for f in failed:
            print(f"  - {f['sku']}: {f['reason']}")
    
    summary = f"""🤖 *KOHGANE v5.2 (Pexels Only)*

✅ 성공: {len(success)}/{len(FAILED_PRODUCTS)}
❌ 실패: {len(failed)}
📦 {sum(s['count'] for s in success)}장 업로드"""
    
    send_telegram(summary)


if __name__ == '__main__':
    main()
