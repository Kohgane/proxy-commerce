# KEYWORD_TRENDS.md — 키워드/검색어 트렌드 운영 가이드 (Phase 160)

## 개요

`/seller/keywords`는 키워드 검색량/경쟁도/경쟁상품수/추정 CPC/추세를
**실시간 · 일 · 주 · 월 · 년** 기준으로 보여주는 트렌드 대시보드입니다.

- 데이터 소스: `src.ads.keyword_optimizer.get_keyword_metrics()`
- 공급자: `KEYWORD_OPT_PROVIDER=mock|naver_searchad|coupang_ads`
- 공급자/키 미설정 시: mock 시계열 fallback (레이아웃 유지)

---

## 화면 구성

1. 키워드 검색 입력
2. 기간 토글 (실시간/일/주/월/년)
3. 메인 테이블
   - 검색량(기간 환산)
   - 경쟁도
   - 경쟁상품수(추정)
   - 추정 CPC
   - 전기간 대비 추세(%)
   - 미니 인라인 바 차트
4. 급상승(라이저) / 연관 / 롱테일 추천

---

## 액션 연결

- `이 키워드로 소싱` → `/seller/sourcing?keyword=<kw>`
- 키워드 상세 재분석 → `/seller/keywords?q=<kw>&period=<period>`

---

## 운영 포인트

- 네이버 검색광고 키가 없으면 자동으로 mock fallback 됩니다.
- API/키 미설정 상태에서도 표/카드가 비지 않고 placeholder를 유지합니다.
- 차트 라이브러리는 사용하지 않고 CSS 인라인 막대로 렌더링합니다.
