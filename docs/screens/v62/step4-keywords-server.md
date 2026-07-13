# v62 STEP4 — 키워드 서버 생성으로 이관

## 수리
- 신규 `src/seller_console/keyword_gen.py`:
  - `generate_keywords(title, category, options, desc_text, brand)` — 규칙 기반. 우선순위:
    **브랜드 → 제목 핵심 명사구(모델·용도) → 카테고리 라벨 → 옵션명 → 상세 빈출어(2회+)**.
  - 필터: 마케팅 수식어·일반어 불용어(best·premium·무료·배송·특가…) + **오염어**(chat/history/고가수집기/
    도메인/사이드패널 — 토큰 단위까지). 중복 제거, 8~15개.
  - `refine_keywords`: OPENAI 가용 시 문맥 정제(미가용/실패 시 그대로 — 가짜 생성 0).
- 확장 수집(`extension_api`): 저장 시 서버가 `_extra.keywords`/`tags` 생성(클라 추출 폐지).
- 드로어 키워드 탭: `_EXTRA.keywords` 태그칩 렌더 + 편집 가능(기존).

## 실증
- 제목 "andobil … Grip … Chat history" + 옵션 색상/사이즈 + 상세 빈출어 →
  키워드 [andobil, Magnetic, Grip, …, 그립, 거치대] · **오염어(Chat/history/고가수집기) 0**.
- 불용어(best/premium/무료/배송/특가) 필터.
- E2E: 확장 collect payload → 서버 생성 keywords 저장(오염어 0) 확인.

## 판정 (배포 후 실기기 — 오너)
수집 직후 키워드 탭에 유효 키워드 8~15개(오염어 0) 캡처.

가드 test_v62_keyword_server(5). (서버만 — 확장 무변경.)
