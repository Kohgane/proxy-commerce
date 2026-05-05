# COLLECTORS.md — 수동 수집기 구조 (Phase 128)

URL 붙여넣기 → 도메인 감지 → 적절한 collector → 상품 메타데이터 추출.

---

## 수집기 종류

| 수집기 | 소스 문자열 | 설명 |
|---|---|---|
| `AmazonCollector` | `amazon_paapi` / `amazon_og` | Amazon US/JP. PA-API → OG 메타 폴백 |
| `RakutenCollector` | `rakuten_api` / `rakuten_og` | 라쿠텐 이치바. WS API → OG 메타 폴백 |
| `AloCollector` | `alo_scrape` / `alo_og` | Alo Yoga. JSON-LD 스크래핑 → OG 폴백 |
| `LululemonCollector` | `lululemon_scrape` / `lululemon_og` | lululemon. JSON-LD 스크래핑 → OG 폴백 |
| `GenericOgCollector` | `generic_og` | 기타 모든 사이트. OG 메타 + JSON-LD 파싱 |

---

## 도메인 매핑

```
amazon.com / amazon.co.jp / amazon.co.uk / amazon.de / amazon.fr → AmazonCollector
rakuten.co.jp (및 서브도메인) → RakutenCollector
aloyoga.com → AloCollector
shop.lululemon.com / lululemon.com → LululemonCollector
그 외 → GenericOgCollector
```

미지원 도메인 (OG 폴백 + 경고):
- `1688.com`, `taobao.com`, `tmall.com`

---

## 폴백 체인

```
API 키 활성 → 실 API 호출
API 키 미설정 → OG 메타태그 파싱
OG 태그 없음 → JSON-LD schema 시도
실패 시 → success=False + error 메시지
```

---

## CollectorResult 필드

```python
@dataclass
class CollectorResult:
    success: bool
    url: str
    source: str          # 수집 소스 ("amazon_paapi", "amazon_og", ...)
    title: Optional[str]
    description: Optional[str]
    images: list[str]
    price: Optional[Decimal]
    currency: Optional[str]
    sku: Optional[str]
    asin: Optional[str]  # Amazon 전용
    brand: Optional[str]
    category: Optional[str]
    attributes: dict
    warnings: list[str]  # 경고 메시지 (폴백 발생 등)
    error: Optional[str]
```

---

## 새 수집기 추가 방법

1. `src/seller_console/collectors/` 에 새 파일 생성:

```python
# src/seller_console/collectors/mynewstore.py
from .base import BaseCollector, CollectorResult

class MyNewStoreCollector(BaseCollector):
    name = "mynewstore"

    def collect(self, url: str) -> CollectorResult:
        # ... 구현 ...
        return CollectorResult(
            success=True,
            url=url,
            source="mynewstore",
            title="...",
        )
```

2. `dispatcher.py` 의 `DOMAIN_MAP`에 추가:

```python
DOMAIN_MAP = {
    ...
    "mynewstore.com": MyNewStoreCollector,
}
```

3. `__init__.py` 에 import 추가:

```python
from .mynewstore import MyNewStoreCollector
```

4. 테스트 작성: `tests/test_mynewstore_collector.py`

---

## API 의존성

| 수집기 | 필요 패키지 | 없을 때 |
|---|---|---|
| AloCollector, LululemonCollector | `beautifulsoup4` | GenericOgCollector 폴백 |
| AmazonCollector | `AMAZON_*` 환경변수 | OG 폴백 |
| RakutenCollector | `RAKUTEN_APP_ID` 환경변수 | OG 폴백 |
| GenericOgCollector | `requests` | 실패 |
