"""
KOHGANE - Memo Paris Image Collector v4 FINAL
================================================
v3에서는 '향수병 사진만' 4장씩 가져왔는데
v4는 '페이지의 모든 진짜 이미지' 가져옴:
  - 향수병 (다른 각도)
  - 분위기 사진 (호수, 도시, 자연)
  - 재료 사진 (자스민, 가죽 등)
  - 조향사 인터뷰 사진
  - 컬렉션 라인업

- /cdn/shop/files/* 모든 이미지 (브랜드 자산만 제외)
- 주제별로 가능한 다양한 각도/콘텐츠
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
}

session = requests.Session()
session.headers.update(HEADERS)
session.auth = (WC_KEY, WC_SECRET)


# ============================================================
# 50개 매핑 (v3와 동일)
# ============================================================
MEMO_PRODUCTS = [
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
    ("MP-RUSSIAN-LEATHER", "Russian Leather", "russian-leather-eau-de-parfum", 
        ["russian-leather"]),
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
    ("MP-CAP-CAMARAT-X-OLIMPIA", "Cap Camarat × Olimpia Zagnoli", "cap-camarat-eau-de-parfum-olimpia-zagnoli",
        ["cap-camarat-x-olimpia-zagnoli"]),
    ("MP-CASSIOPEIAROSE", "Cassiopeia Rose", "cassiopeia-rose-eau-de-parfum", []),
    ("MP-PALAIS-BOURBON", "Palais Bourbon", "palais-bourbon-eau-de-parfum", []),
    ("MP-ABU-DHABI", "Abu Dhabi", "abu-dhabi-eau-de-parfum", []),
    ("MP-AFRICAN-LEATHER", "African Leather", "african-leather-eau-de-parfum", []),
    ("MP-TIGERS-NEST", "Tigers Nest", "tigers-nest-eau-de-parfum",
        ["tiger-s-nest-eau-de-parfum"]),
    ("MP-MENORCA", "Menorca", "menorca-eau-de-parfum", []),
]


# ============================================================
# 진짜 컨텐츠 이미지만 필터 (확장된 패턴)
# ============================================================
def is_brand_asset(url: str) -> bool:
    """브랜드 자산(로고/박스)인지 판별 → True면 제외"""
    url_lower = url.lower()
    
    # 명백한 브랜드 자산
    brand_keywords = [
        '/m-memoparis', '/memoparislogo', '/memoparis_logo', '/memo_paris_logo',
        '/octogon', '/octagon',
        '/memo-box', '/memo_box', 'box-memo',
        '/logo-', '/logo_', 'mlogo',
        '/placeholder', '/default-product',
        '/social-icon', '/instagram-icon',
        '/payment-', '/pay-method',
        '/footer-', '/header-',
    ]
    
    return any(kw in url_lower for kw in brand_keywords)


def fetch_all_product_images(handle: str) -> List[str]:
    """페이지의 모든 진짜 이미지 추출 (분위기/재료/조향사 포함)"""
    url = f"https://www.memoparis.com/products/{handle}"
    
    try:
        resp = requests.get(
            url,
            headers={'User-Agent': HEADERS['User-Agent']},
            timeout=30
        )
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code}")
            return []
        
        html = resp.text
        
        # 모든 Memo Paris CDN 이미지 찾기
        patterns = [
            r'https://www\.memoparis\.com/cdn/shop/files/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
            r'//www\.memoparis\.com/cdn/shop/files/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
            r'https://www\.memoparis\.com/cdn/shop/products/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
            r'//www\.memoparis\.com/cdn/shop/products/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
        ]
        
        all_matches = []
        for pattern in patterns:
            all_matches.extend(re.findall(pattern, html))
        
        # 정규화
        unique = []
        seen = set()
        for img in all_matches:
            full_url = 'https:' + img if img.startswith('//') else img
            # 사이즈 파라미터 제거 (원본 받기)
            clean_url = re.sub(r'(\?|&)v=\d+', '', full_url)
            clean_url = re.sub(r'(\?|&)width=\d+', '', clean_url)
            
            # URL 끝 정리
            clean_url = clean_url.rstrip('?&')
            
            if clean_url not in seen:
                seen.add(clean_url)
                unique.append(clean_url)
        
        # 브랜드 자산만 제외
        content_images = [img for img in unique if not is_brand_asset(img)]
        
        # 너무 많으면 6장만 (퀄리티 우선)
        # 향수병 1~2장 + 분위기/재료 4장 정도로 다양성
        return content_images[:6]
    
    except Exception as e:
        print(f"    Error: {e}")
        return []


def fetch_with_fallback(primary: str, alts: List[str]) -> tuple:
    images = fetch_all_product_images(primary)
    if images:
        return primary, images
    for alt in alts:
        print(f"    → trying alt: {alt}")
        images = fetch_all_product_images(alt)
        if images:
            return alt, images
    return None, []


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
            timeout=120
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
    print("🚀 KOHGANE Memo Paris Image Collector v4 (Full Content)")
    print("=" * 70)
    print(f"Target: {WC_URL}")
    print(f"Strategy: 페이지의 모든 진짜 이미지 (브랜드 자산만 제외)")
    print(f"Products: {len(MEMO_PRODUCTS)}\n")
    
    # Pre-flight
    try:
        resp = session.get(f"{WC_URL}/wp-json/wc/v3/products", params={'per_page': 1}, timeout=15)
        if resp.status_code != 200:
            print(f"❌ API status: {resp.status_code}")
            return
        print(f"✅ API OK\n")
    except Exception as e:
        print(f"❌ {e}")
        return
    
    success = []
    failed_no_image = []
    failed_no_product = []
    
    for i, (sku, name, handle, alts) in enumerate(MEMO_PRODUCTS, 1):
        print(f"[{i}/{len(MEMO_PRODUCTS)}] {name}")
        
        used_handle, images = fetch_with_fallback(handle, alts)
        
        if not images:
            print(f"  ⚠️ No images")
            failed_no_image.append({'sku': sku, 'name': name})
            time.sleep(1)
            continue
        
        if used_handle != handle:
            print(f"  📌 Used alt: {used_handle}")
        print(f"  ✅ Found {len(images)} images")
        
        product = find_product_by_sku(sku)
        if not product:
            print(f"  ⚠️ SKU not in WC")
            failed_no_product.append({'sku': sku, 'name': name})
            time.sleep(1)
            continue
        
        if update_images(product['id'], images):
            print(f"  ✅ Updated #{product['id']}: {len(images)} images")
            success.append({'sku': sku, 'name': name, 'count': len(images)})
        else:
            print(f"  ❌ Update failed")
        
        time.sleep(2)
    
    # 결과
    print("\n" + "=" * 70)
    print("📊 RESULTS v4")
    print("=" * 70)
    print(f"✅ Success: {len(success)}")
    print(f"⚠️ No images: {len(failed_no_image)}")
    print(f"⚠️ No SKU: {len(failed_no_product)}")
    print(f"📦 Total: {sum(s['count'] for s in success)} images")
    
    if failed_no_image:
        print(f"\nNo images found for:")
        for f in failed_no_image:
            print(f"  - {f['name']}")
    
    if failed_no_product:
        print(f"\nNo SKU match:")
        for f in failed_no_product:
            print(f"  - {f['name']}")
    
    summary = f"""🤖 *KOHGANE v4 — Full Content*

✅ 성공: {len(success)}개
⚠️ 이미지 없음: {len(failed_no_image)}개
⚠️ SKU 매칭 X: {len(failed_no_product)}개

📦 총 {sum(s['count'] for s in success)}장 (분위기+재료+향수병)
🎯 평균 {sum(s['count'] for s in success) / max(len(success), 1):.1f}장/상품"""
    
    send_telegram(summary)


if __name__ == '__main__':
    main()
