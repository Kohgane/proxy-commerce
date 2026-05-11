# 옴니채널 재고 동기화 운영 가이드 (Phase 147)

## 개요

Phase 147에서 쿠팡/스마트스토어/11번가 등 멀티채널 재고를 실시간으로 동기화하는 옴니채널 재고 모듈이 추가되었습니다.

## 환경변수

```env
INVENTORY_OMNI_SYNC_ENABLED=0        # 1 이면 활성 (기본: 0, 채널 연동 후 ON)
INVENTORY_OMNI_SYNC_MODE=common_pool # common_pool | per_channel
INVENTORY_OMNI_SYNC_INTERVAL_SEC=60  # 자동 동기화 주기 (초)
OMNI_SYNC_LOG_PATH=data/omni_sync_log.jsonl  # 로그 파일 경로
```

## 동기화 모드

### common_pool (기본)
- **공통 재고 풀**: 한 채널에서 판매 → 모든 채널 재고 동일하게 차감
- 예: 실재고 10개, 쿠팡 3개 판매 → 스마트스토어도 10→7로 자동 차감
- 단일 재고 풀 관리에 적합

### per_channel
- **채널 독립**: 채널별 재고를 별도로 관리
- 한 채널 판매가 다른 채널에 영향 없음
- 채널별 독립 운영 시 사용

## 활성화 방법

1. 마켓 API 설정 완료 (`COUPANG_VENDOR_ID`, `NAVER_COMMERCE_CLIENT_ID` 등)
2. 환경변수 설정: `INVENTORY_OMNI_SYNC_ENABLED=1`
3. 동기화 모드 선택: `INVENTORY_OMNI_SYNC_MODE=common_pool`
4. `/seller/inventory/omni`에서 채널별 재고 확인

## 판매 이벤트 연동

```python
from src.inventory.omni_sync import OmniInventorySyncer

syncer = OmniInventorySyncer()

# 쿠팡에서 3개 판매 → 다른 채널 재고 자동 차감
result = syncer.on_sale("SKU-001", sold_qty=3, source_channel="coupang")
# result: {"smartstore": True, "11st": False}
```

## 수동 동기화

```python
# 특정 SKU 모든 채널 재고 조회 후 동기화
channel_qty = syncer.manual_sync("SKU-001")
# channel_qty: {"coupang": 10, "smartstore": 10, "11st": 0}
```

## 관리 UI

- `/seller/inventory/omni` — 채널별 재고 조회 + 수동 동기화
- `/admin/diagnostics` → "📦 옴니채널 재고 동기화" 섹션

## 동기화 로그

로그 파일: `data/omni_sync_log.jsonl`

```python
from src.inventory.omni_sync import OmniSyncLog
log = OmniSyncLog()
for event in log.recent(20):
    print(event)
```

## 채널 어댑터 추가

신규 마켓 채널 추가 시 `src/inventory/omni_sync.py`에 `ChannelStockAdapter` 서브클래스 구현:

```python
class NewMarketAdapter(ChannelStockAdapter):
    channel = "newmarket"
    
    def is_configured(self) -> bool:
        return bool(os.getenv("NEWMARKET_API_KEY"))
    
    def get_stock(self, sku: str) -> int:
        # 재고 조회 구현
        return 0
    
    def set_stock(self, sku: str, stock: int) -> bool:
        # 재고 업데이트 구현
        return True
```

그리고 `_build_adapters()` 함수에 추가:
```python
def _build_adapters():
    return [
        CoupangStockAdapter(),
        SmartstoreStockAdapter(),
        ElevenStockAdapter(),
        NewMarketAdapter(),  # 추가
    ]
```

## 관련 파일

- `src/inventory/omni_sync.py` — 동기화 엔진 + 채널 어댑터
- `src/seller_console/views.py` — `/seller/inventory/omni` 라우트
- `src/dashboard/admin_views.py` — 진단 카드
