# v50 — 브랜드 아이콘 v8 전면 배포 (진단 + 캐시버스트)

## 진단 (오너: 라이브 favicon ≠ v8 마스터, "한 번도 배포 안 됨")
해시로 근원 규명:
- **커밋된 static 파비콘 = build_icons.py 코드 v8 출력과 해시 정확히 일치**(favicon-16/32/48·ico·apple-touch·
  icon-192/512/1024·확장 16/32/48/128 전부 MATCH). → 레포의 파비콘은 이미 v8.
- **Dockerfile은 `COPY src/ ./src/`로 static을 이미지에 포함**(누락 아님).
- 따라서 라이브 불일치 = **배포/캐시 문제**(구 Render 빌드가 아직 서비스 중 or 브라우저·CDN 캐시), 스테일
  파일 문제가 아님.
- **유일한 스테일 자산 = og-card.png**(Jun 29 생성, Jul 4 v8 재빌드 이전 → 구 아이콘 임베드). → v8 마스터로 재생성.

> ⚠️ 브리프가 지목한 `brand_icons_v2/` 디렉토리는 레포에 없음. 확정 v8 마스터의 단일 소스는
> `scripts/build_icons.py`(오너가 #415에서 지오메트리 스펙 제공한 코드 렌더)로 간주하고 그걸 기준으로 대조·
> 재생성. 만약 오너의 `brand_icons_v2/` 마스터가 코드 렌더와 **픽셀 단위로 다르면**, 그 PNG를 레포에 커밋해
> 주면 그걸 정본으로 재파생하겠음(후속). 현재로선 코드 v8 = 정본.

## 조치
1. **og-card 재생성**: `gen_og_card.py`(소스=`assets/brand-icons/icon-master-1024.png` v8) 재실행 →
   `static/og-card.png`·`assets/og/og-card-1200x630.png` v8로 갱신(구 아이콘 제거). og `?v=4→5`.
2. **파비콘 세트 재확인**: `build_icons.py deploy` 재실행 — 출력이 커밋본과 동일(이미 v8, diff 0). 신선도 보장.
3. **캐시버스트 `?v=180→181`**(63개 참조: `<head>` favicon 링크·manifest·landing 로고·북마클릿 토스트 마크 등)
   → 라이브 브라우저가 파비콘을 **강제 재요청**(캐시가 원인이면 이걸로 해소).
4. **네비바 로고**: 랜딩·콘솔 헤더 로고 = `favicon.svg`(v8, 흰 배경 카드+먹 보더) — `?v` 범프로 갱신. 스타일 무변경.
5. **확장 아이콘**: 이미 v8(해시 일치). manifest **1.5.50→1.5.51**(재로딩 유도).
6. **구 아이콘 정리**: static에 글러브/오빗/지구본 PNG **0**(v8 11개 파일만), 참조 잔존 **0**(grep 확인).

## 판정 (오너 배포 후)
- 라이브 `kohganepercentiii.com/seller/static/favicon-32.png?v=181` 받아 **md5 대조**:
  - 정본 v8 md5 = `d72587e824e4a907c1d062f9da685dfd` (favicon-32.png). 일치하면 v8 라이브 확정.
  - (favicon.ico=`e6f93179…`, favicon-16=`c18be9aa…`, apple-touch=`3e7958b3…`)
- 브라우저 탭·네비바·북마클릿 파일 ICON 3곳 캡처. 확장은 1.5.51 재로딩 후 툴바 아이콘 캡처.
- **핵심**: 파일은 이미 v8이므로 오너는 **Render를 재배포**(수동 Deploy)해야 라이브가 갱신됨 + 강한 새로고침
  (Cmd/Ctrl+Shift+R)로 브라우저 파비콘 캐시 비우기.

## 가드
test_v50_icon_v8_rollout(5): 커밋 파비콘=코드 v8 해시일치 / og-card v8 멱등 / 캐시버스트 181·5 / 확장 1.5.51 /
구 아이콘 파일 0. test_v28_og_image(?v=5)·아이콘 버전핀 테스트 갱신. 폰트·색 변경 0(아이콘 파일·버전 쿼리만).
