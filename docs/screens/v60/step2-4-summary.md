# v60 STEP2-4 — 상세설명 + 번역 품질 + AI 초안 키워드

## STEP2 — 상세설명 수집 (구조화)
- **근원 수리**: `_domDescription`이 needDom 게이트 안에서만 실행 → Tier1이 가격·이미지를 채우면(needDom=false)
  상세설명이 영영 비었음(아마존 About this item 미수집 근원). → **가격/이미지와 독립 수집**(있으면 채움).
- 아마존 About this item(`#feature-bullets`) 불릿을 `·` 구조화 텍스트 + `#productDescription` 본문.
- 출력에 `desc_text`(=description)·`desc_images`(=detail_images) 명시 분리(브리프 명명). 드로어 상세 탭이 둘 다 렌더(기존).
- 실증(real Chromium): JSON-LD full(price+images)인데도 desc_text에 "Ultra-Thin·MagSafe" 불릿 수집.

## STEP3 — 번역 품질 (직역투 박멸)
- **현 경로 감사**: OpenAI chat completions(모델 `OPENAI_MODEL`, 기본 gpt-4o-mini) → 실패 시 DeepL → stub(원문 보존).
  구 프롬프트 = 범용 "한국어로 번역" 1줄 → 직역투·음차 유발.
- **재작성**(system 프롬프트 신설): ①브랜드명·모델명·규격(MagSafe·iPhone 15 등) 원문 보존, 억지 음차·직역 금지
  ②마케팅 수식어 자연 판매 문체(ultra-thin→초슬림) ③단위 변환 금지·없는 스펙 창작 금지 ④상품명=브랜드+핵심스펙+용도
  ⑤설명 불릿 유지. temperature 0.2.
- 드로어 원문 병기(title_en 원문 토글, v39 D)로 검수 가능.

## STEP4 — AI 초안 키워드 재설계
- 오염어 차단(STEP1 스코프 공유): `_is_contaminated` — Chat history·고가수집기·kgp·사이드패널·도메인(.com/http)·
  '번역까지 한 번에' 등 확장 UI/페이지 크롬 텍스트를 키워드·제목에서 배제.
- 초안 구조 고정: 상품명 → **후킹 1줄** → (브랜드·카테고리) → ■ 특징(실 키워드) → ■ 옵션·상세 → **■ 배송·구매대행 안내**.
  허위 스펙 창작 금지 유지(확인된 정보만).
- 실증: 키워드 [MagSafe 호환·Chat history·360도 회전·고가수집기] → 초안에 오염어 0, 실 키워드만.

manifest 1.5.59→1.5.60. 가드 test_v60_desc_translate_draft(4) + test_v56_ai_draft 갱신.
