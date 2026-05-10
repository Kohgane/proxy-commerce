# MEDIA_PIPELINE.md — 미디어 파이프라인 운영 가이드 (Phase 143)

## 개요

상품 이미지를 자동으로 처리하는 파이프라인입니다.
워터마크 제거, 채널별 리사이즈, WebP 변환을 순서대로 수행합니다.

## 처리 단계

```
[이미지 URL] → [다운로드] → [워터마크 감지] → [Inpainting]
                                                    ↓
                            [채널별 리사이즈/크롭] → [WebP 변환] → [결과 반환]
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `IMAGE_PIPELINE_ENABLED` | `1` | 파이프라인 활성화 |
| `IMAGE_INPAINT_ENABLED` | `1` | 워터마크 inpainting 활성화 |

## 의존성

| 라이브러리 | 용도 | 필수 여부 |
|-----------|------|-----------|
| `opencv-python` | 워터마크 감지 + inpainting | 선택 (없으면 건너뜀) |
| `Pillow` | 리사이즈, 크롭, WebP 변환 | 선택 (없으면 건너뜀) |

> 라이브러리가 없어도 graceful fallback으로 원본 이미지 URL을 반환합니다.

## 워터마크 감지 알고리즘

1. 이미지를 그레이스케일로 변환
2. 임계값(200) 이상 밝은 픽셀 추출
3. 이미지 4개 모서리 20% 영역에서 밝은 픽셀 비율 확인
4. 비율 > 10% 시 워터마크 의심

## Inpainting (OpenCV TELEA)

워터마크 영역(모서리)을 마스크로 지정하고 TELEA 알고리즘으로 복원합니다.

## 채널별 설정

| 채널 | 크롭 비율 | 최소 해상도 | 최대 파일 크기 |
|------|-----------|-------------|----------------|
| 쿠팡 | 1:1 | 800×800 | 5MB |
| 스마트스토어 | 1:1 | 1000×1000 | 10MB |
| 11번가 | 1:1 | 750×750 | 5MB |

## 사용 예시

```python
from src.media.image_pipeline import process_image, process_image_urls

# 단일 이미지
result = process_image("https://example.com/product.jpg", channel="coupang")
print(result.watermark_detected)  # True/False
print(result.webp_converted)      # True/False
print(result.file_size_bytes)     # 처리 후 파일 크기

# 복수 이미지
urls = ["https://example.com/img1.jpg", "https://example.com/img2.jpg"]
processed_urls = process_image_urls(urls, channel="coupang")
```

## 운영 팁

- **프로덕션**: 처리된 이미지를 CDN에 업로드 후 URL을 `processed_url`에 반환하도록 확장 필요
- **WebP**: 처리 후 크기가 원본보다 큰 경우 자동으로 원본 형식 유지
- **인페인팅 OFF**: `IMAGE_INPAINT_ENABLED=0` 으로 비활성화 (처리 속도 향상)
- **통계**: `image_pipeline_stats(results)` 로 배치 처리 결과 통계 확인
