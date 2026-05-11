# 멀티마켓 동시 등록 가이드 (Phase 149)

## 개요

Phase 149의 멀티마켓 동시 등록 기능은 `src/ai_listing/multi_publisher.py`에 구현되어 있습니다.
`ThreadPoolExecutor`를 사용해 여러 마켓에 병렬 등록하며, 부분 성공을 허용합니다.

## 지원 마켓

| 마켓 | 코드 | 상태 |
|------|------|------|
| 쿠팡 | `coupang` | mock (Phase 149) / 실 API 예정 (Phase 150) |
| 스마트스토어 | `smartstore` | mock (Phase 149) / 실 API 예정 (Phase 150) |
| 11번가 | `11st` | mock |
| G마켓 | `gmarket` | mock |

## 부분 성공 처리

일부 마켓 등록이 실패해도 전체 결과를 반환합니다:

```python
result = publish_to_markets(
    ai_listing_id="uuid-...",
    product_data={...},
    markets=["coupang", "smartstore", "11st"],
)

print(result.success_count)   # 2
print(result.failed_count)    # 1
print(result.partial_success) # True
```

실패한 마켓은 Phase 147 잡 큐(`src/jobs/queue_manager.py`)에 자동 재시도 요청이 등록됩니다.

## 새 마켓 어댑터 추가 방법

### Step 1: Phase 143 auto_publish.py에 채널 어댑터 추가

```python
# src/listing/auto_publish.py 내 publish_to_channel 함수 확장
def publish_to_channel(channel: str, product: dict) -> dict:
    if channel == "newmarket":
        return _publish_newmarket(product)
    ...
```

### Step 2: 카테고리 매핑 추가

```python
# src/ai_listing/category_mapper.py
_NEWMARKET_CATEGORY_MAP = {
    "패션": "nm_1001",
    "뷰티": "nm_1002",
    ...
    "default": "nm_1001",
}
_MARKET_CATEGORY_MAPS["newmarket"] = _NEWMARKET_CATEGORY_MAP
```

### Step 3: 제목 글자수 제한 추가

```python
# src/ai_listing/templates_prompts.py
MARKET_TITLE_MAX_LEN["newmarket"] = 80
```

### Step 4: 수수료율 추가 (선택)

```python
# src/ai_listing/price_suggester.py
_MARKET_FEE_RATES["newmarket"] = 0.09
```

### Step 5: 금칙어 추가 (선택)

```python
# src/ai_listing/templates_prompts.py
MARKET_FORBIDDEN_TERMS["newmarket"] = ["최저가", "보장"]
```

### Step 6: 기본 마켓 목록에 추가 (선택)

```env
AI_LISTING_MARKETS_DEFAULT=coupang,smartstore,newmarket
```

## 실패 재시도 흐름

```
publish_to_markets() 호출
        ↓
ThreadPoolExecutor (max_workers=4) 병렬 실행
        ↓
각 마켓 어댑터 호출
        ↓
실패 시 → _enqueue_retry() → FileJobQueue 등록
        ↓
Phase 147 잡 큐 worker가 재시도 처리
```

## 모니터링

`/admin/diagnostics` → **📤 멀티마켓 동시 등록** 섹션에서:
- 24h 등록 시도 / 성공 / 실패 건수
- 마켓별 통계

## 코드 위치

| 파일 | 역할 |
|------|------|
| `src/ai_listing/multi_publisher.py` | 멀티마켓 동시 등록 메인 로직 |
| `src/listing/auto_publish.py` | Phase 143 채널별 어댑터 (본 구현 시 연동) |
| `src/jobs/queue_manager.py` | Phase 147 잡 큐 (재시도) |
| `src/ai_listing/category_mapper.py` | 마켓별 카테고리 코드 |
| `src/ai_listing/templates_prompts.py` | 마켓별 제약 (제목 길이, 금칙어) |
