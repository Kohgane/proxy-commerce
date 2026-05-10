# AUTO_LISTING.md — 상품 등록 자동화 운영 가이드 (Phase 143)

## 개요

승인된 소싱 후보를 쿠팡, 스마트스토어, 11번가에 동시 등록하는 자동화 파이프라인입니다.
부분 실패를 허용하며, 일부 채널에서 오류가 발생해도 성공한 채널의 결과를 반환합니다.

## 아키텍처

```
[Candidate 승인]
      ↓
[_prepare_product_from_candidate]
  ├── translate_title / translate_description (번역)
  └── process_image_urls (이미지 처리)
      ↓
[adapt_for_channel] × N채널
  ├── 카테고리 매핑
  ├── 수수료 반영 가격 조정
  └── 이미지/제목 채널 적응
      ↓
[_upload_to_channel] × N채널 (부분 실패 허용)
      ↓
[결과 반환 + 이력 저장]
```

## 핵심 모듈

| 함수 | 역할 |
|------|------|
| `auto_publish(candidate, channels)` | 채널별 업로드 결과 반환 |
| `adapt_for_channel(product, channel)` | 채널 적응 |
| `listing_stats()` | 등록 이력 통계 |

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LISTING_AUTO_PUBLISH` | `0` | 자동 등록 활성화 (기본 OFF) |
| `LISTING_AUTO_PUBLISH_CHANNELS` | `coupang,smartstore` | 등록 채널 |

⚠️ **자동 등록은 기본 OFF** — 운영 준비 후 `LISTING_AUTO_PUBLISH=1`로 활성화

## 채널별 설정

| 채널 | 제목 최대 길이 | 수수료 | 이미지 최소 해상도 |
|------|----------------|--------|-------------------|
| 쿠팡 | 100자 | 10.8% | 800×800 |
| 스마트스토어 | 100자 | 7% | 1000×1000 |
| 11번가 | 80자 | 9% | 750×750 |

## 카테고리 매핑

`src/listing/auto_publish.py` 의 `_CHANNEL_CATEGORY_MAP` 딕셔너리를 수정하여 카테고리 매핑을 관리합니다.

## 이력 조회

등록 이력은 메모리(`_listing_history`)에 최대 500건 보관됩니다.
```python
from src.listing.auto_publish import get_listing_history
history = get_listing_history()
```

## 드라이런 모드

`LISTING_AUTO_PUBLISH=0` (기본값) 시 드라이런 모드로 동작:
- 실제 채널 업로드 없이 준비 결과만 반환
- `listing_id`에 `dry-run-` 접두사 포함

## 운영 팁

- **부분 실패**: 채널 중 하나가 실패해도 다른 채널은 계속 진행
- **스마트스토어/11번가**: 현재 stub 구현. 실제 운영 시 API 키 연동 필요
- **가격 조정**: 수수료 반영 후 100원 단위 올림 처리
- **이미지**: `processed_image_urls` 우선 사용 (워터마크 제거 완료 이미지)
