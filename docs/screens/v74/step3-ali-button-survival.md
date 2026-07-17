# v74 STEP3 — 알리 버튼 생존 (퍼센티 패리티)

## 증상
알리 카드에 마우스 호버 시 오버레이(장바구니/위시 등)가 **카드 서브트리를 통째로 재렌더**(React) → 그 안에
있던 우리 호버 수집 버튼이 **증발**. 퍼센티는 생존.

## 수리 (소실 즉시 재부착 — 위치 회귀 0)
브리프 옵션 검토: (2)안정 조상 앵커는 v65 이미지-앵커 위치를 바꿔 전 사이트 회귀 위험 → (1)**소실 즉시 재부착** 채택.
- 신규 MutationObserver가 **우리 오버레이(`.kgp-card-quick`/`.kgp-card-chk`)의 제거만** 감지(`_isOurOverlay`) →
  `kgpReattachOverlays()`가 **100ms 디바운스**로 `kgpInjectListing()`(멱등) 호출 → 사라진 버튼만 다시 생성.
- 기존 300ms 신규-타일 재스캔과 **별개**(더 빠른 전용 경로) — 호버 재렌더 폭주는 디바운스로 완화.
- 이미지 앵커(v65) 그대로 → 다른 사이트 위치 회귀 0.

## 판정
- 가드 `tests/test_v74_ali_button_survival.py`(3): source-contract + 실 content_script를 **호버 시 서브트리를
  재렌더하는 알리 픽스처**에 주입 → 초기 7 부착 → **호버로 카드1 버튼 파괴(7→6)** → **재부착(6→7·카드1 복귀)**.
- **판정 캡처(필름스트립 3장)**: `step3-ali-a-before.png`(호버 전 버튼) → `step3-ali-b-during-swap.png`(호버 재렌더
  직후 소실) → `step3-ali-c-reattached.png`(오버레이 'Add to Cart' 등장 중에도 '수집' 버튼 재부착).
- 픽스처 `fixtures/realpages/ali-list.html`(mouseenter → .card-inner 재렌더; 오너 실스냅샷 공급 시 교체).
- manifest 1.5.94→**1.5.95**(재로딩) + 버전핀. 회귀: 전체 그린.
- **실기기(오너 몫)**: 알리 카드 호버→오버레이 등장 중에도 수집 버튼 잔존 녹화(확장 1.5.95 재로딩 후).

## 금지 준수
추출기 변경 0 · 위치 회귀 0(이미지 앵커 보존) · 가짜 성공 0(실 재렌더 픽스처로 소실→재부착 실측).

적용 스킬: (확장 오버레이 재부착 — UI 색/렌더 변경 없음. impeccable/humanizer CLI 미설치.)
