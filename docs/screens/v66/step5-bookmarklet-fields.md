# v66 STEP5 — 북마클릿 옵션·상세 (run.js 보강)

## 감사 결과 (이미 충족 — v62 단일 모듈)
- `/seller/bookmarklet/run.js` = `_bookmarklet_run_js()` = **공유 추출기 전체(`kgp-extractor.js`) + `__kgpRun` 래퍼**.
- 즉 북마클릿(run.js 채택 시)은 확장 콘텐츠 스크립트와 **바이트 동일한** 추출 코어를 사용 → 옵션·상세·가격·이미지 추출이 STEP2·3과 **동일 코어** 공유(v62 STEP1 단일 모듈 원칙).
- 포함 확인:
  - **옵션**: `_domOptions`(스와치·select·트위스터).
  - **상세**: `_domDescription` + `#feature-bullets`·`#productDescription`·`#aplus img`.
  - **가격**: v66 STEP2 `_composedPrice`(합성 텍스트).
  - **아마존 hi-res**: `data-old-hires`·`hiRes()`.
- 래퍼는 `html`·`ext_version`만 얹고 추출은 코어가 — run.js에 토큰·서버 URL 노출 0(전송은 코어가 토큰으로).

→ **미포함 없음** — 이미 포함. 이 STEP은 단일 모듈 원칙을 회귀 자물쇠로 고정(재작업 불필요).

## 판정
- 가드 `tests/test_v66_bookmarklet_fields.py` (3):
  - run.js가 공유 추출기 전체 포함(`core == kgp-extractor.js` 바이트 동일) + `__kgpRun` 래퍼.
  - 옵션(`_domOptions`)·상세(`_domDescription`·feature-bullets·productDescription)·합성가격(`_composedPrice`)·아마존 hi-res(`data-old-hires`·`#aplus img`) 포함.
  - 래퍼가 html·버전만 얹음·토큰/Bearer 미노출.
- 실기기(북마클릿으로 아마존 1건 수집 → 옵션·상세 채움)는 오너 환경 — 프록시 라이브 차단.

## 금지 준수
- 경로별 추출기 중복 구현 0(run.js=확장 코어 바이트 동일) · 자격증명 평문 0(run.js에 토큰 없음).

적용 스킬: (백엔드 번들 감사 — 우리 토큰 무관. impeccable/humanizer CLI 미설치.)
