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

## 대형 통일 (오너 확정 — 512 공식 마크로 파생)
오너 지시 "대형통일" → 대형 아이콘(180/192/512/1024·apple-touch·OG·확장128)을 코드 마스터 대신
**오너 공식 `master-512.png`**(md5 `70cbdee83a618e676caa82ec632fcd43`, 512×512 RGBA)에서 파생:
- `_large_master()`: master-512.png 있으면 대형 소스로(1024=업스케일·그 외=다운스케일), 없으면 코드 마스터 폴백.
- OG 카드(`gen_og_card.py`)가 `icon-master-1024.png`(=오너 512 업스케일)를 소스로 재생성 → OG도 공식 마크.
- 캐시버스트 og `?v=5 → v=6`(OG 디자인 변경 강제 갱신).
- 오너 아트 특성: 보더 바깥 **투명**(alpha 0), 내부 흰 배경.

**결과: favicon(소형)과 앱아이콘·OG(대형)가 동일 디자인으로 통일** — 캡처 `step1b-large-master-crosscheck.png`
(BEFORE: 코드 링아치 vs 정답지 열린아치 불일치) → 통일 후 favicon-48 ≡ icon-512 동일 마크.

## 오너 액션
- 배포 후: `python scripts/compare_favicon.py --live https://kohganepercentiii.com/seller/static/favicon-48.png?v=182` → 라이브 픽셀 동일 확인.
