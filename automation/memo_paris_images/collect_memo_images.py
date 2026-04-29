"""
KOHGANE - Memo Paris Image Collector
=====================================

메모파리 공식 사이트에서 50개 상품 이미지 자동 수집 + WooCommerce 업데이트.

[작동 흐름]
1. 메모파리 50개 상품 페이지 순회
2. 각 페이지에서 이미지 URL 추출 (4~6장씩)
3. WooCommerce REST API로 상품 검색 (SKU 기반)
4. Featured Image + Gallery 자동 매핑
5. Telegram 알림

[환경 변수 - GitHub Secrets]
WC_URL: https://kohganemultishop.org
WC_KEY: ck_xxx (WooCommerce Consumer Key)
WC_SECRET: cs_xxx (WooCommerce Consumer Secret)
TELEGRAM_TOKEN (optional)
TELEGRAM_CHAT_ID (optional)

[실행]
GitHub Actions 수동 트리거 (workflow_dispatch)
"""

import os
import re
import time
import requests
from typing import List, Dict, Optional

# ============================================================
# 환경 변수
# ============================================================
WC_URL = os.environ.get('WC_URL', 'https://kohganemultishop.org').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# 검증
if not WC_KEY or not WC_SECRET:
    print("❌ ERROR: WC_KEY and WC_SECRET must be set as environment variables")
    exit(1)


# ============================================================
# 메모파리 50개 상품 매핑
# ============================================================
MEMO_PRODUCTS = [
    # (SKU, English Name, memoparis.com handle)
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
    ("MP-RUSSIAN-LEATHER", "Russian Leather", "russian-leather-eau-de-parfum"),
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
    ("MP-TIGERS-NEST", "Tigers Nest", "tigers-nest-eau-de-parfum"),
    ("MP-MENORCA", "Menorca", "menorca-eau-de-parfum"),
]


# ============================================================
# 이미지 URL 추출
# ============================================================
def fetch_product_images(handle: str) -> List[str]:
    """
    메모파리 상품 페이지에서 이미지 URL 추출.
    Shopify 사이트라 패턴이 일관됨.
    """
    url = f"https://www.memoparis.com/products/{handle}"
    
    try:
        resp = requests.get(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'},
            timeout=30
        )
        if resp.status_code != 200:
            print(f"  ⚠️ {handle}: HTTP {resp.status_code}")
            return []
        
        html = resp.text
        
        # Shopify CDN 이미지 패턴
        # https://www.memoparis.com/cdn/shop/files/{handle}-eau-de-parfum-75ml-{XXX}.jpg
        pattern = r'https://www\.memoparis\.com/cdn/shop/files/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)'
        matches = re.findall(pattern, html)
        
        # 중복 제거 + 정렬
        unique_images = list(dict.fromkeys(matches))  # 순서 유지하며 중복 제거
        
        # 75ml 이미지만 필터 (200ml, 30ml, 10ml 제외)
        filtered = [img for img in unique_images if '75ml' in img or 'eau-de-parfum' in img.lower()]
        
        # 우선순위: 75ml-XXX 패턴 > 다른 패턴
        priority = [img for img in filtered if re.search(r'75ml-\d+', img)]
        non_priority = [img for img in filtered if img not in priority]
        
        result = (priority + non_priority)[:6]  # 최대 6장
        
        return result
    
    except Exception as e:
        print(f"  ❌ {handle}: {e}")
        return []


# ============================================================
# WooCommerce API
# ============================================================
def find_product_by_sku(sku: str) -> Optional[Dict]:
    """SKU로 워드프레스 상품 조회"""
    try:
        resp = requests.get(
            f"{WC_URL}/wp-json/wc/v3/products",
            params={'sku': sku},
            auth=(WC_KEY, WC_SECRET),
            timeout=30
        )
        if resp.status_code == 200:
            results = resp.json()
            if results:
                return results[0]
    except Exception as e:
        print(f"  ⚠️ Product lookup failed: {e}")
    return None


def update_product_images(product_id: int, image_urls: List[str]) -> bool:
    """
    상품 이미지 업데이트.
    첫 이미지 = Featured Image
    나머지 = Gallery
    """
    if not image_urls:
        return False
    
    # WooCommerce 이미지 형식
    # src URL을 주면 자동으로 미디어 라이브러리에 다운로드 + 저장
    images = [{'src': url, 'position': i} for i, url in enumerate(image_urls)]
    
    try:
        resp = requests.put(
            f"{WC_URL}/wp-json/wc/v3/products/{product_id}",
            json={'images': images},
            auth=(WC_KEY, WC_SECRET),
            timeout=60  # 이미지 다운로드 시간 고려
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"  ⚠️ Update failed: {e}")
        return False


# ============================================================
# Telegram
# ============================================================
def send_telegram(message: str):
    """Telegram 알림 (옵션)"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown'
            },
            timeout=10
        )
    except Exception:
        pass


# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 70)
    print("🚀 KOHGANE Memo Paris Image Collector")
    print("=" * 70)
    print(f"Target: {WC_URL}")
    print(f"Products to process: {len(MEMO_PRODUCTS)}")
    print()
    
    success = []
    failed = []
    not_found = []
    
    for i, (sku, name, handle) in enumerate(MEMO_PRODUCTS, 1):
        print(f"[{i}/{len(MEMO_PRODUCTS)}] {name} ({sku})")
        
        # 1. 메모파리 사이트에서 이미지 가져오기
        images = fetch_product_images(handle)
        
        if not images:
            print(f"  ⚠️ No images found at memoparis.com/products/{handle}")
            failed.append({'sku': sku, 'name': name, 'reason': 'No images on source'})
            time.sleep(1)
            continue
        
        print(f"  ✅ Found {len(images)} images")
        
        # 2. 워드프레스 상품 찾기
        product = find_product_by_sku(sku)
        if not product:
            print(f"  ⚠️ Product not found in WooCommerce")
            not_found.append({'sku': sku, 'name': name})
            time.sleep(1)
            continue
        
        # 3. 이미지 업데이트
        if update_product_images(product['id'], images):
            print(f"  ✅ Updated product #{product['id']} with {len(images)} images")
            success.append({
                'sku': sku, 'name': name, 'id': product['id'],
                'image_count': len(images)
            })
        else:
            print(f"  ❌ Update failed")
            failed.append({'sku': sku, 'name': name, 'reason': 'API update failed'})
        
        # Rate limiting (메모파리 사이트 부담 줄이기)
        time.sleep(2)
    
    # 결과 출력
    print()
    print("=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    print(f"✅ Success: {len(success)}")
    print(f"⚠️ Not found in WC: {len(not_found)}")
    print(f"❌ Failed: {len(failed)}")
    
    if not_found:
        print("\nNot found in WooCommerce (SKU mismatch):")
        for item in not_found[:10]:
            print(f"  - {item['name']} ({item['sku']})")
    
    if failed:
        print("\nFailed:")
        for item in failed[:10]:
            print(f"  - {item['name']}: {item['reason']}")
    
    # Telegram 알림
    summary = f"""🤖 *KOHGANE Image Collector*

✅ 성공: {len(success)}개
⚠️ WC에서 못 찾음: {len(not_found)}개
❌ 실패: {len(failed)}개

총 이미지: {sum(s['image_count'] for s in success)}장 업로드"""
    
    send_telegram(summary)
    print(f"\n{'='*70}")
    print(f"Total images uploaded: {sum(s['image_count'] for s in success)}")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
