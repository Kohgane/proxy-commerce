<<<<<<< copilot/fix-phase-151-analysis-cache
# AI 상품등록 자동화 가이드 (Phase 151.1)
=======
# AI 상품등록 자동화 가이드 (Phase 151)
>>>>>>> main

## 개요

Phase 149에서 추가된 AI 상품등록 자동화 기능은 이미지 1~5장을 업로드하면 AI가 자동으로 상품 정보를 추출하고, 여러 마켓에 동시에 등록해주는 기능입니다.

Phase 151.1에서 **캐시 키 정상화**가 적용되었습니다: Phase 번호와 prompt_version을 캐시 키에 포함하여 Phase 업그레이드 시 자동으로 새 결과를 생성합니다.

## 핵심 플로우

```
이미지 업로드 (1~5장)
        ↓
Vision API 분석 (GPT-4o-mini / Claude Sonnet / mock)
        ↓
카테고리 / 브랜드 / 색상 / 소재 / 키워드 추출
        ↓
마켓별 제목 / 설명 / 카테고리 / 가격 / 태그 생성
        ↓
사용자 검토 & 인라인 편집
        ↓
선택한 마켓에 동시 등록 (coupang / smartstore / 11st / gmarket)
        ↓
등록 결과 카드 표시 (성공 / 실패 + 재시도)
```

## 진입점

- **UI**: `/seller/listing/ai-create`
- **사이드바**: 🤖 AI 상품등록 (카탈로그 그룹)

## 환경변수

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `AI_LISTING_ENABLED` | `1` | 기능 활성화 (0=비활성) |
| `AI_LISTING_VISION_PROVIDER` | `mock` | Vision 제공자: `openai` \| `claude` \| `mock` |
| `AI_LISTING_VISION_MODEL` | `gpt-4o-mini` | OpenAI Vision 모델 |
| `AI_LISTING_CLAUDE_MODEL` | `claude-3-5-sonnet-20241022` | Claude 모델 (claude 제공자 시) |
| `AI_LISTING_MAX_IMAGES_PER_REQUEST` | `5` | 요청당 최대 이미지 수 |
| `AI_LISTING_MAX_DAILY_PER_USER` | `50` | 사용자별 일일 최대 생성 건수 |
| `AI_LISTING_CACHE_TTL_HOURS` | `24` | 이미지 분석 캐시 TTL (시간) |
| `AI_LISTING_MARKETS_DEFAULT` | `coupang,smartstore` | 기본 등록 마켓 |
| `AI_LISTING_LANG_DEFAULT` | `kr` | 기본 생성 언어 (`kr` \| `jp` \| `both`) |
| `AI_LISTING_PRICE_MODE` | `auto` | 가격 모드 (`auto` \| `manual`) |
| `AI_LISTING_URL_HEAD_CHECK` | `1` | 상품 URL 입력 시 HEAD 200 검증 |
| `AI_LISTING_URL_HEAD_CHECK_GET_FALLBACK` | `0` | HEAD 403/405 시 GET fallback 허용 |
| `AI_LISTING_FORCE_REFRESH_ALLOWED` | `1` | 다시 분석 시 캐시 무시 허용 |
| `AI_LISTING_DEBUG_PANEL` | `1` | 결과 카드 원본 데이터 패널 표시 |
| `AI_LISTING_PROMPT_VERSION` | `v2_explicit_fields` | 분석 프롬프트 버전 (기본 v2 강제) |
<<<<<<< copilot/fix-phase-151-analysis-cache
| `AI_LISTING_CACHE_INCLUDE_PHASE` | `1` | 캐시 키에 Phase 번호 포함 (Phase 151.1, 코드 레벨 강제 적용) |
| `AI_LISTING_CACHE_INCLUDE_PROMPT_VERSION` | `1` | 캐시 키에 prompt_version 포함 (Phase 151.1, 코드 레벨 강제 적용) |
| `AI_LISTING_FORCE_REFRESH_INVALIDATE_ANALYSIS` | `1` | force_refresh 시 analysis 캐시도 함께 무효화 (Phase 151.1) |
=======
| `AI_LISTING_JSONLD_PRIORITY` | `1` | JSON-LD 명시값(name/brand/price/variants/description) 우선 사용 |
| `AI_LISTING_VARIANT_AUTO_EXTRACT` | `1` | JSON-LD `hasVariant` 자동 분리 |
| `AI_LISTING_PRICE_USE_JSONLD` | `1` | JSON-LD 가격을 환율 변환 가격의 기준값으로 사용 |
| `AI_LISTING_TRANSLATE_DESCRIPTION` | `1` | 원문 설명 한국어 번역 시도 |
| `FALLBACK_USD_KRW` | `1375` | USD 환율 fallback |
| `FALLBACK_JPY_KRW` | `9.2` | JPY 환율 fallback |
| `FALLBACK_EUR_KRW` | `1500` | EUR 환율 fallback |
| `FALLBACK_CNY_KRW` | `190` | CNY 환율 fallback |
>>>>>>> main

## Vision 제공자 설정

### OpenAI (gpt-4o-mini)

```env
AI_LISTING_VISION_PROVIDER=openai
AI_LISTING_VISION_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

### Claude Sonnet

```env
AI_LISTING_VISION_PROVIDER=claude
AI_LISTING_CLAUDE_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=sk-ant-...
```

### Mock (API 키 없음 / 개발용)

```env
AI_LISTING_VISION_PROVIDER=mock
# OPENAI_API_KEY 미설정 시 자동으로 mock 동작
```

## API 레퍼런스

### POST `/api/ai-listing/analyze`

이미지 URL을 받아 Vision AI 분석 결과를 반환합니다.

**Request:**
```json
{
  "image_url": "https://example.com/product.jpg",
  "language": "kr",
  "markets": ["coupang", "smartstore"]
}
```

**Response:**
```json
{
  "ok": true,
  "listing_id": "uuid-...",
  "analysis": {
    "category": "패션",
    "brand": null,
    "colors": ["화이트", "블랙"],
    "materials": ["면"],
    "keywords": ["티셔츠", "기본", "데일리"],
    "estimated_price_range": {"min": 15000, "max": 45000},
    "product_type": "티셔츠",
    "features": ["기본 라운드넥", "루즈핏"]
  }
}
```

### POST `/api/ai-listing/generate`

분석 결과를 바탕으로 마켓별 제목/설명/태그/가격을 생성합니다.

**Request:**
```json
{
  "listing_id": "uuid-...",
  "analysis": { ... },
  "markets": ["coupang", "smartstore"],
  "language": "kr",
  "price_mode": "auto"
}
```

**Response:**
```json
{
  "ok": true,
  "markets": {
    "coupang": {
      "title": "기본 티셔츠 화이트/블랙 루즈핏",
      "description": "✨ 티셔츠\n소재: 면\n✔ 기본 라운드넥",
      "tags": ["티셔츠", "기본", "데일리", "루즈핏", "캐주얼"],
      "category_code": "56139",
      "suggested_price_krw": 29000,
      "margin_pct": 22.0,
      "fee_rate": 0.108
    }
  }
}
```

### POST `/api/ai-listing/publish`

여러 마켓에 동시 등록합니다. 부분 성공 허용.

**Request:**
```json
{
  "listing_id": "uuid-...",
  "markets": ["coupang", "smartstore"],
  "market_data": {
    "coupang": {"title": "최종 제목", "price_krw": 29000},
    "smartstore": {"title": "최종 제목 NS", "price_krw": 28000}
  },
  "analysis": { ... }
}
```

**Response:**
```json
{
  "ok": true,
  "results": {
    "ai_listing_id": "uuid-...",
    "success_count": 2,
    "failed_count": 0,
    "partial_success": false,
    "markets": [
      {"market": "coupang", "status": "success", "external_product_id": "MOCK-COUPANG-abc12345"},
      {"market": "smartstore", "status": "success", "external_product_id": "MOCK-SMARTSTORE-def67890"}
    ]
  }
}
```

## 비용 관리

- **BudgetGuard 연동**: `src/ai/budget.py`의 `BudgetGuard` 사용. 월 예산 초과 시 Vision API 차단 후 mock 결과 반환.
- **캐시**: 동일 이미지 해시(SHA-256) 기준 24h 캐시. 동일 이미지 재분석 비용 없음.
- **일일 한도**: 사용자별 50건/일 (AI_LISTING_MAX_DAILY_PER_USER).

## 비용 예시 (참고)

| 제공자 | 모델 | 이미지 1장 추정 |
|--------|------|----------------|
| OpenAI | gpt-4o-mini | ~$0.001 |
| Anthropic | claude-3-5-sonnet | ~$0.003 |
| mock | - | $0 |

## 마켓별 제목 글자수 제한

| 마켓 | 최대 글자수 |
|------|------------|
| 쿠팡 | 50자 |
| 스마트스토어 | 100자 |
| 11번가 | 100자 |
| G마켓 | 80자 |

## 금칙어 필터

각 마켓의 운영정책에 따른 금칙어 자동 제거:

- **쿠팡**: 최저가, 100%, 무조건, 보장
- **스마트스토어**: 최저가, 최고, 1위, 보장
- **11번가**: 최저가, 보장, 무조건
- **G마켓**: 최저가, 100%

## Admin 진단 카드

`/admin/diagnostics` → **🤖 AI 상품등록 (Phase 동적 검증)** 섹션:
- 활성화 여부
- 24h 분석 시도/스크래퍼 호출률/HTTP200 성공률
- JSON-LD/OG 추출률, 평균 추출 필드 수(10개)
- 캐시 적중률, 프롬프트 버전 분포(v1/v2)
- **Phase 151.1 추가**: 캐시 키 정상화 여부 (phase 포함 ✅/❌, prompt_version 포함 ✅/❌)
- **Phase 151.1 추가**: Phase 하드코딩 가드 상태 (검출 건수)
- **Phase 151.1 추가**: 🗑️ AI listing 캐시 전체 삭제 버튼 (POST /admin/diagnostics/ai-cache-clear)

## Phase 151 — JSON-LD 우선순위

- 제목: `json_ld_normalized.name` → `og:title` → AI fallback
- 브랜드: `json_ld_normalized.brand.name` 우선
- 가격: `offers.price`/`hasVariant[].offers.price`를 환율 모듈로 KRW 변환
- 변형: `hasVariant`에서 색상/사이즈/SKU/GTIN 자동 분리
- 설명: JSON-LD 원문 + 한국어 번역 동시 표시

## Phase 151 — 결과 카드

- 원본가(통화) / 환산가(KRW) / 적용 환율 노출
- 색상/사이즈 칩 + SKU/GTIN 테이블 노출
- 신뢰도 배지: JSON-LD / AI 추론 / 빈 값 구분

## 아키텍처

```
src/ai_listing/
├── __init__.py           패키지 메타
├── analyzer.py           Vision API 분석 + 캐시
├── generator.py          제목/설명/태그 생성
├── category_mapper.py    마켓별 카테고리 코드 매핑
├── price_suggester.py    가격 제안 (Phase 140 연동)
├── multi_publisher.py    멀티마켓 동시 등록 (ThreadPoolExecutor)
├── templates_prompts.py  프롬프트 템플릿
└── routes.py             Flask Blueprint
```

## Phase 150.1 Hotfix

- URL 입력 시 HEAD 200 검증 실패를 사용자에게 즉시 경고
- "🔄 다시 분석 (캐시 무시)" 버튼으로 `force_refresh=1` 강제 재분석
- 분석 카드에 신뢰도 배지(스크래핑 성공/AI 추론/빈 값) 노출
- "📋 원본 데이터" 디버그 패널(HTTP 상태, 응답 크기, JSON-LD, OG, prompt_version, cache hit/miss)
