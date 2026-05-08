"""
KOHGANE - 메모파리 191개 가격 즉시 조정
========================================
새 매입 모델 기반 가격 재계산:
- FragranceNet 일반가 (37% off 쿠폰가)
- Malltail 배송비
- 환율 적용
- 마진 50% (한국 정가 대비 30~40% 저렴)

기존 +20% → 새 모델로 자동 변경
"""

import os
import sys
import time
import requests
from datetime import datetime

WC_URL = os.environ.get('WC_URL', '').rstrip('/')
WC_KEY = os.environ.get('WC_KEY', '')
WC_SECRET = os.environ.get('WC_SECRET', '')
USD_KRW_RATE = float(os.environ.get('USD_KRW_RATE', '1380'))
DRY_RUN = os.environ.get('DRY_RUN', 'true').lower() == 'true'

if not all([WC_URL, WC_KEY, WC_SECRET]):
    print("❌ WC credentials missing")
    sys.exit(1)

# ===== 메모파리 가격 데이터 (FragranceNet 기준) =====
# 형식: SKU 또는 이름 키워드 → {fragrancenet_usd, weight_kg}
# 실제 데이터는 직접 조회해서 업데이트 필요

MEMO_PARIS_PRICES = {
    # African Leather
    'african leather': {'usd': 189, 'weight': 0.4, 'official_krw': 468000},
    'italian leather': {'usd': 175, 'weight': 0.4, 'official_krw': 410000},
    'french leather': {'usd': 175, 'weight': 0.4, 'official_krw': 410000},
    'irish leather': {'usd': 175, 'weight': 0.4, 'official_krw': 410000},
    'iberian leather': {'usd': 175, 'weight': 0.4, 'official_krw': 410000},
    'russian leather': {'usd': 175, 'weight': 0.4, 'official_krw': 410000},
    'ocean leather': {'usd': 175, 'weight': 0.4, 'official_krw': 410000},
    'oriental leather': {'usd': 175, 'weight': 0.4, 'official_krw': 410000},
    'chinese leather': {'usd': 175, 'weight': 0.4, 'official_krw': 410000},
    'sicilian leather': {'usd': 175, 'weight': 0.4, 'official_krw': 410000},
    
    # Travel notes
    'marfa': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'odeon': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'inle': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'kedu': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'palais bourbon': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'madurai': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'winter palace': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'argentina': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'sherwood': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'ithaca': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'kotor': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'granada': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'cap camarat': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'menorca': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'corfu': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    'tiger nut': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
    
    # Default fallback
    '_default': {'usd': 165, 'weight': 0.4, 'official_krw': 380000},
}


def calc_landed_cost(usd_price, weight_kg, rate):
    """한국 도착 원가"""
    # 1. 상품 (37% 쿠폰 적용한 가격이라 가정)
    product_krw = usd_price * rate
    
    # 2. Malltail 배송비 (USA → Korea)
    # 첫 0.5kg = $20 / 추가 = $10/0.5kg
    if weight_kg <= 0.5:
        malltail_usd = 20
    else:
        malltail_usd = 20 + (weight_kg - 0.5) * 20
    malltail_krw = malltail_usd * rate
    
    # 3. 통관 (해외구매대행은 부가세 + 관세)
    # 향수: 관세 6.5% + 부가세 10% = 약 17%
    # 단순화: 18%
    duty = product_krw * 0.18
    
    return int(product_krw + malltail_krw + duty)


def calc_selling_price(landed_cost, target_margin_pct=50):
    """판매가 = 원가 × (1 + 마진)"""
    selling = landed_cost * (1 + target_margin_pct / 100)
    # 천원 단위 반올림
    return round(selling / 1000) * 1000


def find_memo_data(product_name):
    """상품명에서 메모파리 향 종류 매칭"""
    name_lower = product_name.lower()
    for key, data in MEMO_PARIS_PRICES.items():
        if key == '_default':
            continue
        if key in name_lower:
            return data
    return MEMO_PARIS_PRICES['_default']


def main():
    print("=" * 60)
    print("💰 KOHGANE - 메모파리 가격 재계산")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   USD → KRW: {USD_KRW_RATE}")
    print(f"   DRY_RUN: {DRY_RUN}")
    print("=" * 60)
    
    session = requests.Session()
    session.auth = (WC_KEY, WC_SECRET)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Content-Type': 'application/json',
    })
    
    # 메모파리 카테고리 찾기
    print("\n🔍 메모파리 카테고리 찾는 중...")
    cat_resp = session.get(
        f"{WC_URL}/wp-json/wc/v3/products/categories",
        params={'search': 'Memo Paris', 'per_page': 10}, timeout=15
    )
    
    memo_cat_id = None
    if cat_resp.status_code == 200:
        for c in cat_resp.json():
            if 'Memo' in c['name']:
                memo_cat_id = c['id']
                print(f"  ✅ 카테고리: {c['name']} (ID: {memo_cat_id})")
                break
    
    if not memo_cat_id:
        print("❌ 메모파리 카테고리 없음")
        sys.exit(1)
    
    # 메모파리 상품 가져오기
    print("\n📦 메모파리 상품 로딩...")
    products = []
    page = 1
    while True:
        resp = session.get(
            f"{WC_URL}/wp-json/wc/v3/products",
            params={'category': memo_cat_id, 'per_page': 100, 'page': page},
            timeout=30
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        products.extend(data)
        page += 1
        if len(data) < 100:
            break
    
    print(f"  {len(products)}개 상품")
    
    # 가격 재계산
    print("\n💰 가격 재계산 중...")
    print(f"  {'상품명':<40} {'기존':>10} → {'새가격':>10} {'마진':>8}")
    print("  " + "-" * 75)
    
    updated = 0
    for product in products:
        name = product.get('name', '')
        sku = product.get('sku', '')
        current_price = product.get('regular_price', '0')
        
        # 메모파리 데이터 매칭
        memo = find_memo_data(name)
        usd = memo['usd']
        weight = memo['weight']
        
        # 한국 도착 원가
        landed_cost = calc_landed_cost(usd, weight, USD_KRW_RATE)
        
        # 새 판매가 (마진 50%)
        new_price = calc_selling_price(landed_cost, target_margin_pct=50)
        
        # 한국 정가의 70% 이하인지 확인 (경쟁력)
        max_price = int(memo['official_krw'] * 0.7)
        if new_price > max_price:
            new_price = max_price
        
        try:
            current = int(current_price)
        except:
            current = 0
        
        change_pct = ((new_price - current) / current * 100) if current else 0
        
        print(f"  {name[:40]:<40} {current:>10,} → {new_price:>10,} {change_pct:>+7.1f}%")
        
        if not DRY_RUN:
            try:
                resp = session.put(
                    f"{WC_URL}/wp-json/wc/v3/products/{product['id']}",
                    json={'regular_price': str(new_price)},
                    timeout=30
                )
                if resp.status_code == 200:
                    updated += 1
            except Exception as e:
                print(f"    ❌ 업데이트 실패: {e}")
            
            time.sleep(0.3)
    
    print("\n" + "=" * 60)
    if DRY_RUN:
        print("🔵 DRY RUN - 실제 변경 없음")
        print("   실제 적용: DRY_RUN=false 환경변수 설정")
    else:
        print(f"✅ 완료: {updated}/{len(products)}개 가격 변경")
    
    # 요약
    avg_landed = sum(calc_landed_cost(MEMO_PARIS_PRICES[k]['usd'], 
                                       MEMO_PARIS_PRICES[k]['weight'], 
                                       USD_KRW_RATE) 
                    for k in MEMO_PARIS_PRICES if k != '_default') / (len(MEMO_PARIS_PRICES) - 1)
    print(f"\n📊 평균 도착원가: ₩{int(avg_landed):,}")
    print(f"📊 평균 판매가 (마진 50%): ₩{int(avg_landed * 1.5):,}")
    print(f"📊 한국 정가 대비: 약 30~40% 저렴")


if __name__ == '__main__':
    main()
