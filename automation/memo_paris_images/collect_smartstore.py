"""
KOHGANE - Smartstore Image Extractor
=========================================
너 스마트스토어 50개 상품에서 이미지 자동 추출.

[작동 흐름]
1. 너 Listly 파일에서 50개 상품 URL 읽기
2. 각 상품 페이지에서 이미지 추출 시도:
   a) 정적 HTML 파싱 (가장 빠름)
   b) Naver API 호출 (백업)
   c) 메타 태그 og:image (최후)
3. WooCommerce에 업로드
4. 결과 + 실패 리스트 출력
"""

import os
import re
import json
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
# 헤더 — 진짜 브라우저처럼
# ============================================================
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Upgrade-Insecure-Requests': '1',
}

session = requests.Session()
session.headers.update(HEADERS)

wc_session = requests.Session()
wc_session.auth = (WC_KEY, WC_SECRET)
wc_session.headers.update({
    'User-Agent': HEADERS['User-Agent']
})


# ============================================================
# 50개 상품 URL 매핑
# ============================================================
# (SKU, Smartstore URL) 형식
SMARTSTORE_PRODUCTS = [
    ("MP-EAU-DE-MEMO", "https://smartstore.naver.com/gocosmos/products/13432620224"),
    # 나머지는 너 Listly 파일에서 가져옴
    # 실행 시 listly_data.json에서 읽음
]


def load_products_from_listly():
    """Listly JSON에서 상품 매핑 로드"""
    listly_path = os.path.join(os.path.dirname(__file__), 'memo_smartstore_urls.json')
    if not os.path.exists(listly_path):
        print(f"⚠️ {listly_path} not found")
        return SMARTSTORE_PRODUCTS
    
    with open(listly_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return [(item['sku'], item['url']) for item in data]


# ============================================================
# 이미지 추출 - 3단계 시도
# ============================================================

def extract_images_static(html: str) -> List[str]:
    """방법 1: 정적 HTML에서 직접 추출"""
    patterns = [
        r'https://shop-phinf\.pstatic\.net/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
        r'https://shopping-phinf\.pstatic\.net/[^"\'?\s]+\.(?:jpg|jpeg|png|webp)',
        # JSON 안에 들어있을 가능성
        r'"https://shop-phinf\.pstatic\.net/[^"]+"',
        r'"https://shopping-phinf\.pstatic\.net/[^"]+"',
    ]
    
    all_images = []
    for pattern in patterns:
        matches = re.findall(pattern, html)
        all_images.extend(matches)
    
    # 정리
    cleaned = []
    seen = set()
    for img in all_images:
        # 따옴표 제거
        img = img.strip('"')
        # 사이즈 파라미터 정규화 (원본 받기)
        clean = re.sub(r'\?type=[fw]\d+_\d+', '', img)
        clean = re.sub(r'\?type=w\d+', '', clean)
        if clean not in seen and any(ext in clean for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            seen.add(clean)
            cleaned.append(clean)
    
    return cleaned


def extract_images_meta(html: str) -> List[str]:
    """방법 2: og:image 메타 태그 등에서 추출"""
    patterns = [
        r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+name=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
    ]
    
    images = []
    for pattern in patterns:
        matches = re.findall(pattern, html)
        images.extend(matches)
    
    return images


def extract_images_json(html: str) -> List[str]:
    """방법 3: __NEXT_DATA__ JSON에서 이미지 추출"""
    # Next.js 페이지는 __NEXT_DATA__ script 태그에 모든 데이터 있음
    next_data_match = re.search(
        r'<script\s+id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>',
        html
    )
    
    if not next_data_match:
        return []
    
    try:
        data = json.loads(next_data_match.group(1))
        # 재귀로 이미지 URL 찾기
        images = set()
        
        def find_images(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, str) and 'pstatic.net' in v and any(ext in v for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        images.add(v.split('?')[0])  # 사이즈 파라미터 제거
                    else:
                        find_images(v)
            elif isinstance(obj, list):
                for item in obj:
                    find_images(item)
        
        find_images(data)
        return list(images)
    except json.JSONDecodeError:
        return []


def fetch_smartstore_images(url: str) -> List[str]:
    """3단계 시도로 이미지 추출"""
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"    [debug] HTTP {resp.status_code}")
            return []
        
        html = resp.text
        
        # 방법 1: 정적
        images = extract_images_static(html)
        if len(images) >= 4:
            print(f"    [debug] Method 1 (static): {len(images)}")
            return images[:6]
        
        # 방법 2: __NEXT_DATA__ JSON
        json_images = extract_images_json(html)
        if json_images:
            print(f"    [debug] Method 3 (JSON): {len(json_images)}")
            # 정적이랑 합치기
            combined = list(set(images + json_images))
            return combined[:6]
        
        # 방법 3: 메타 태그
        meta_images = extract_images_meta(html)
        if meta_images:
            print(f"    [debug] Method 2 (meta): {len(meta_images)}")
            combined = list(set(images + meta_images))
            return combined[:6]
        
        # 다 안되면 정적 결과 반환
        return images
    
    except Exception as e:
        print(f"    [debug] Error: {e}")
        return []


# ============================================================
# WooCommerce
# ============================================================
def find_product_by_sku(sku: str) -> Optional[Dict]:
    variations = [sku, sku.replace('×', 'X'), sku.replace('-X-', '-x-')]
    for var in variations:
        try:
            resp = wc_session.get(
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
        resp = wc_session.put(
            f"{WC_URL}/wp-json/wc/v3/products/{product_id}",
            json={'images': images},
            timeout=120
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"    [debug] Update error: {e}")
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
    print("🚀 KOHGANE Smartstore Image Extractor")
    print("=" * 70)
    
    # 사전 테스트: 한 페이지만 시도
    print("\n[Pre-flight] Testing one Smartstore page...")
    test_url = "https://smartstore.naver.com/gocosmos/products/13432620224"
    test_resp = session.get(test_url, timeout=15, allow_redirects=True)
    print(f"  Status: {test_resp.status_code}")
    print(f"  Content length: {len(test_resp.text)}")
    
    if test_resp.status_code != 200:
        print(f"  ❌ Smartstore blocked our request (HTTP {test_resp.status_code})")
        print(f"  → 자동 추출 불가능. Listly 또는 수동 다운로드 필요.")
        send_telegram(f"❌ Smartstore blocked. Status: {test_resp.status_code}")
        return
    
    test_images = fetch_smartstore_images(test_url)
    print(f"  Extracted: {len(test_images)} images")
    
    if not test_images:
        print(f"\n❌ 이미지 추출 실패. Smartstore가 SPA(JavaScript 렌더링)일 가능성.")
        print(f"→ Listly 또는 수동 다운로드 필요.")
        send_telegram("❌ Smartstore image extraction failed - SPA detected")
        return
    
    print(f"\n✅ Sample images extracted! Proceeding with all 50...")
    print(f"Sample image URLs:")
    for img in test_images[:3]:
        print(f"  {img[:100]}")
    
    # 본 작업
    products = load_products_from_listly()
    print(f"\nLoaded {len(products)} products")
    
    success = []
    failed = []
    
    for i, (sku, url) in enumerate(products, 1):
        print(f"\n[{i}/{len(products)}] {sku}")
        
        images = fetch_smartstore_images(url)
        if not images:
            print(f"  ⚠️ No images")
            failed.append({'sku': sku, 'reason': 'no images'})
            time.sleep(2)
            continue
        
        print(f"  ✅ Found {len(images)} images")
        
        product = find_product_by_sku(sku)
        if not product:
            print(f"  ⚠️ SKU not in WC")
            failed.append({'sku': sku, 'reason': 'no SKU match'})
            time.sleep(2)
            continue
        
        if update_images(product['id'], images):
            print(f"  ✅ Updated #{product['id']}")
            success.append({'sku': sku, 'count': len(images)})
        else:
            print(f"  ❌ Update failed")
            failed.append({'sku': sku, 'reason': 'update failed'})
        
        time.sleep(2)
    
    # 결과
    print("\n" + "=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    print(f"✅ Success: {len(success)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"📦 Total images: {sum(s['count'] for s in success)}")
    
    summary = f"""🤖 *KOHGANE Smartstore*

✅ 성공: {len(success)}개
❌ 실패: {len(failed)}개
📦 {sum(s['count'] for s in success)}장 업로드"""
    send_telegram(summary)


if __name__ == '__main__':
    main()
