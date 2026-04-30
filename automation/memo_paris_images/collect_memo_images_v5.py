"""
KOHGANE - Memo Paris Image Collector v5
============================================
하이브리드 전략:
  - 향수병 2장: 메모파리 공식 (v4 결과 활용)
  - 분위기 3장: Unsplash 자동 검색 (향 노트 + 장소 기반)

각 메모파리 향수마다 큐레이션된 분위기 사진 자동 매칭.
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
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

if not WC_KEY or not WC_SECRET:
    print("❌ WC_KEY and WC_SECRET required")
    exit(1)

if not UNSPLASH_KEY and not PEXELS_KEY:
    print("⚠️ No Unsplash or Pexels API key. Using only Memo Paris bottle images.")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
}

session = requests.Session()
session.headers.update(HEADERS)
session.auth = (WC_KEY, WC_SECRET)


# ============================================================
# 50개 매핑 + 큐레이션 검색어
# ============================================================
# Format: (sku, name, memo_handle, search_keywords[], alt_handles[])
# search_keywords: Unsplash에서 검색할 분위기 키워드들

MEMO_PRODUCTS = [
    # === Iconics ===
    ("MP-EAU-DE-MEMO", "Eau de Memo", "eau-de-memo-eau-de-parfum",
        ["birds flying sky", "freedom travel", "vintage memo book"], []),
    
    # === Odéon Collection (Paris) ===
    ("MP-ODEON", "Odeon", "odeon-eau-de-parfum",
        ["paris rooftops night", "patchouli", "rose garden paris"], []),
    ("MP-ODEON-ROSEBUD", "Odeon Rosebud", "odeon-rosebud-eau-de-parfum",
        ["pink rose petals", "paris romantic", "soft rose"], []),
    ("MP-ODON-X-JEAN-JULLIEN", "Odon X Jean Jullien", "odeon-eau-de-parfum-jean-jullien",
        ["clouds sky abstract", "paris sunset clouds", "modern art clouds"], []),
    ("MP-QUARTIERLATIN", "Quartier Latin", "quartier-latin-eau-de-parfum",
        ["paris bookshop vintage", "latin quarter cafe", "old books library"], []),
    
    # === Cuirs Nomades (Leather Series) ===
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
    
    # === Graines Vagabondes (Wandering Seeds) ===
    ("MP-INLE", "Inle", "inle-eau-de-parfum",
        ["myanmar inle lake", "floating gardens water", "burma sunset"], []),
    ("MP-KEDU", "Kedu", "kedu-eau-de-parfum",
        ["indonesia temple", "borobudur sunrise", "java tropical"], []),
    ("MP-TAMARINDO", "Tamarindo", "tamarindo-eau-de-parfum",
        ["costa rica tropical", "tamarind tree", "tropical fruit"], []),
    ("MP-ILHA-DO-MEL", "Ilha Do Mel", "ilha-do-mel-eau-de-parfum",
        ["brazil tropical island", "honey island brazil", "tropical paradise"], []),
    ("MP-FLAM", "Flam", "flam-eau-de-parfum",
        ["solar flame", "warm sun rays", "fire light"], []),
    ("MP-JANNAT", "Jannat", "jannat-eau-de-parfum",
        ["paradise garden", "heaven clouds", "ethereal flowers"], []),
    ("MP-SHAMS-OUD", "Shams Oud", "shams-oud-eau-de-parfum",
        ["arabian desert sun", "oud wood", "middle east golden"], []),
    ("MP-SHERWOOD", "Sherwood", "sherwood-eau-de-parfum",
        ["sherwood forest", "english oak", "robin hood forest"], []),
    ("MP-LALIBELA", "Lalibela", "lalibela-eau-de-parfum",
        ["ethiopia rock church", "lalibela stone", "ethiopian highlands"], []),
    ("MP-MARFA", "Marfa", "marfa-eau-de-parfum",
        ["marfa texas desert", "texas sunset", "desert minimalist"], []),
    ("MP-MADURAI", "Madurai", "madurai-eau-de-parfum",
        ["jasmine india flower", "indian temple", "sandalwood"], []),
    ("MP-ARGENTINA", "Argentina", "argentina-eau-de-parfum",
        ["argentina tango", "patagonia landscape", "buenos aires"], []),
    ("MP-INVERNESS", "Inverness", "inverness-eau-de-parfum",
        ["scottish highlands", "inverness castle", "scotland mist"], []),
    ("MP-ITHAQUE", "Ithaque", "ithaque-eau-de-parfum",
        ["greek island ithaca", "mediterranean blue", "olive tree greece"], []),
    ("MP-SINTRA", "Sintra", "sintra-eau-de-parfum",
        ["sintra portugal palace", "portuguese garden", "portugal tile"], []),
    
    # === Fleurs Bohèmes / Escales ===
    ("MP-CASSIOPEIAROSE", "Cassiopeia Rose", "cassiopeia-rose-eau-de-parfum",
        ["starry night rose", "cosmos flower", "purple rose dark"], []),
    ("MP-AFRICAN-ROSE", "African Rose", "african-rose-eau-de-parfum",
        ["african rose desert", "red rose sand", "sahara rose"], []),
    
    # === Escales Extraordinaires (Travel) ===
    ("MP-CAP-CAMARAT", "Cap Camarat", "cap-camarat-eau-de-parfum",
        ["french riviera coast", "saint tropez sea", "mediterranean villa"], []),
    ("MP-CAP-CAMARAT-X-OLIMPIA", "Cap Camarat × Olimpia Zagnoli", "cap-camarat-eau-de-parfum-olimpia-zagnoli",
        ["pop art beach", "modern illustration mediterranean", "stylized riviera"],
        ["cap-camarat-x-olimpia-zagnoli"]),
    ("MP-MENORCA", "Menorca", "menorca-eau-de-parfum",
        ["menorca island balearic", "salt flats sea", "mediterranean white"], []),
    ("MP-ZANTE", "Zante", "zante-eau-de-parfum",
        ["zakynthos beach blue", "greek shipwreck", "greek island white"], []),
    ("MP-CORFU", "Corfu", "corfu-eau-de-parfum",
        ["corfu island", "greek olive grove", "ionian sea"], []),
    ("MP-KOTOR", "Kotor", "kotor-eau-de-parfum",
        ["kotor montenegro fjord", "balkan mountains", "adriatic bay"], []),
    ("MP-GRANADA", "Granada", "granada-eau-de-parfum",
        ["alhambra granada", "spanish moorish", "andalusia palace"], []),
    ("MP-CAPPADOCIA", "Cappadocia", "cappadocia-eau-de-parfum",
        ["cappadocia balloons", "turkey rock formations", "anatolia sunset"], []),
    ("MP-WINTER-PALACE", "Winter Palace", "winter-palace-eau-de-parfum",
        ["winter palace russia", "imperial palace snow", "russian winter"], []),
    ("MP-ABU-DHABI", "Abu Dhabi", "abu-dhabi-eau-de-parfum",
        ["abu dhabi mosque", "uae desert architecture", "arabian gold"], []),
    ("MP-PALAIS-BOURBON", "Palais Bourbon", "palais-bourbon-eau-de-parfum",
        ["paris assembly classical", "french palace marble", "paris architecture"], []),
    ("MP-RED-ISLAND", "Red Island", "red-island-eau-de-parfum",
        ["madagascar red soil", "tropical red earth", "exotic island"], []),
    ("MP-PORTOBELLO-ROAD", "Portobello Road", "portobello-road-eau-de-parfum",
        ["portobello london market", "notting hill", "vintage market"], []),
    ("MP-LUXOR-OUD", "Luxor Oud", "luxor-oud-eau-de-parfum",
        ["luxor egypt temple", "egyptian gold", "nile river"], []),
    ("MP-HONEY-DRAGON", "Honey Dragon", "honey-dragon-eau-de-parfum",
        ["chinese honey", "dragon golden", "asian tea ceremony"], []),
    ("MP-MOON-FEVER", "Moon Fever", "moon-fever-eau-de-parfum",
        ["moonlight night", "lunar mystical", "moon glow"], []),
    ("MP-TIGERS-NEST", "Tigers Nest", "tigers-nest-eau-de-parfum",
        ["bhutan tigers nest", "himalaya monastery", "bhutan mountain"],
        ["tiger-s-nest-eau-de-parfum"]),
]


# ============================================================
# Memo Paris 향수병 이미지 추출 (v4 로직)
# ============================================================
def is_brand_asset(url: str) -> bool:
    url_lower = url.lower()
    bad = ['/m-memoparis', '/memoparislogo', '/memoparis_logo', '/octogon', '/octagon',
           '/memo-box', '/memo_box', '/logo-', '/logo_', '/placeholder']
    return any(kw in url_lower for kw in bad)


def fetch_memo_bottle_images(handle: str, alts: List[str]) -> List[str]:
    """메모파리 사이트에서 향수병 사진만 추출 (2장)"""
    handles_to_try = [handle] + alts
    
    for h in handles_to_try:
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
            
            # 향수병 첫 2장만 (브랜드 자산 제외 후)
            return unique[:2]
        except Exception:
            continue
    
    return []


# ============================================================
# Unsplash 이미지 검색
# ============================================================
def fetch_unsplash_images(keywords: List[str], count: int = 3) -> List[str]:
    """각 키워드로 1장씩 가져옴"""
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
                    'content_filter': 'high',
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
                    # 1080px 사이즈 사용 (퀄리티 vs 용량 밸런스)
                    img_url = results[0].get('urls', {}).get('regular', '')
                    if img_url:
                        images.append(img_url)
            
            time.sleep(1)  # rate limit 보호
        except Exception as e:
            print(f"    Unsplash error '{keyword}': {e}")
    
    return images


def fetch_pexels_images(keywords: List[str], count: int = 3) -> List[str]:
    """Unsplash 백업: Pexels"""
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
                    img_url = photos[0].get('src', {}).get('large', '')
                    if img_url:
                        images.append(img_url)
            
            time.sleep(1)
        except Exception as e:
            print(f"    Pexels error '{keyword}': {e}")
    
    return images


# ============================================================
# WooCommerce
# ============================================================
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
            timeout=180  # 외부 이미지 다운로드 시간 더
        )
        return resp.status_code in (200, 201)
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


# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 70)
    print("🚀 KOHGANE Memo Paris Image Collector v5 (Hybrid)")
    print("=" * 70)
    print(f"Strategy: 향수병 2장 (메모파리) + 분위기 3장 (Unsplash)")
    print(f"Unsplash API: {'✅' if UNSPLASH_KEY else '❌'}")
    print(f"Pexels API: {'✅' if PEXELS_KEY else '❌'}")
    print(f"Products: {len(MEMO_PRODUCTS)}\n")
    
    # Pre-flight: WC API
    try:
        resp = session.get(f"{WC_URL}/wp-json/wc/v3/products", params={'per_page': 1}, timeout=15)
        if resp.status_code != 200:
            print(f"❌ WC API: {resp.status_code}")
            return
        print(f"✅ WC API OK")
    except Exception as e:
        print(f"❌ {e}")
        return
    
    # Pre-flight: Unsplash 또는 Pexels
    if UNSPLASH_KEY:
        try:
            resp = requests.get(
                'https://api.unsplash.com/photos/random',
                headers={'Authorization': f'Client-ID {UNSPLASH_KEY}'},
                timeout=10
            )
            if resp.status_code == 200:
                print(f"✅ Unsplash API OK")
            else:
                print(f"⚠️ Unsplash status: {resp.status_code}")
        except Exception as e:
            print(f"⚠️ Unsplash error: {e}")
    
    print()
    
    success = []
    failed = []
    
    for i, (sku, name, handle, keywords, alts) in enumerate(MEMO_PRODUCTS, 1):
        print(f"[{i}/{len(MEMO_PRODUCTS)}] {name}")
        
        # 1. 메모파리 향수병 (2장)
        bottle_images = fetch_memo_bottle_images(handle, alts)
        print(f"  📦 Bottle images: {len(bottle_images)}")
        
        # 2. Unsplash 분위기 (3장)
        atmosphere_images = []
        if UNSPLASH_KEY:
            atmosphere_images = fetch_unsplash_images(keywords, count=3)
            print(f"  🎨 Unsplash atmosphere: {len(atmosphere_images)}")
        
        # 3. Pexels 백업 (Unsplash 부족하면)
        if len(atmosphere_images) < 3 and PEXELS_KEY:
            needed = 3 - len(atmosphere_images)
            pexels_imgs = fetch_pexels_images(keywords, count=needed)
            atmosphere_images.extend(pexels_imgs)
            print(f"  🎨 + Pexels: {len(pexels_imgs)}")
        
        all_images = bottle_images + atmosphere_images
        
        if not all_images:
            print(f"  ❌ No images found")
            failed.append({'sku': sku, 'reason': 'no images'})
            time.sleep(1)
            continue
        
        # 4. WC 업데이트
        product = find_product_by_sku(sku)
        if not product:
            print(f"  ⚠️ SKU not in WC")
            failed.append({'sku': sku, 'reason': 'no SKU'})
            time.sleep(1)
            continue
        
        if update_images(product['id'], all_images):
            print(f"  ✅ Updated #{product['id']}: {len(all_images)} images "
                  f"(병 {len(bottle_images)} + 분위기 {len(atmosphere_images)})")
            success.append({
                'sku': sku, 'name': name,
                'bottle': len(bottle_images),
                'atmosphere': len(atmosphere_images),
                'total': len(all_images)
            })
        else:
            print(f"  ❌ Update failed")
            failed.append({'sku': sku, 'reason': 'update failed'})
        
        time.sleep(3)  # API rate limit 보호
    
    # 결과
    print("\n" + "=" * 70)
    print("📊 RESULTS v5")
    print("=" * 70)
    print(f"✅ Success: {len(success)}")
    print(f"❌ Failed: {len(failed)}")
    
    total_bottles = sum(s['bottle'] for s in success)
    total_atmos = sum(s['atmosphere'] for s in success)
    print(f"\n📦 Total images: {total_bottles + total_atmos}")
    print(f"   - 향수병 (메모파리): {total_bottles}")
    print(f"   - 분위기 (Unsplash/Pexels): {total_atmos}")
    
    summary = f"""🤖 *KOHGANE v5 Hybrid*

✅ 성공: {len(success)}개
❌ 실패: {len(failed)}개

📦 총 {total_bottles + total_atmos}장
  • 향수병: {total_bottles}장
  • 분위기: {total_atmos}장"""
    
    send_telegram(summary)


if __name__ == '__main__':
    main()
