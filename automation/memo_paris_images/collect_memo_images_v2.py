"""
KOHGANE - Memo Paris Image Collector v2
==========================================
Bluehost Mod_Security 우회 + 견고한 인증
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

# ============================================================
# 브라우저 위장 헤더 (Bluehost Mod_Security 우회)
# ============================================================
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

# Session으로 재사용 (효율 + 일관성)
session = requests.Session()
session.headers.update(HEADERS)
session.auth = (WC_KEY, WC_SECRET)


# ============================================================
# 메모파리 50개 매핑 (404 핸들 수정 포함)
# ============================================================
MEMO_PRODUCTS = [
    ("MP-EAU-DE-MEMO", "Eau de Memo", "eau-de-memo-eau-de-parfum"),
    ("MP-ODEON", "Odeon", "odeon-eau-de-parfum"),
    ("MP-ODEON-ROSEBUD", "Odeon Rosebud", "odeon-rosebud-eau-de-parfum"),
    ("MP-ODON-X-JEAN-JULLIEN", "Odon X Jean Jullien", "odeon-eau-de-parfum-jean-jullien"),
    ("MP-RED-ISLAND", "Red Island", "red-island-eau-de-parfum"),
    ("MP-CAP-CAMARAT", "Cap Camarat", "cap-camarat-eau-de-parfum"),
    ("MP-ZANTE", "Zante", "zante-eau-de-parfum"),
    ("MP-PORTOBELLO-ROAD", "Portobello Road", "portobello-road-eau-de-parfum"),
    ("MP-JANNAT", "Jannat", "jannat-eau-de-parfum"),
    ("MP-INDIAN-LEATHER", "Indian Leather", "indian-leather-eau-de-parfum"),
    ("MP-ORIENTAL-LEATHER", "Oriental Leather", "oriental-leather-eau-de-parfum"),
    ("MP-MOROCCAN-LEATHER", "Moroccan Leather", "moroccan-leather-eau-de-parfum"),
    ("MP-LUXOR-OUD", "Luxor Oud", "luxor-oud-eau-de-parfum"),
    ("MP-AFRICAN-ROSE", "African Rose", "african-rose-eau-de-parfum"),
    ("MP-GRANADA", "Granada", "granada-eau-de-parfum"),
    ("MP-KOTOR", "Kotor", "kotor-eau-de-parfum"),
    ("MP-CORFU", "Corfu", "corfu-eau-de-parfum"),
    ("MP-HONEY-DRAGON", "Honey Dragon", "honey-dragon-eau-de-parfum"),
    ("MP-MOON-FEVER", "Moon Fever", "moon-fever-eau-de-parfum"),
    ("MP-CAPPADOCIA", "Cappadocia", "cappadocia-eau-de-parfum"),
    ("MP-TAMARINDO", "Tamarindo", "tamarindo-eau-de-parfum"),
    # Russian Leather - 메모파리 사이트에서 제거됨/변경됨
    ("MP-RUSSIAN-LEATHER", "Russian Leather", "russian-leather"),  # try alternate handle
    ("MP-SHAMS-OUD", "Shams Oud", "shams-oud-eau-de-parfum"),
    ("MP-KEDU", "Kedu", "kedu-eau-de-parfum"),
    ("MP-SICILIAN-LEATHER", "Sicilian Leather", "sicilian-leather-eau-de-parfum"),
    ("MP-SHERWOOD", "Sherwood", "sherwood-eau-de-parfum"),
    ("MP-ILHA-DO-MEL", "Ilha Do Mel", "ilha-do-mel-eau-de-parfum"),
    ("MP-ARGENTINA", "Argentina", "argentina-eau-de-parfum"),
    ("MP-INVERNESS", "Inverness", "inverness-eau-de-parfum"),
    ("MP-OCEAN-LEATHER", "Ocean Leather", "ocean-leather-eau-de-parfum"),
    ("MP-QUARTIERLATIN", "Quartier Latin", "quartier-latin-eau-de-parfum"),
    ("MP-WINTER-PALACE", "Winter Palace", "winter-palace-eau-de-parfum"),
    ("MP-FLAM", "Flam", "flam-eau-de-parfum"),
    ("MP-IBERIANLEATHER", "Iberian Leather", "iberian-leather-eau-de-parfum"),
    ("MP-ITALIAN-LEATHER", "Italian Leather", "italian-leather-eau-de-parfum"),
    ("MP-LALIBELA", "Lalibela", "lalibela-eau-de-parfum"),
    ("MP-INLE", "Inle", "inle-eau-de-parfum"),
    ("MP-ITHAQUE", "Ithaque", "ithaque-eau-de-parfum"),
    ("MP-SINTRA", "Sintra", "sintra-eau-de-parfum"),
    ("MP-FRENCH-LEATHER", "French Leather", "french-leather-eau-de-parfum"),
    ("MP-IRISH-LEATHER", "Irish Leather", "irish-leather-eau-de-parfum"),
    ("MP-MADURAI", "Madurai", "madurai-eau-de-parfum"),
    ("MP-MARFA", "Marfa", "marfa-eau-de-parfum"),
    ("MP-CAP-CAMARAT-X-OLIMPIA", "Cap Camarat X Olimpia", "cap-camarat-eau-de-parfum-olimpia-zagnoli"),
    ("MP-CASSIOPEIAROSE", "Cassiopeia Rose", "cassiopeia-rose-eau-de-parfum"),
    ("MP-PALAIS-BOURBON", "Palais Bourbon", "palais-bourbon-eau-de-parfum"),
    ("MP-ABU-DHABI", "Abu Dhabi", "abu-dhabi-eau-de-parfum"),
    ("MP-AFRICAN-LEATHER", "African Leather", "african-leather-eau-de-parfum"),
    # Tigers Nest - 다른 핸들 시도
    ("MP-TIGERS-NEST", "Tigers Nest", "tiger-s-nest-eau-de-parfum"),
    ("MP-MENORCA", "Menorca", "menorca-eau-de-parfum"),
]


# ============================================================
# 메모파리 이미지 추출 (User-Agent 적용)
# ============================================================
def fetch_product_images(handle: str) -> List[str]:
    url = f"https://www.memoparis.com/products/{handle}"
    
    try:
        resp = requests.get(
            url,
            headers={'User-Agent': HEADERS['User-Agent']},
            timeout=30
        )
        if resp.status_code != 200:
            print(f"  ⚠️ {handle}: HTTP {resp.status_code}")
            return []
        
        html = resp.text
        
        # Shopify CDN 이미지 패턴 (확장: 더 많은 형식 매칭)
        patterns = [
            r'https://www\.memoparis\.com/cdn/shop/files/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
            r'//www\.memoparis\.com/cdn/shop/files/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
            r'https://www\.memoparis\.com/cdn/shop/products/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
        ]
        
        all_matches = []
        for pattern in patterns:
            matches = re.findall(pattern, html)
            all_matches.extend(matches)
        
        # 중복 제거 + // 시작이면 https: 붙이기
        unique = []
        seen = set()
        for img in all_matches:
            full_url = 'https:' + img if img.startswith('//') else img
            # 사이즈 파라미터 제거 (원본 받기)
            clean_url = re.sub(r'(\?|&)v=\d+', '', full_url)
            clean_url = re.sub(r'(\?|&)width=\d+', '', clean_url)
            if clean_url not in seen:
                seen.add(clean_url)
                unique.append(clean_url)
        
        # 최대 6장
        return unique[:6]
    
    except Exception as e:
        print(f"  ❌ {handle}: {e}")
        return []


# ============================================================
# WooCommerce API (Session 사용 + 헤더 위장)
# ============================================================
def find_product_by_sku(sku: str) -> Optional[Dict]:
    try:
        resp = session.get(
            f"{WC_URL}/wp-json/wc/v3/products",
            params={'sku': sku},
            timeout=30
        )
        if resp.status_code == 200:
            results = resp.json()
            if results:
                return results[0]
        elif resp.status_code != 404:
            print(f"    [debug] SKU search status: {resp.status_code}")
    except Exception as e:
        print(f"    [debug] Lookup error: {e}")
    return None


def update_product_images(product_id: int, image_urls: List[str]) -> bool:
    if not image_urls:
        return False
    
    images = [{'src': url, 'position': i} for i, url in enumerate(image_urls)]
    
    try:
        resp = session.put(
            f"{WC_URL}/wp-json/wc/v3/products/{product_id}",
            json={'images': images},
            timeout=120  # 이미지 다운로드 시간 충분히
        )
        if resp.status_code in (200, 201):
            return True
        else:
            print(f"    [debug] Update status: {resp.status_code}")
            print(f"    [debug] Response: {resp.text[:200]}")
            return False
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
    print("🚀 KOHGANE Memo Paris Image Collector v2")
    print("=" * 70)
    print(f"Target: {WC_URL}")
    print(f"Products: {len(MEMO_PRODUCTS)}")
    print()
    
    # 사전 테스트: API 작동 확인
    print("Pre-flight: testing WC API access...")
    try:
        resp = session.get(f"{WC_URL}/wp-json/wc/v3/products", params={'per_page': 1}, timeout=15)
        if resp.status_code == 200:
            print(f"  ✅ API access OK\n")
        else:
            print(f"  ❌ API status: {resp.status_code}")
            print(f"  Response: {resp.text[:300]}")
            print(f"\n  → If 406, Bluehost ModSecurity is still blocking.")
            print(f"  → User-Agent should help, but may need to disable ModSecurity in cPanel.")
            return
    except Exception as e:
        print(f"  ❌ Pre-flight failed: {e}")
        return
    
    success = []
    failed_no_image = []
    failed_no_product = []
    failed_update = []
    
    for i, (sku, name, handle) in enumerate(MEMO_PRODUCTS, 1):
        print(f"[{i}/{len(MEMO_PRODUCTS)}] {name} ({sku})")
        
        # 1. 이미지 수집
        images = fetch_product_images(handle)
        if not images:
            print(f"  ⚠️ No images on memoparis.com")
            failed_no_image.append({'sku': sku, 'name': name, 'handle': handle})
            time.sleep(1)
            continue
        print(f"  ✅ Found {len(images)} images")
        
        # 2. WC 상품 찾기
        product = find_product_by_sku(sku)
        if not product:
            print(f"  ⚠️ SKU not found in WC")
            failed_no_product.append({'sku': sku, 'name': name})
            time.sleep(1)
            continue
        
        # 3. 이미지 업데이트
        if update_product_images(product['id'], images):
            print(f"  ✅ Updated #{product['id']}: {len(images)} images")
            success.append({'sku': sku, 'name': name, 'count': len(images)})
        else:
            print(f"  ❌ Update API failed")
            failed_update.append({'sku': sku, 'name': name})
        
        time.sleep(2)
    
    # 결과
    print("\n" + "=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    print(f"✅ Success: {len(success)}")
    print(f"⚠️ No image on source: {len(failed_no_image)}")
    print(f"⚠️ Not found in WC: {len(failed_no_product)}")
    print(f"❌ Update failed: {len(failed_update)}")
    print(f"📦 Total images uploaded: {sum(s['count'] for s in success)}")
    
    if failed_no_product:
        print(f"\nNot found in WC (first 5):")
        for f in failed_no_product[:5]:
            print(f"  - {f['name']} ({f['sku']})")
    
    summary = f"""🤖 *KOHGANE Image Collector v2*

✅ 성공: {len(success)}개
⚠️ 소스 이미지 없음: {len(failed_no_image)}개
⚠️ WC 매칭 안 됨: {len(failed_no_product)}개
❌ 업데이트 실패: {len(failed_update)}개

📦 총 {sum(s['count'] for s in success)}장 업로드"""
    
    send_telegram(summary)


if __name__ == '__main__':
    main()
