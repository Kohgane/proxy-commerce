"""
KOHGANE - v5.1 RETRY for failed products
==========================================
v5에서 실패한 18개만 다시 처리.

수정 사항:
- Unsplash 사이즈 'small' (400px) 사용 → 다운로드 시간 줄임
- 호출 사이 sleep 2초 → rate limit 보호
- 실패한 상품 SKU만 처리
"""

import os
import re
import time
import requests
from typing import List, Dict, Optional

WC_URL = os.environ.get('WC_URL', '').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')
UNSPLASH_KEY = os.environ.get('UNSPLASH_ACCESS_KEY', '')
PEXELS_KEY = os.environ.get('PEXELS_API_KEY', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')  # ⭐ 이름 수정
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

if not WC_KEY or not WC_SECRET:
    print("❌ WC_KEY and WC_SECRET required")
    exit(1)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
}

session = requests.Session()
session.headers.update(HEADERS)
session.auth = (WC_KEY, WC_SECRET)


# ============================================================
# v5에서 실패한 18개만
# ============================================================
FAILED_PRODUCTS = [
    # (sku, name, memo_handle, search_keywords, alt_handles)
    ("MP-EAU-DE-MEMO", "Eau de Memo", "eau-de-memo-eau-de-parfum",
        ["birds flying sky", "freedom travel", "vintage memo book"], []),
    ("MP-ODEON", "Odeon", "odeon-eau-de-parfum",
        ["paris rooftops night", "patchouli", "rose garden paris"], []),
    ("MP-ODEON-ROSEBUD", "Odeon Rosebud", "odeon-rosebud-eau-de-parfum",
        ["pink rose petals", "paris romantic", "soft rose"], []),
    ("MP-ODON-X-JEAN-JULLIEN", "Odon X Jean Jullien", "odeon-eau-de-parfum-jean-jullien",
        ["clouds sky abstract", "paris sunset clouds", "modern art clouds"], []),
    ("MP-QUARTIERLATIN", "Quartier Latin", "quartier-latin-eau-de-parfum",
        ["paris bookshop vintage", "latin quarter cafe", "old books library"], []),
    ("MP-AFRICAN-LEATHER", "African Leather", "african-leather-eau-de-parfum",
        ["african savanna sunset", "leather texture", "saffron spice"], []),
    ("MP-ITALIAN-LEATHER", "Italian Leather", "italian-leather-eau-de-parfum",
        ["italian leather workshop", "tomato leaves", "italy countryside"], []),
    ("MP-FRENCH-LEATHER", "French Leather", "french-leather-eau-de-parfum",
        ["french leather artisan", "rose suede", "paris atelier"], []),
    ("MP-IRISH-LEATHER", "Irish Leather", "irish-leather-eau-de-parfum",
        ["irish countryside green", "juniper berries", "irish forest"], []),
    ("MP-RUSSIAN-LEATHER", "Russian Leather", "russian-leather-eau-de-parfum",
        ["russian forest snow", "northern wood", "siberian taiga"],
        ["russian-leather"]),
    ("MP-IBERIANLEATHER", "Iberian Leather", "iberian-leather-eau-de-parfum",
        ["spanish leather", "iberian peninsula", "spanish horse"], []),
    ("MP-OCEAN-LEATHER", "Ocean Leather", "ocean-leather-eau-de-parfum",
        ["ocean waves dark", "salt air leather", "sea spray"], []),
    ("MP-INDIAN-LEATHER", "Indian Leather", "indian-leather-eau-de-parfum",
        ["india spice market", "indian leather craft", "saffron threads"], []),
    ("MP-ORIENTAL-LEATHER", "Oriental Leather", "oriental-leather-eau-de-parfum",
        ["oriental textile", "asian leather", "silk road"], []),
    ("MP-MOROCCAN-LEATHER", "Moroccan Leather", "moroccan-leather-eau-de-parfum",
        ["moroccan tannery", "marrakech leather", "morocco souk"], []),
    ("MP-SICILIAN-LEATHER", "Sicilian Leather", "sicilian-leather-eau-de-parfum",
        ["sicily landscape", "sicilian cypress", "italian sun"], []),
    ("MP-INLE", "Inle", "inle-eau-de-parfum",
        ["myanmar inle lake", "floating gardens water", "burma sunset"], []),
    ("MP-CAP-CAMARAT-X-OLIMPIA", "Cap Camarat × Olimpia", "cap-camarat-eau-de-parfum-olimpia-zagnoli",
        ["pop art beach", "modern illustration mediterranean", "stylized riviera"],
        ["cap-camarat-x-olimpia-zagnoli"]),
]


def is_brand_asset(url: str) -> bool:
    bad = ['/m-memoparis', '/memoparislogo', '/octogon', '/octagon',
           '/memo-box', '/memo_box', '/logo-', '/placeholder']
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


def fetch_unsplash(keywords: List[str], count: int = 3) -> List[str]:
    """Unsplash - 작은 사이즈 사용"""
    if not UNSPLASH_KEY:
        return []
    
    images = []
    for keyword in keywords[:count]:
        try:
            resp = requests.get(
                'https://api.unsplash.com/search/photos',
                params={
                    'query': keyword,
                    'per_page': 1,
                    'orientation': 'portrait',
                },
                headers={
                    'Authorization': f'Client-ID {UNSPLASH_KEY}',
                    'Accept-Version': 'v1',
                },
                timeout=15
            )
            
            if resp.status_code == 200:
                data = resp.json()
                results = data.get('results', [])
                if results:
                    # 'small' = 400px (가벼움) / 'regular' = 1080px (무거움)
                    img_url = results[0].get('urls', {}).get('small', '')
                    if img_url:
                        images.append(img_url)
            elif resp.status_code == 403:
                print(f"    ⚠️ Unsplash rate limit hit")
                break
            
            time.sleep(2)  # rate limit 보호
        except Exception as e:
            print(f"    Unsplash error: {e}")
    
    return images


def fetch_pexels(keywords: List[str], count: int = 3) -> List[str]:
    if not PEXELS_KEY:
        return []
    
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
                    # Pexels: medium = 약 700px (가벼움)
                    img_url = photos[0].get('src', {}).get('medium', '')
                    if img_url:
                        images.append(img_url)
            
            time.sleep(2)
        except Exception as e:
            print(f"    Pexels error: {e}")
    
    return images


def find_product_by_sku(sku: str) -> Optional[Dict]:
    variations = [sku, sku.replace('×', 'X'), sku.replace('-X-', '-x-'), 
                  sku.replace('×', '-X-'), sku + '-ZAGNOLI']
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
            print(f"    [debug] Response: {resp.text[:200]}")
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
    print("🚀 KOHGANE v5.1 RETRY (failed products only)")
    print("=" * 70)
    print(f"Failed products to retry: {len(FAILED_PRODUCTS)}")
    print(f"Image size: small (400px Unsplash, 700px Pexels) - 가벼움")
    print()
    
    success = []
    failed = []
    
    for i, item in enumerate(FAILED_PRODUCTS, 1):
        sku, name, handle, keywords, alts = item
        print(f"[{i}/{len(FAILED_PRODUCTS)}] {name}")
        
        bottles = fetch_memo_bottles(handle, alts)
        print(f"  📦 Bottles: {len(bottles)}")
        
        atmosphere = fetch_unsplash(keywords, count=3)
        print(f"  🎨 Unsplash: {len(atmosphere)}")
        
        if len(atmosphere) < 3 and PEXELS_KEY:
            needed = 3 - len(atmosphere)
            pexels = fetch_pexels(keywords, count=needed)
            atmosphere.extend(pexels)
            print(f"  🎨 + Pexels: {len(pexels)}")
        
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
        
        time.sleep(5)  # 조금 길게 — 워드프레스 부담 줄이기
    
    print("\n" + "=" * 70)
    print(f"✅ Success: {len(success)}/{len(FAILED_PRODUCTS)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"📦 Total: {sum(s['count'] for s in success)} images")
    
    if failed:
        print("\nStill failed:")
        for f in failed:
            print(f"  - {f['sku']}: {f['reason']}")
    
    summary = f"""🤖 *KOHGANE v5.1 Retry*

✅ 성공: {len(success)}/{len(FAILED_PRODUCTS)}
❌ 실패: {len(failed)}
📦 {sum(s['count'] for s in success)}장 업로드"""
    
    send_telegram(summary)


if __name__ == '__main__':
    main()
