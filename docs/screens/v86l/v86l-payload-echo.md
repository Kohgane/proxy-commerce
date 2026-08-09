# v86-L — payload_echo=null 배선 결함 봉인

## 증상 (오너 실기기 확정)
테무 갤럭시 프로젝터 수집 클릭 → 진단 파일 `payload_echo: null` (확장 1.5.140, 04:05:18Z).
`tier1_diag`·`bar_collapsed`는 정상 → 진단 자체는 돌았는데 echo만 비었다.

## 4-지점 추적
- **(a) 월드분리** — 배제. `_kgpMetaStore`·진단 export·recorder 전부 content_script **같은 world**.
  tier1은 MAIN(kgp-net)이지만 `payload_echo`는 tier1을 읽지 않는다.
- **(b) 경로분기** — **★근본.** echo 기록은 `handleFabClick`(FAB 단건, content_script.js:1461)에만
  있었다. 호버 단건 `kgpQuickCollect`(2440)·벌크 `kgpRunBulk`(2501)의 `collectBulk` 경로는
  `_kgpMetaStore.echo`를 **아예 안 남겼다**. 테무 목록에서 호버/벌크로 수집 → echo는 초기 `null` 그대로.
- **(c) 타이밍 / (d) 페이지재렌더** — 배제. 벌크 경로는 애초에 기록 지점이 없어, tier1 대기·SPA 재렌더와
  무관하게 null. (재렌더는 `_kgpMetaStore`를 리셋하지만, 그 이전에 기록 자체가 없었다.)

## 수리
echo 기록 **단일 관문** `_kgpRecordEcho(meta, path, extra)` 신설 — 모든 전송 경로가 경유:
- FAB → `_kgpRecordEcho(meta, "fab")`
- 호버 단건 → `_kgpRecordEcho(meta, "hover")`
- 벌크 → `_kgpRecordEcho(items[0] || {}, "bulk"|"bulk-retry", { items_n })`

echo에 **`path` enum**(fab·hover·bulk·bulk-retry — '어느 버튼이 보냈나')과 **`echoed_at`**('언제')을
동봉. 어느 경로로 보냈든 `payload_echo`는 non-null → 다음 실기기 진단에서 경로까지 즉판.

FAB 직접대입(`_kgpMetaStore.echo = _kgpPayloadEcho(meta)`)은 제거 → 단일 관문 우회 금지(회귀 방지).
manifest 1.5.141 → **1.5.142**.

## 판정
- **echo 계약** `tests/test_v86_l_payload_echo.py`(4): 단일 관문 정의 + 3경로 배선 + node로 경로별
  echo **6필드 이상 non-null · path enum · echoed_at ISO** 실증(빈 meta여도 non-null).
- **인위회귀(로컬 실측):** recorder의 `_kgpMetaStore.echo = e` 무력화 → 계약 2건 **RED**
  (payload_echo=null 재현) → 원복 → **4 GREEN**.
  ```
  ===== 무력화 후 (RED) =====
  FAILED test_echo_recorder_defined_with_path_and_echoed_at
  FAILED test_echo_records_nonnull_for_every_path
  2 failed, 2 passed
  ===== 원복 후 (GREEN) =====
  4 passed
  ```
- **v86-H·I·K 회귀 없음:** v86-i(payload_echo 계약을 단일 관문 기준으로 갱신)·h·k·tier1·diag 가드
  88 passed. (v86-i의 옛 FAB 직접대입 단언 1건을 recorder 기준으로 갱신 — 동작 보존.)

## 금지 준수
추출기·tier1 선택 로직·kgp-net.js(MAIN world) 스코프 무변경. 변경은 content_script 전송 계측 3경로 배선뿐.
서버 파일 불가침. v86-K와 브랜치 분리(별도 커밋), 스위트 실행 중 브랜치 전환 없음.
