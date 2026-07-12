# v57 STEP1b — 파비콘 소사이즈 정답지 확정 (오너 원본 커밋)

## 정답지 수령·검증
- 오너가 `assets/brand-icons/icon-bridge-v2-48.png` 업로드(커밋 8d56ca1) → `favicon-master-48.png`로 rename(git mv).
- **md5 = `98b537dd451b2a28e1d8e397dcc6597c`** (48×48, RGBA, 3056 bytes) — 검증 통과 ✓.
  (앞서 base64 채팅 전송본은 IDAT 손상으로 불합격 → 파일 업로드로 무결하게 수령.)

## 파이프라인 (build_icons.deploy)
- **favicon-48 = 정답지 픽셀 그대로**(48→48 리샘플 0, RGBA 보존) → 픽셀 동일 보장.
- favicon-16/32·favicon.ico(48레이어)·확장 16/32/48 = 정답지 다운스케일(16 = 정답지 다운스케일).
- 대형(180/192/512/1024·apple-touch·OG·확장 128) = 기존 1024 코드 마스터 유지.

## 픽셀 대조 판정 (scripts/compare_favicon.py)
```
favicon-48 vs favicon-master-48
크기동일=True  md5(A)=9455967894914f6f26ef89d2bbc8b42b  md5(B)=9455967894914f6f26ef89d2bbc8b42b
다른 픽셀=0/2304 (0.00%)  최대채널차=0/1020
판정: 픽셀 동일 ✓ 합격
```
캡처: `step1b-favicon-answer-key.png`(favicon 16/32/48 native + 확대).

## ⚠️ 대형 마스터 디자인 대조 (오너 요청 기록)
`icon-bridge-v2-512`(오너 공식 대형) vs 현행 1024 코드 마스터(`icon-512.png`) — **디자인 불일치**:
| | 512 정답지 | 1024 코드 마스터 |
|---|---|---|
| 아치 | 열린 게이트 아치(inverted-U) | 거의 완전한 링(원) |
| 케이블 | 타워→측면 사이드스팬(깔끔) | 중앙 깊은 해먹 처짐 |
| 수면 라인 | 없음 | 데크 아래 청록 2줄 |

지시대로 대형은 1024 마스터 유지. 캡처: `step1b-large-master-crosscheck.png`.
→ **권고**: 브랜드 일관성을 위해 대형도 오너 공식 512에서 파생하도록 통일 가능(오너 확인 시 1커밋). 현재는 미적용(지시 준수).

## 오너 액션
- 배포 후: `python scripts/compare_favicon.py --live https://kohganepercentiii.com/seller/static/favicon-48.png?v=182` → 라이브 픽셀 동일 확인.
