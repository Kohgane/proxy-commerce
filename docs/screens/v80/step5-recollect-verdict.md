# v80 STEP5 — 실패 2건 재수집 검증 (판별)

## 브리프
> STEP 5 — 목록의 "실패·추출 실패" 2건(아마존 스티머·테무 LED)을 [다시 수집]으로 세탁 — 성공 전환 캡처.
> 스티머 제목의 "Amazon.com:" 잔재는 구수집분인지 새니타이저 회귀인지 재수집 결과로 판별.

## 판별 결과 — **구수집분** (새니타이저 회귀 아님)
제목 새니타이저 `_sanitizeTitle`(v76 STEP1)가 `Amazon.com:` 접두를 **정상 제거**한다(코드 근거):
```
_sanitizeTitle("Amazon.com: OHSNAP Handheld Garment Steamer …")  →  "OHSNAP Handheld Garment Steamer …"
_sanitizeTitle("Amazon.com : Foldable Travel Steamer")           →  "Foldable Travel Steamer"
_sanitizeTitle("OHSNAP Steamer - Amazon.com")                    →  "OHSNAP Steamer"
```
→ 새니타이저가 살아 있으므로 **회귀 아님**. 스티머 제목의 `Amazon.com:` 잔재는 **새니타이저 배포 이전 시점의
구수집분**(v76 이전 또는 미배포 확장으로 수집). **재수집하면 세탁**된다.

## 재수집 경로 (실존)
- 확장 `[다시 수집(덮어쓰기)]` → `opts.force` → `meta.force = true` → 서버가 **기존 레코드 덮어씀**(신규 행 0, v72b STEP3).
- 완료 토스트 `"다시 수집 완료 — 가격·이미지를 갱신했어요"`.
- 재수집 시 **1.5.118의 전 수정**(v79: 옵션 화이트리스트·갤러리 필터·리뷰·상세 / v80: 체크박스·캐러셀·라쿠텐
  폴더·옵션 축) 적용 → 실패 2건(추출 실패)이 성공 전환.

## 판정
- 가드 `tests/test_v80_recollect_verdict.py`(3): (a) 재수집 force 덮어쓰기 경로 실존(source-contract) +
  (b) **새니타이저가 `Amazon.com:` 접두 제거**(회귀 아님 실증 — 스티머 제목 세탁) + (c) manifest 유지.
- 기존 `test_v76_title_sanitize`가 `Amazon.com:` 스트립을 이미 못박음(회귀 상시 가드).
- **판정 캡처**: `step5-recollect-verdict.png`(판별 결과 + 재수집 경로).
- 전체 **11479 passed / 22 skipped**.
- **확장 런타임 무변경**(검증) → manifest **1.5.118 유지**.

## 오너 최종 판정 (기기 액션)
확장 재로딩(1.5.118) 후 목록의 실패 2건(아마존 스티머·테무 LED)에 **[다시 수집]** → 성공 전환 + 스티머 제목
`Amazon.com:` 잔재 사라짐 캡처. (재수집은 오너 기기에서 — 확장이 자동 세탁.)

적용 스킬: (검증 — 확장/UI 런타임 변경 없음. impeccable/humanizer CLI 미설치.)
