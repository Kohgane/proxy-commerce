# v60 STEP5 — 디폴트 소싱처 버튼 결정성 + 호버 수집

## 디폴트 소싱처 버튼 (판정불능 금지)
- `kgpIsDefaultSourcing()` + `KGP_DEFAULT_SRC_RE`(amazon·temu·aliexpress·taobao·tmall·1688·야후재팬·메루카리·라쿠텐).
- `kgpDetectPageType`: 디폴트 소싱처면 **URL 패턴으로 결정적 판정**(불능 'unknown' 금지):
  상세패턴(/dp/·/gp/product·-g-{id}·/item/·/goods/{n} 등) → **single(우측 단건)** / 그 외 도메인 전체 → **list(중앙 벌크)**.
- 실증(node): amazon /dp/→single · /s?k=→list · temu -g-123→single · temu home→list · 그 외 사이트→기존 휴리스틱.

## 호버 수집 (목록 페이지 — v42 E-3 기반 재확인·가드)
- 카드 우상단 소형 [수집] 버튼(우리 마크), **카드당 1개**(`:scope > .kgp-card-quick` 중복 방지), 재스캔 시 재사용.
- 클릭 → `kgpQuickCollect` → **확장 큐(`collectBulk` 메시지)** 로 단건 수집(백그라운드 fetch 아님) → `_kgpCollectedUrls` +
  `kgpMarkQuickCollected`로 **'수집됨 ✓' 배지**. 실제 새 수집만 축하(중복은 조용).
- `kgpMarkExisting`(collectExists)로 이미 수집된 카드 선표시(중복 방지 연동).
- 카드 감지: 아마존 `_kgpAmazonCards` 어댑터 + 제네릭(`_kgpIsDetailHref`가 /g-{id} 등 테무 그리드 인식).

## 판정 (배포 후 실기기 — 오너, 총 4캡처)
아마존 검색결과 호버 [수집]→클릭→토스트→목록 반영 / 아마존 상세 우측 단건 / 테무 동일 2종.
manifest 1.5.60→1.5.61. 가드 test_v60_hover_default(4, node 결정성 실증).
