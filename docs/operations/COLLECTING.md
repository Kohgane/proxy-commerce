# COLLECTING.md — 수집 방법 가이드 (Phase 135)

상품을 코가네 퍼센티에 수집하는 4가지 방법.

---

## 방법 1: URL 직접 입력 (단일)

`/seller/collect` 페이지에서 URL 1개 붙여넣기.

1. URL 입력 → **수집하기** 클릭
2. 결과 즉시 표시 (제목, 이미지, 가격, 신뢰도)
3. **저장** 클릭 → 카탈로그 저장

---

## 방법 2: 벌크 URL 수집

`/seller/collect` 탭에서 여러 URL 한 번에.

1. 줄바꿈으로 구분된 URL 목록 붙여넣기 (최대 100개)
2. **벌크 수집 시작** 클릭
3. 진행률 실시간 확인
4. 완료 시 텔레그램 알림 "📦 벌크 수집 완료: 23/30 성공"

API: `POST /api/v1/collect/bulk`

---

## 방법 3: 북마클릿

한 번 설치 후 아무 쇼핑 페이지에서 클릭.

1. `/seller/bookmarklet` 페이지에서 설치
2. 토큰 입력 후 북마클릿 업데이트
3. 북마클릿 버튼을 북마크바로 드래그
4. 쇼핑 페이지에서 북마크 클릭 → 즉시 수집

---

## 방법 4: 크롬 확장 (본 구현)

가장 편리한 방법. 아이콘 클릭 한 번.

1. `chrome://extensions/` → 개발자 모드 → 압축 해제 폴더 로드
2. `/seller/me/tokens`에서 Personal Access Token 발급
3. 확장 옵션 페이지에서 토큰 설정
4. 쇼핑 페이지에서 아이콘 클릭 → **이 상품 수집하기**

자세한 설치 가이드: [CHROME_EXTENSION.md](CHROME_EXTENSION.md)

---

## 범용 수집기 (UniversalScraper) 동작 원리

어댑터가 없는 사이트는 자동으로 범용 수집기 사용:

```
URL 수신
    ↓ robots.txt 준수, User-Agent: KohganePercentiii/1.0
HTML 다운로드 (최대 1MB)
    ↓
1순위: JSON-LD schema.org Product → 신뢰도 0.8~1.0
2순위: Open Graph 메타태그 → 신뢰도 0.6~0.8
3순위: Microdata (schema.org) → 신뢰도 0.5~0.7
4순위: Heuristic (<title>, <h1>, 가격 패턴) → 신뢰도 0.0~0.5
    ↓
신뢰도 ≥ 0.5: 수집 성공
신뢰도 < 0.5: "어댑터 필요" 알림
```

---

## 신뢰도 기준

| 신뢰도 | 의미 |
|---|---|
| 0.8 ~ 1.0 | JSON-LD 완전 수집 (제목+이미지+가격+브랜드) |
| 0.6 ~ 0.8 | OG 메타 수집 (제목+이미지+가격) |
| 0.5 ~ 0.6 | 기본 정보 수집 (제목+이미지 또는 제목+가격) |
| 0.0 ~ 0.5 | 불완전 수집 — 어댑터 개발 권장 |

---

## 어댑터 추가 가이드 (개발자용)

새 쇼핑몰 어댑터 추가 방법:

```python
# src/collectors/adapters/mystore_adapter.py
from .base_adapter import BrandAdapter
from ..universal_scraper import ScrapedProduct, _fetch_html

class MyStoreAdapter(BrandAdapter):
    name = "mystore"
    domain = "mystore.com"

    def fetch(self, url: str) -> ScrapedProduct:
        # 1. DRY_RUN 처리
        if os.getenv("ADAPTER_DRY_RUN") == "1":
            return ScrapedProduct(...)

        # 2. HTML 다운로드
        html = _fetch_html(url)

        # 3. 파싱 (JSON-LD 또는 site-specific CSS selector)
        ...

        return ScrapedProduct(
            source_url=url,
            title=title,
            extraction_method="adapter:mystore",
            confidence=0.9,
        )
```

`src/collectors/dispatcher.py`에 등록:
```python
self.adapters["mystore.com"] = MyStoreAdapter()
```

테스트 작성: `tests/test_mystore_adapter.py`

---

## 현재 지원 어댑터

| 도메인 | 어댑터 | 특이사항 |
|---|---|---|
| aloyoga.com | AloAdapter | JSON-LD 우선 |
| lululemon.com | LululemonAdapter | OG 메타 |
| marketstudio.com | MarketStudioAdapter | JSON-LD + CSS 폴백 |
| pleasuresnow.com | PleasuresAdapter | Shopify /products/*.json API |
| yoshidakaban.com | YoshidaKabanAdapter | 일본어 번역 + 엔화→원화 변환 |
| 그 외 | UniversalScraper | 자동 메타 추출 |

---

## 제약 / robots.txt 준수

- `User-Agent: KohganePercentiii/1.0`
- 타임아웃: `SCRAPER_TIMEOUT_SEC` 환경변수 (기본 15초)
- HTML 최대 1MB
- `ADAPTER_DRY_RUN=1`: 모든 실제 HTTP 요청 차단 (테스트용)
