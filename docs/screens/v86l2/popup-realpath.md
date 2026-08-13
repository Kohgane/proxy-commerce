# v86-L2 — 팝업 [수집] 실경로: 하네스-실기기 괴리 근원 수리

## 오너 확정 사실 (재조사 금지)
테무 상세 [수집] → 직후 진단: **payload_echo=null + 서버 레코드 1/5**(가격·갤러리 탈락). 같은 진단에서
추출은 그린(price=12730=DOM 일치, tier1 adopted 정상). = **추출은 되는데 전송이 빔**. v86-I/L 인위회귀
그린은 실경로 미커버 = 공허한 그린.

## 4항 보고

### 1) 실브라우저 재현 (테무 상세 → [수집] → echo null + 1/5)
playwright + 확장 로드로, **상품이 네트워크로만 오는 테무형 픽스처**(가격·이미지는 XHR 응답 → MAIN 캡처,
DOM엔 og:title만)에서 재현:
- **수리 前 팝업 executeScript 추출** → `price=''` + `currency='USD'`(임의 기본값). = 서버 1/5 + 정직 위반.
- 팝업 전송 경로는 `_kgpRecordEcho`를 **호출하지 않음** → payload_echo=null. (echo=null 자체가 "FAB가
  아니라 팝업으로 보냈다"의 증거 — FAB/호버/벌크는 항상 echo를 남긴다.)

### 2) 클릭→전송 실경로 계측 + I·L 경로 동일성 판정
수집 진입점은 **넷**이다: FAB(`handleFabClick`)·호버(`kgpQuickCollect`)·벌크(`kgpRunBulk`)·**팝업(popup.js)**.
- v86-I/L은 앞의 셋을 단일 정본 경로(`kgpAcquireMeta` = 클릭 시점 재독출 + MAIN tier1 병합 →
  `_kgpRecordEcho`)로 통일하고 echo를 계측했다.
- **팝업만** 독립 경로였다: `chrome.scripting.executeScript`로 og/jsonld를 **ISOLATED**에서 읽어(→ 테무
  네트워크 상품 JSON=MAIN 캡처를 못 봄 → title만), `product:price:currency` 없으면 **currency를 임의
  'USD'로** 채우고, **echo를 안 남겼다**. → 오너가 가정한 "복수 진입점 중 하나만 수리"가 정확히 이것.

### 3) 근원 수리 + 실브라우저 계약 재작성
- **content_script.js**: `action:"kgpCollectNow"` 핸들러 신설 → FAB와 **같은 코드**
  (`kgpAcquireMeta` → `kgpExtractMerged`[MAIN tier1 병합] → `_kgpRecordEcho(meta,"popup")` → 전송).
  `extractMeta` 봉인과 동일하게 single 게이트도 방어선.
- **popup.js**: 수집 클릭이 **먼저** `kgpCollectNow`에 위임. content_script 부재 시에만 옛 executeScript 폴백.
- **실브라우저 계약**(`tests/test_v86_l2_popup_realpath.py`): 수리 前(price='' + 임의 USD) → 수리 後
  (corr_id 부여 + currency 정직 'KRW' + `echo.path='popup'`, payload_echo≠null). **CORE: PASS ✅**.

**부검 1줄**: 기존 I·L 계약은 in-page(FAB/호버/벌크)만 계측·검증했고, 팝업(popup.js)의 독립 collect 경로
(executeScript og/jsonld ISOLATED + tabs.sendMessage extractMeta, echo 미기록·MAIN 병합 없음)는 계약 밖이라
실경로를 놓쳤다.

### 4) 최종 판정 = 오너 실기기
확장 1.5.144 재로딩(chrome://extensions 새로고침) 후 테무 상세에서 **팝업 [수집]** → 직후 진단:
- `payload_echo`가 **null이 아니라** `{path:"popup", has_price:true, images_n:…}`로 채워지는지,
- 서버 레코드가 1/5가 아니라 가격·갤러리 포함으로 저장되는지 확인.

## 하네스 한계 (정직 표기 — 은폐 금지)
playwright `--load-extension`(headless=new)에서 `[kgp-extractor, kgp-main]`의 **MAIN 월드 주입이
불안정**하다: `window.kgpExtractProduct`가 페이지 월드에서 미정의(실 크롬/오너 실기기에선 정상 — kgp-net의
`window.__kgpCaptured`는 보이나 kgp-extractor의 export는 안 보이는 하네스 아티팩트). 그래서 이 계약은
**결함이 사는 배선(팝업→정본+echo)**을 실브라우저로 못박고, MAIN tier1 추출 자체(전 페이로드)는 jsdom
realpage 하네스(`test_v70_realpage_harness`)와 **오너 실기기 진단**이 별도로 담보한다. 이 분리를 숨기지 않는다.

## 금지 구조 준수
- **추출기·tier1 선택 로직 무수정**(kgp-extractor.js / kgp-net.js 불변 — 그린 확정 존중). 배선(content_script
  진입점 + popup 위임)만 수리.
- **서버 파일 불가침**(src/ 무변경).
- **'하네스에서 그린' 불인정** — 실브라우저(playwright + 확장) 증빙만 완료 근거로 제시.

## 캡처
`popup-realpath-before-after.png` — 근원(4 진입점 중 팝업만 독립) + 前(빈 가격·임의 USD·echo null) /
後(corr_id·KRW·echo path=popup) + CORE PASS.
