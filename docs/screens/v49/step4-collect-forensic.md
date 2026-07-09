# v49 STEP4 — 필드 수집 포렌식 + 서버 초기상태 JSON 파서

## 분기 확정 (어디서 깨지나)
북마클릿은 렌더된 페이지 **outerHTML(최대 90만자)을 이미 서버로 전송** 중이었다. 4지점 중:
- 클라 미추출 / 전송 누락 → 아님(북마클릿은 html 통째 전송).
- **서버가 html을 받고도 초기상태 JSON을 파싱 안 함 → 유력·확정.** 서버는 DOM/OG만 봐서 Temu가 인라인
  `<script>window.rawData={...}</script>`에 심은 sku 가격·갤러리·옵션·리뷰를 못 읽었다.
- 저장 매핑 누락 → 아님(있는 값은 저장됨).

## 수리
- **서버 파서** `src/collectors/state_json.py`: 확장 JS 추출기(kgp-extractor.js)의 초기상태 파서를 **파이썬
  동형 이식**. 수신 HTML 텍스트에서 상태 JSON을 균형 매칭으로 꺼내(`window.rawData`·`__NEXT_DATA__` 등)
  키 이름 휴리스틱으로 **sku 가격(센트 환산)·갤러리 전체·옵션 sku·상세 이미지·평점·리뷰** 매핑.
  사이트 스키마 하드코딩 없음. **추가 API 호출 없음**(텍스트 파싱만).
- **확장·북마클릿 통일**: collect API가 `html` 수신 시 이 서버 파서를 **먼저** 경유(빈 필드만 보강, 클라 값
  우선) → DOM/OG(UniversalScraper)는 그 다음 폴백. 클라별 파서 중복 없음.
- **가격 sanity**: KRW<100 등 → `needs_check`(재고·리뷰 숫자 오인 저장 거부). 기존 게이트 유지.
- 실패 필드는 STEP2/STEP5 "부분 수집" 배지에 필드명 명시.

## 포렌식 로그 (4단 추적)
- **클라 콘솔(전송 직전)**: 확장·북마클릿 모두 `[고가수집기] 전송요약 {price, currency, images, desc, ...}`.
- **서버 수신 요약**: `[collect ...] 수신요약 price=.. images=N desc=N자 html=N자 options=N reviews=N`.
- **서버 파싱 로그**: `초기상태 JSON 파싱: price=.. images=N options=N detail=N reviews=N rating=..`.
- **DB 저장값** → **드로어 렌더**. corr-id로 4단 일치 확인.

## 로컬 실증 (Temu 형태 html → 서버 파싱 → DB)
mock `window.rawData`(skuList salePrice 20605 KRW·갤러리 3·옵션 블랙/화이트·avgRating 4.7·reviewCount 328·
리뷰 2건) 를 `/api/v1/collect/extension`에 html로 전송 →
**DB: price=20605 KRW · images=3 · options=[블랙,화이트] · rating=4.7 · review_count=328**. USD 센트 환산(1299→12.99)도 검증.

## 판정 (오너 실기기)
Temu 실URL 1건: [클라 콘솔 요약 → 서버 수신·파싱 로그 → DB 저장값 → 드로어 5탭] 4단 일치 캡처, 가격 20,605.
(확장은 1.5.49 재로딩.)

## 가드
test_v49_collect_forensic(6): 파서(가격/센트/갤러리/옵션/평점/리뷰·빈상태) + html E2E→DB + 가격 sanity +
소스 계약(수신·파싱·전송 요약·통일·무 API). manifest 1.5.48→1.5.49.
