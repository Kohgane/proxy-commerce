# v71 STEP3 — 상세이미지 접힘 펼침 (버그③ 상세이미지 0)

## 증상 (오너 스냅샷 실측)
- 상세이미지 0 — 접힘 뒤 콘텐츠(펼침 전엔 DOM에 미주입). 경고는 정상 출력.

## 수리 (`kgp-extractor.js`)
1. **tier1 상세 갤러리 우선**: 상태 JSON에 상세 이미지 리스트(`DET_KEY`: detail·desc·decoration·bottomimage·richtext·longimage·goodsdesc)가 있으면 그대로 detailImages로(펼침 불요) — v57 유지.
2. **펼침 라벨 보강** `FOLD_RE`: 테무·CJK(`상품상세`·`상세정보`·`全部`·`查看更多`·`展开`·`もっと見る`·`続きを読む`·`view all`·`product details`).
3. **이미지/div 기반 펼침** `_foldButtons`: button/a 외 `[class*="expand"]`·`[class*="viewmore"]`·`[class*="unfold"]`·`[class*="showmore"]`도 후보(테무는 button 아님).
4. **상세 컨테이너 스코프 보강** `_domImages` dSel + reveal scope: `goods-desc`·`decoration`·`richtext`·`longimage`·`productDesc` 추가.
5. **보강 창 흐름**(v67 extractMetaWait): 자동 스크롤(lazy) → 인터스티셜 닫기 → `kgpRevealDetailFolds`(더보기 클릭·최대 3섹션 + MutationObserver로 새 이미지 mount 대기, 최대 3초) → 렌더 추출. 실패 시 현행 정직 경고 유지("상세이미지 일부만").

## 판정
- 가드 `tests/test_v71_fold_expand.py` (3):
  - 소스계약(CJK 라벨·상세 컨테이너·이미지 펼침 후보·DET_KEY 우선).
  - **node로 `FOLD_RE`**: 상품상세/查看更多/もっと見る/view all 매칭 · 장바구니/구매/리뷰/배송 비매칭.
  - **Playwright 실브라우저**: 접힘 상세(더보기 클릭 시 상세이미지 6장 DOM 주입) → `kgpRevealDetailFolds` 후 **detail_images 0→6(≥5)**.
- manifest 1.5.84. `test_v57_temu_images`·실페이지 하네스 그린.
- **실기기(오너 몫)**: 테무 1건 보강 후 드로어 상세이미지 ≥5 캡처. (개발 프록시 라이브 테무 차단.)

## 금지 준수
- 펼침 실패 시 정직 경고 유지(무음 실패 0) · 서버측 직접 크롤 0(보강 창 DOM) · 가짜 성공 0.

적용 스킬: (확장 추출 로직 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
