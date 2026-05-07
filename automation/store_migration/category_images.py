"""
KOHGANE - 카테고리 분위기 이미지 자동 설정
==============================================
각 카테고리에 Pexels에서 큐레이션된 분위기 이미지 자동 설정.
"""

import os
import requests
import time
from typing import Optional

WC_URL = os.environ.get('WC_URL', '').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')
PEXELS_KEY = os.environ.get('PEXELS_API_KEY', '')

if not WC_KEY or not PEXELS_KEY:
    print("❌ Required: WC_KEY, WC_SECRET, PEXELS_API_KEY")
    exit(1)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
}

session = requests.Session()
session.auth = (WC_KEY, WC_SECRET)
session.headers.update(HEADERS)


# ============================================================
# 카테고리 → 큐레이션된 검색 키워드 매핑
# ============================================================
CATEGORY_KEYWORDS = {
    # 메인 카테고리
    'Fragrance': 'luxury perfume bottle minimal',
    'Home': 'minimalist luxury home interior',
    'Body & Care': 'marble bathroom luxury minimal',
    'Tech': 'minimalist desk technology',
    'Footwear': 'leather sandals beach california',
    'Kids & Baby': 'scandinavian baby room minimal',
    'Bags & Accessories': 'luxury leather bag',
    'Workspace': 'minimalist desk workspace',
    
    # 하위 카테고리
    'Tabletop': 'italian dining table luxury',
    'Candles': 'candle flame ambient warm',
    'Bath & Shower': 'marble bathroom luxury',
    'Skincare': 'minimal skincare bottles',
    'Deodorant': 'wellness body care',
    'Phone Cases': 'minimal phone accessories',
    'Stand & Wallet': 'leather wallet minimal',
}


def fetch_pexels_image(keyword: str, orientation: str = 'landscape') -> Optional[str]:
    """Pexels에서 이미지 1장 가져오기"""
    try:
        resp = requests.get(
            'https://api.pexels.com/v1/search',
            params={
                'query': keyword,
                'per_page': 5,  # 5개 중 큐레이션
                'orientation': orientation,
                'size': 'large',
            },
            headers={'Authorization': PEXELS_KEY},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            photos = data.get('photos', [])
            if photos:
                # 첫 번째 사진의 large 사이즈 (1280px)
                return photos[0].get('src', {}).get('large', '')
    except Exception as e:
        print(f"  Pexels error: {e}")
    return None


def upload_image_to_wp(image_url: str) -> Optional[int]:
    """이미지를 워드프레스 미디어 라이브러리에 업로드 (URL 방식)"""
    try:
        # 1. 이미지 다운로드
        img_resp = requests.get(image_url, timeout=30)
        if img_resp.status_code != 200:
            return None
        
        # 2. 워드프레스 미디어로 업로드
        filename = image_url.split('/')[-1].split('?')[0] + '.jpg'
        if '.' not in filename:
            filename = 'category-image.jpg'
        
        upload_resp = session.post(
            f"{WC_URL}/wp-json/wp/v2/media",
            data=img_resp.content,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'image/jpeg',
                'User-Agent': HEADERS['User-Agent'],
            },
            timeout=60
        )
        
        if upload_resp.status_code in (200, 201):
            return upload_resp.json().get('id')
    except Exception as e:
        print(f"  Upload error: {e}")
    return None


def get_categories():
    """모든 카테고리 가져오기"""
    cats = []
    page = 1
    while True:
        try:
            resp = session.get(
                f"{WC_URL}/wp-json/wc/v3/products/categories",
                params={'per_page': 100, 'page': page},
                timeout=15
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            cats.extend(data)
            page += 1
            if len(data) < 100:
                break
        except Exception as e:
            print(f"Get cats error: {e}")
            break
    return cats


def update_category_image(cat_id: int, media_id: int) -> bool:
    """카테고리에 이미지 설정"""
    try:
        resp = session.put(
            f"{WC_URL}/wp-json/wc/v3/products/categories/{cat_id}",
            json={'image': {'id': media_id}},
            timeout=30
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


def main():
    print("=" * 70)
    print("🎨 KOHGANE Category Image Setter")
    print("=" * 70)
    
    cats = get_categories()
    print(f"카테고리 {len(cats)}개 발견\n")
    
    success = 0
    failed = []
    
    for cat in cats:
        name = cat.get('name', '')
        cat_id = cat.get('id')
        slug = cat.get('slug', '')
        
        # 매핑 찾기
        keyword = CATEGORY_KEYWORDS.get(name)
        if not keyword:
            # 슬러그로도 시도
            keyword = CATEGORY_KEYWORDS.get(name.title())
        
        if not keyword:
            print(f"⏭️  {name} (slug: {slug}) - 매핑 없음, 스킵")
            continue
        
        # 이미 이미지 있으면 스킵 (덮어쓰기 안 함)
        if cat.get('image'):
            print(f"⏭️  {name} - 이미 이미지 있음")
            continue
        
        print(f"🎨 {name}")
        print(f"   검색: {keyword}")
        
        # Pexels에서 이미지
        img_url = fetch_pexels_image(keyword)
        if not img_url:
            print(f"   ❌ Pexels에서 못 찾음")
            failed.append(name)
            continue
        
        print(f"   📥 다운로드: {img_url[:60]}...")
        
        # 워드프레스에 업로드
        media_id = upload_image_to_wp(img_url)
        if not media_id:
            print(f"   ❌ 워드프레스 업로드 실패")
            failed.append(name)
            time.sleep(2)
            continue
        
        # 카테고리에 설정
        if update_category_image(cat_id, media_id):
            print(f"   ✅ 설정 완료 (media #{media_id})")
            success += 1
        else:
            print(f"   ❌ 카테고리 설정 실패")
            failed.append(name)
        
        time.sleep(2)
    
    print("\n" + "=" * 70)
    print(f"✅ 성공: {success}")
    print(f"❌ 실패: {len(failed)}")
    if failed:
        print(f"실패: {failed}")


if __name__ == '__main__':
    main()
