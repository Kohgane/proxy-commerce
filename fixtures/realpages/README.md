# fixtures/realpages — 실페이지 추출 하네스 픽스처 (v70 STEP5)

라이브 run.js/kgp-extractor.js를 **렌더된 DOM**에 물려 [title·price·images·options·desc]를 스냅샷 비교하는
회귀 하네스의 입력이다. 추출 로직(kgp-extractor.js)을 바꾸면 이 하네스가 통과해야 한다(CLAUDE.md 규약).

## 파일 규약
- `<name>.html` — 페이지 DOM(문서 전체). `<name>.expected.json` — 기대 스냅샷(관대 매처).
- `expected.json` 필드:
  - `url` (필수): 이 픽스처를 물릴 가짜 URL. **호스트가 추출 분기를 결정**(amazon.* → 아마존 갤러리 스코프).
  - `title_contains`, `price`, `currency`, `options`(축→값 배열), `no_option_names`(있으면 안 되는 축),
    `images_min`/`images_max`, `images_exclude_substr`, `description_contains`, `note`.

## 합성 vs 실페이지 (정직)
- `synthetic-*.html` = **구조 재현 합성 픽스처**(실제 캡처 아님 — 정직 표기). 추출기 3버그(가격·옵션·갤러리)를
  실브라우저 DOM에서 end-to-end 검증한다. 가짜 '실페이지'로 위장하지 않는다.
- **실페이지 픽스처**(amazon-dp·temu-detail·yoshida-detail 등)는 오너가 확장 팝업 **"진단 스냅샷 저장"**으로
  1회 저장해 여기에 커밋한다(테무·로그인성 사이트의 렌더된 DOM 공급용). 커밋 즉시 하네스가 자동 포함.

## 실행
- CI/로컬 게이트: `pytest tests/test_v70_realpage_harness.py`(Playwright — 실 크로미움 DOM).
- 오너 로컬(jsdom): `node scripts/extract_harness.js`(jsdom 설치 시).
