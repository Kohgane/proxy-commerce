"""
KOHGANE - Memo Paris Image Collector v3
==========================================
주요 개선:
- 진짜 상품 이미지만 필터 (로고/박스 제외)
- 404 핸들 자동 fallback (대안 핸들 시도)
- SKU 매칭 변형 (×, X 등 자동 시도)
"""

import os
import re
import time
import requests
from typing import List, Dict, Optional

WC_URL = os.environ.get('WC_URL', '').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

if not WC_KEY or not WC_SECRET:
    print("❌ WC_KEY and WC_SECRET required")
    exit(1)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
    'Connection': 'keep-alive',
}

session = requests.Session()
session.headers.update(HEADERS)
session.auth = (WC_KEY, WC_SECRET)


# ============================================================
# 50개 매핑 (404 항목은 alt_handles로 fallback)
# ============================================================
MEMO_PRODUCTS = [
    # (SKU, Name, primary_handle, [alt_handles])
    ("MP-EAU-DE-MEMO", "Eau de Memo", "eau-de-memo-eau-de-parfum", []),
    ("MP-ODEON", "Odeon", "odeon-eau-de-parfum", []),
    ("MP-ODEON-ROSEBUD", "Odeon Rosebud", "odeon-rosebud-eau-de-parfum", []),
    ("MP-ODON-X-JEAN-JULLIEN", "Odon X Jean Jullien", "odeon-eau-de-parfum-jean-jullien", []),
    ("MP-RED-ISLAND", "Red Island", "red-island-eau-de-parfum", []),
    ("MP-CAP-CAMARAT", "Cap Camarat", "cap-camarat-eau-de-parfum", []),
    ("MP-ZANTE", "Zante", "zante-eau-de-parfum", []),
    ("MP-PORTOBELLO-ROAD", "Portobello Road", "portobello-road-eau-de-parfum", []),
    ("MP-JANNAT", "Jannat", "jannat-eau-de-parfum", []),
    ("MP-INDIAN-LEATHER", "Indian Leather", "indian-leather-eau-de-parfum", []),
    ("MP-ORIENTAL-LEATHER", "Oriental Leather", "oriental-leather-eau-de-parfum", []),
    ("MP-MOROCCAN-LEATHER", "Moroccan Leather", "moroccan-leather-eau-de-parfum", []),
    ("MP-LUXOR-OUD", "Luxor Oud", "luxor-oud-eau-de-parfum", []),
    ("MP-AFRICAN-ROSE", "African Rose", "african-rose-eau-de-parfum", []),
    ("MP-GRANADA", "Granada", "granada-eau-de-parfum", []),
    ("MP-KOTOR", "Kotor", "kotor-eau-de-parfum", []),
    ("MP-CORFU", "Corfu", "corfu-eau-de-parfum", []),
    ("MP-HONEY-DRAGON", "Honey Dragon", "honey-dragon-eau-de-parfum", []),
    ("MP-MOON-FEVER", "Moon Fever", "moon-fever-eau-de-parfum", []),
    ("MP-CAPPADOCIA", "Cappadocia", "cappadocia-eau-de-parfum", []),
    ("MP-TAMARINDO", "Tamarindo", "tamarindo-eau-de-parfum", []),
    # Russian Leather - try multiple handles
    ("MP-RUSSIAN-LEATHER", "Russian Leather", "russian-leather-eau-de-parfum", 
        ["russian-leather", "russian-leather-edp", "russianleather-eau-de-parfum"]),
    ("MP-SHAMS-OUD", "Shams Oud", "shams-oud-eau-de-parfum", []),
    ("MP-KEDU", "Kedu", "kedu-eau-de-parfum", []),
    ("MP-SICILIAN-LEATHER", "Sicilian Leather", "sicilian-leather-eau-de-parfum", []),
    ("MP-SHERWOOD", "Sherwood", "sherwood-eau-de-parfum", []),
    ("MP-ILHA-DO-MEL", "Ilha Do Mel", "ilha-do-mel-eau-de-parfum", []),
    ("MP-ARGENTINA", "Argentina", "argentina-eau-de-parfum", []),
    ("MP-INVERNESS", "Inverness", "inverness-eau-de-parfum", []),
    ("MP-OCEAN-LEATHER", "Ocean Leather", "ocean-leather-eau-de-parfum", []),
    ("MP-QUARTIERLATIN", "Quartier Latin", "quartier-latin-eau-de-parfum", []),
    ("MP-WINTER-PALACE", "Winter Palace", "winter-palace-eau-de-parfum", []),
    ("MP-FLAM", "Flam", "flam-eau-de-parfum", []),
    ("MP-IBERIANLEATHER", "Iberian Leather", "iberian-leather-eau-de-parfum", []),
    ("MP-ITALIAN-LEATHER", "Italian Leather", "italian-leather-eau-de-parfum", []),
    ("MP-LALIBELA", "Lalibela", "lalibela-eau-de-parfum", []),
    ("MP-INLE", "Inle", "inle-eau-de-parfum", []),
    ("MP-ITHAQUE", "Ithaque", "ithaque-eau-de-parfum", []),
    ("MP-SINTRA", "Sintra", "sintra-eau-de-parfum", []),
    ("MP-FRENCH-LEATHER", "French Leather", "french-leather-eau-de-parfum", []),
    ("MP-IRISH-LEATHER", "Irish Leather", "irish-leather-eau-de-parfum", []),
    ("MP-MADURAI", "Madurai", "madurai-eau-de-parfum", []),
    ("MP-MARFA", "Marfa", "marfa-eau-de-parfum", []),
    # Cap Camarat × Olimpia - try variations
    ("MP-CAP-CAMARAT-X-OLIMPIA", "Cap Camarat × Olimpia Zagnoli", "cap-camarat-eau-de-parfum-olimpia-zagnoli",
        ["cap-camarat-x-olimpia-zagnoli", "cap-camarat-olimpia", "olimpia-zagnoli"]),
    ("MP-CASSIOPEIAROSE", "Cassiopeia Rose", "cassiopeia-rose-eau-de-parfum", []),
    ("MP-PALAIS-BOURBON", "Palais Bourbon", "palais-bourbon-eau-de-parfum", []),
    ("MP-ABU-DHABI", "Abu Dhabi", "abu-dhabi-eau-de-parfum", []),
    ("MP-AFRICAN-LEATHER", "African Leather", "african-leather-eau-de-parfum", []),
    # Tigers Nest - try variations
    ("MP-TIGERS-NEST", "Tigers Nest", "tigers-nest-eau-de-parfum",
        ["tiger-s-nest-eau-de-parfum", "tigers-nest", "tiger-nest-eau-de-parfum"]),
    ("MP-MENORCA", "Menorca", "menorca-eau-de-parfum", []),
]


# ============================================================
# 진짜 상품 이미지만 필터링
# ============================================================
def is_real_product_image(url: str, handle: str) -> bool:
    """
    상품 이미지 vs 브랜드 자산 구분.
    
    - 진짜 상품: URL에 핸들 이름 또는 'eau-de-parfum' 포함
    - 브랜드 자산: 'memo', 'logo', 'box', 'octogon' 등
    """
    url_lower = url.lower()
    
    # 핸들 이름의 핵심 단어 추출 (예: 'african-rose-eau-de-parfum' → 'african-rose')
    handle_core = handle.replace('-eau-de-parfum', '').replace('-edp', '').replace('eau-de-parfum-', '')
    
    # 브랜드 자산 (제외)
    bad_keywords = [
        'logo', 'mlogo', 'm-memo', 'memoparis', 'memo-paris',
        'octogon', 'octagon', 'memo-box', 'box-', '-box',
        'placeholder', 'default'
    ]
    if any(bad in url_lower for bad in bad_keywords):
        return False
    
    # 진짜 상품 (포함)
    # 1) URL에 핸들 핵심이 들어있으면 진짜
    if handle_core in url_lower:
        return True
    
    # 2) 'eau-de-parfum-75ml' 패턴이면 진짜
    if 'eau-de-parfum' in url_lower or 'edp' in url_lower:
        return True
    
    # 3) 75ml 또는 30ml/200ml 사이즈 명시
    if any(size in url_lower for size in ['75ml', '200ml', '30ml']):
        return True
    
    # 모호한 건 제외
    return False


def fetch_product_images(handle: str) -> List[str]:
    url = f"https://www.memoparis.com/products/{handle}"
    
    try:
        resp = requests.get(url, headers={'User-Agent': HEADERS['User-Agent']}, timeout=30)
        if resp.status_code != 200:
            return []
        
        html = resp.text
        
        patterns = [
            r'https://www\.memoparis\.com/cdn/shop/files/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
            r'//www\.memoparis\.com/cdn/shop/files/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
            r'https://www\.memoparis\.com/cdn/shop/products/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
        ]
        
        all_matches = []
        for pattern in patterns:
            all_matches.extend(re.findall(pattern, html))
        
        # 정규화
        unique = []
        seen = set()
        for img in all_matches:
            full_url = 'https:' + img if img.startswith('//') else img
            clean_url = re.sub(r'(\?|&)v=\d+', '', full_url)
            clean_url = re.sub(r'(\?|&)width=\d+', '', clean_url)
            if clean_url not in seen:
                seen.add(clean_url)
                unique.append(clean_url)
        
        # ⭐ 진짜 상품 이미지만 필터
        product_images = [img for img in unique if is_real_product_image(img, handle)]
        
        # 최대 4장 (퀄리티 우선)
        return product_images[:4]
    
    except Exception as e:
        print(f"  [debug] Fetch error: {e}")
        return []


def fetch_with_fallback(primary: str, alts: List[str]) -> tuple:
    """주 핸들 시도 → 실패 시 대안 핸들들 시도"""
    images = fetch_product_images(primary)
    if images:
        return primary, images
    
    for alt in alts:
        print(f"    → trying alt handle: {alt}")
        images = fetch_product_images(alt)
        if images:
            return alt, images
    
    return None, []


# ============================================================
# WooCommerce API
# ============================================================
def find_product_by_sku(sku: str) -> Optional[Dict]:
    """SKU로 검색 + 변형 시도"""
    # 1. 원본 SKU
    variations = [sku]
    
    # 2. × → X 변형 (둘 다 시도)
    if '×' in sku:
        variations.append(sku.replace('×', 'X'))
        variations.append(sku.replace('×', '-X-'))
    if '-X-' in sku:
        variations.append(sku.replace('-X-', '-x-'))
    
    for var_sku in variations:
        try:
            resp = session.get(
                f"{WC_URL}/wp-json/wc/v3/products",
                params={'sku': var_sku},
                timeout=30
            )
            if resp.status_code == 200:
                results = resp.json()
                if results:
                    return results[0]
        except Exception:
            continue
    
    return None


def update_product_images(product_id: int, image_urls: List[str]) -> bool:
    if not image_urls:
        return False
    
    images = [{'src': url, 'position': i} for i, url in enumerate(image_urls)]
    
    try:
        resp = session.put(
            f"{WC_URL}/wp-json/wc/v3/products/{product_id}",
            json={'images': images},
            timeout=120
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"    [debug] Update error: {e}")
        return False


# ============================================================
# 메인
# ============================================================
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
    print("🚀 KOHGANE Memo Paris Image Collector v3")
    print("=" * 70)
    print(f"Target: {WC_URL}")
    print(f"Products: {len(MEMO_PRODUCTS)}")
    print()
    
    # Pre-flight
    print("Pre-flight...")
    try:
        resp = session.get(f"{WC_URL}/wp-json/wc/v3/products", params={'per_page': 1}, timeout=15)
        if resp.status_code != 200:
            print(f"  ❌ API status: {resp.status_code}")
            return
        print(f"  ✅ API OK\n")
    except Exception as e:
        print(f"  ❌ {e}")
        return
    
    success = []
    failed_no_image = []
    failed_no_product = []
    
    for i, (sku, name, handle, alts) in enumerate(MEMO_PRODUCTS, 1):
        print(f"[{i}/{len(MEMO_PRODUCTS)}] {name} ({sku})")
        
        # 1. 이미지 수집 (fallback 포함)
        used_handle, images = fetch_with_fallback(handle, alts)
        
        if not images:
            print(f"  ⚠️ No product images found")
            failed_no_image.append({'sku': sku, 'name': name})
            time.sleep(1)
            continue
        
        if used_handle != handle:
            print(f"  📌 Used alt handle: {used_handle}")
        print(f"  ✅ Found {len(images)} REAL product images")
        
        # 2. WC 상품 찾기 (변형 시도)
        product = find_product_by_sku(sku)
        if not product:
            print(f"  ⚠️ SKU not found in WC: {sku}")
            failed_no_product.append({'sku': sku, 'name': name, 'images': images})
            time.sleep(1)
            continue
        
        # 3. 업데이트
        if update_product_images(product['id'], images):
            print(f"  ✅ Updated #{product['id']}: {len(images)} images")
            success.append({'sku': sku, 'name': name, 'count': len(images)})
        else:
            print(f"  ❌ Update failed")
        
        time.sleep(2)
    
    # 결과
    print("\n" + "=" * 70)
    print("📊 RESULTS v3")
    print("=" * 70)
    print(f"✅ Success: {len(success)}")
    print(f"⚠️ No image source: {len(failed_no_image)}")
    print(f"⚠️ Not found in WC: {len(failed_no_product)}")
    print(f"📦 Total images: {sum(s['count'] for s in success)}")
    
    if failed_no_product:
        print(f"\nNot found in WC:")
        for f in failed_no_product:
            print(f"  - {f['name']} ({f['sku']})")
    
    if failed_no_image:
        print(f"\nNo source images:")
        for f in failed_no_image:
            print(f"  - {f['name']}")
    
    summary = f"""🤖 *KOHGANE v3 Final*

✅ 성공: {len(success)}개
⚠️ 소스 없음: {len(failed_no_image)}개
⚠️ WC 매칭 실패: {len(failed_no_product)}개

📦 진짜 상품 이미지 {sum(s['count'] for s in success)}장 업로드
🎯 평균 {sum(s['count'] for s in success) / max(len(success), 1):.1f}장/상품"""
    
    send_telegram(summary)


if __name__ == '__main__':
    main()
