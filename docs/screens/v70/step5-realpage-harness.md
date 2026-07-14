# v70 STEP5 — 실페이지 하네스 CI 상설화

## 목표
- 추출 로직(kgp-extractor.js)을 바꾸면 회귀를 즉시 잡는 **실페이지 스냅샷 하네스**를 상설화.

## 구성
1. **하네스 게이트** `tests/test_v70_realpage_harness.py` (Playwright · 실 크로미움 DOM):
   - `fixtures/realpages/<name>.html`에 라이브 `kgp-extractor.js`(=run.js 코어)를 물려 `kgpExtractProduct()` 실행 → `<name>.expected.json` 스냅샷과 [title·price·currency·options·images·desc] 비교.
   - `page.route`로 가짜 URL을 픽스처로 채워 **호스트가 추출 분기 결정**(amazon.* → 갤러리 스코프). 네트워크 없이 렌더된 DOM.
2. **오너 로컬 러너** `scripts/extract_harness.js` (jsdom): 오너 채팅 하네스와 동형. jsdom 미설치 시 정직 안내(가짜 통과 0).
3. **진단 스냅샷 저장 버튼**(확장 팝업): 현재 렌더된 페이지 DOM(`outerHTML`)을 파일로 내려받아 `fixtures/realpages/`에 커밋 → 테무·로그인성 사이트의 렌더 DOM 픽스처 공급.
4. **CLAUDE.md 규약**: "추출 로직 변경 시 실페이지 하네스 통과 필수 · 픽스처 없는 추출 변경 금지".

## 픽스처 (정직: 합성 vs 실페이지)
- 현재 커밋: `synthetic-amazon-dp`(buybox 29.99 vs 광고 32.99 · 색상 트위스터 4 · 수량 셀렉트 · altImages 5 · 관련상품 2 · feature-bullets) + `synthetic-generic-detail`(비아마존 JSON-LD Product). **구조 재현 합성 — 실제 캡처 아님(정직 표기)**. 추출기 3버그(가격·옵션·갤러리)를 실 브라우저 DOM에서 end-to-end 검증.
- 실페이지 픽스처(amazon-dp·temu-detail·yoshida-detail 등)는 **오너가 스냅샷 버튼으로 1회 저장해 커밋**하면 하네스가 자동 포함.

## 판정
- `tests/test_v70_realpage_harness.py`:
  - `test_realpage_snapshot[synthetic-amazon-dp]`: 실 크로미움에서 **price=29.99·currency=USD**(광고 32.99 무시) · **옵션 색상 4값·수량 미수집** · **이미지 5장(관련상품 REL·sprite 혼입 0)** · 상세 '무선 충전' → 그린.
  - `test_realpage_snapshot[synthetic-generic-detail]`: 제네릭 JSON-LD 경로 그린(회귀 0).
  - `test_snapshot_infra_source_contract`: 스냅샷 핸들러·팝업 버튼·스크립트·픽스처·CLAUDE.md 규약·manifest 1.5.80.
- 부수 수리: 아마존 갤러리 크기 필터를 **로드된 naturalWidth만**으로(깨진/미로드 이미지 layout width=16 오판 방지 — 미로드 스프라이트는 파일명 NONPROD_IMG로 배제). 전체 그린.
- **CI 로그(오너 몫)**: CD `pytest -q`(main)에서 하네스 그린. PR CI는 `--collect-only`라 하네스 수집만(실행은 로컬/CD).

## 금지 준수
- 픽스처 없는 추출 변경 0(규약) · 합성 픽스처를 실페이지로 위장 0(정직 표기) · 서버측 직접 크롤 0(렌더 DOM).

적용 스킬: (하네스·확장 — UI는 팝업 버튼 1개(토큰 유지). impeccable/humanizer CLI 미설치.)
