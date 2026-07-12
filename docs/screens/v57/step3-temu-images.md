# v57 STEP3 — 테무 상세이미지 전량 ('더보기' 접힘 대응)

## Tier1 (MAIN world 캡처 API JSON) 재확인·보강
- 상세이미지 키 라우팅 보강: `DET_KEY = /(detail|desc|content|decoration|bottomimage|richtext|longimage|goodsdesc)/i`
  → 테무 접힘 상세(decorationImages·bottomImages·richText 등)도 detail 버킷으로. API JSON은 접힘과 무관하게
  전체 URL을 담으므로 캡처만 되면 전량 수집.

## Tier2 (DOM 폴백) 강화 — 더보기 접힘
1. **상세이미지 갤러리 독립 수집** (핵심 버그 수리): 기존엔 `images.length === 0`일 때만 상세 DOM 수집 →
   Tier1이 갤러리를 채우면 상세는 영영 비었음. 이제 `detailImages.length === 0`이면 갤러리 유무와 무관하게 수집.
2. **숨김 컨테이너 포함**: `_domImages`의 `querySelectorAll`은 `display:none`도 포함 + `_bestImgSrc`가
   `data-src`/`data-original`/srcset까지 읽음 → 접힘(display:none) 상세이미지 수집.
3. **더보기 프로그램 클릭 + 대기** (`kgpRevealDetailFolds`): 상세/설명 컨테이너 안 '더보기'·'펼치기'·'see more'
   버튼을 찾아 클릭 → `MutationObserver`로 새 img mount 대기(**최대 3s**, 새 이미지 뜨면 조기 종료) → 재수집.
   접힘 없으면 즉시 진행(정상 페이지 지연 0). 추가 네트워크 요청 0(페이지 자체 로더가 채움).
   `handleFabClick`이 추출 전에 호출.
4. **정직 '일부만'**: 접힘 잔존(`detail_fold`) + 상세이미지 0이면 경고("상세이미지 일부만 — 더보기 펼침 필요").

## 갤러리 vs 상세이미지 분리 + 드로어 렌더
- `gallery_images` / `detail_images` 별도 필드(기존) + `detail_fold` 플래그 신규(클라 병합 OR → 서버 영속).
- 드로어 **'상세페이지' 탭**(data-etab="detail")이 `_EXTRA.detail_images` 렌더(기존 썸네일 탭 → 상세페이지 탭 이동).
  접힘 잔존 시 정직 안내("원본에서 '더보기'를 펼친 뒤 다시 수집" — 무음 실패 금지).

## 판정
- 가드 test_v57_temu_images(8): Tier1 키·독립수집·fold경고/플래그·reveal함수·content_script배선·서버영속·
  드로어탭 + **node 실행**(mock 더보기 버튼 클릭·cb 1회) pass. 관련 43 pass.
- 확장 1.5.57(v57 일괄 — STEP1 아이콘과 동일 배포). 오너 액션: 확장 1.5.57 재로딩.
