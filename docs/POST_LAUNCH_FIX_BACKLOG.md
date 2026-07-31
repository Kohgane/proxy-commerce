# 론칭 후 수리 대상 — 사전 존재 실패 16건

> 오너 프리즈 지시(2026-07-31) §5: **기록만. 오늘 수리 금지.**
> 지휘 문서 `launch_masterplan_D30`은 리포에 없어(CLAUDE.md에 이름만 참조) 이 파일로 기록한다.

**기준 커밋:** `ad825d31` (main, PR #554·#555·#557 머지 후)
**측정:** 전체 스위트 11555 passed / 16 failed / 81 skipped —
`PLAYWRIGHT_BROWSERS_PATH=… PYTHONUTF8=1 KGP_REQUIRE_BROWSER=1 pytest tests/ -q`
**중요:** 이 16건은 v86/v87 작업 **이전부터 빨갛던 것**이다. 이번 트랙이 만든 실패는 0건(베이스라인 대조).

---

## 분류

아래 사유는 각 테스트를 **읽기만** 해서 뽑은 실측 메시지다. 원인 단정이 아니라 **관측된 실패 문구**이며,
실제 근본은 수리 착수 시 규명해야 한다(추측 금지).

### A. 아이콘 자산 — 커밋본과 코드 생성본 불일치 (2건)

| 테스트 | 관측된 실패 |
|---|---|
| `test_v50_icon_v8_rollout::test_committed_favicons_match_code_v8_master` | `favicon-16.png 커밋≠코드v8(재생성 필요)` — 해시 `cc99d7c3…` vs `d33f4ed2…` |
| `test_v57_icon_truth::test_committed_favicons_match_code` | 동일 (`favicon-16.png 커밋≠코드`) |

> 같은 원인으로 보이는 한 쌍. `scripts/build_icons.py` 재실행 후 커밋이면 해소될 가능성이 높으나,
> **왜 갈라졌는지**(생성기 변경 vs 자산 수기 교체)를 먼저 확인할 것.

### B. 아이콘/OG 부산물 — 테스트가 실행 중 파일을 재생성 (1건)

| 테스트 | 관측된 실패 |
|---|---|
| `test_v50_icon_v8_rollout::test_og_card_uses_v8_master` | 실행 순서에 따라 통과/실패가 갈린다 |

> **알려진 함정:** 아이콘 테스트가 `assets/og/og-card-1200x630.png`·`src/seller_console/static/og-card.png`를
> 매 실행마다 재생성한다. 커밋 전 `git checkout --`로 되돌리지 않으면 리포에 부산물이 섞인다.
> 수리 시 "테스트가 산출물을 건드리지 않게" 하는 쪽이 근본이다.

### C. 확장 소스 고정핀 — 코드가 옮겨갔는데 핀이 옛 문자열 (5건)

| 테스트 | 관측된 실패 |
|---|---|
| `test_v45_p3p4p5_extension::test_p5_fab_documentElement_and_observer_reattach` | `'z-index:2147483647' in …` — FAB이 shadow 호스트로 이전되며 인라인 z-index 표기가 바뀜 |
| `test_v47_mainworld_extract::test_download_zip_includes_main_bridge` | `assert (None)` |
| `test_v51_temu_adapter::test_source_labels_and_bookmarklet_toast` | `'"kgp-net.js"' in views.py` — 확장 파일명이 서버 뷰에 있길 기대 |
| `test_v78_desc_priority::test_desc_ladder_source` | `'description = _m; descSource = "meta";' in kgp-extractor.js` |
| `test_v83_currency_ali::test_step2_ali_source_contract` | `'aliexpress\.[a-z][a-z.]*$' in kgp-sources.js` |

> **패턴:** 전부 "소스에 이 문자열이 정확히 있다"는 고정핀이다. 이번 트랙에서 여러 번 겪은 유형 —
> 리팩터링에 부서지고, 부서진 채 방치되면 **그 계약이 지키던 동작이 무방비**가 된다.
> 수리 방향은 문자열 핀 → **동작 계약** 재작성(v43-2·v71·v77·v81 선례).

### D. 노드 하네스 — 의존 누락으로 스크립트 자체가 실패 (4건)

| 테스트 | 관측된 실패 |
|---|---|
| `test_v70_price_precision::test_buybox_wins_over_ad_text_price_node` | `tmp….js:133` / `assert 1 == 0` |
| `test_v76_title_sanitize::test_sanitize_patterns_node` | `tmp….js:15` / `assert 1 == 0` |
| `test_v80_recollect_verdict::test_amazon_title_sanitizer_strips_prefix_verdict` | `tmp….js:15` / `assert 1 == 0` |
| `test_v81_source_matcher::test_amazon_country_currency_locale` | `node 실패: [eval]:1` |

> **패턴:** 하네스가 함수를 **이름으로 뽑아** 실행하는데 대상 함수가 새 의존을 갖게 되면
> `ReferenceError`로 **조용히 0건**이 된다. 이번 트랙에서 v43-2가 정확히 이 함정으로 27→16이 됐고,
> 제품 회귀로 오독할 뻔했다. 수리 시 의존 목록 갱신 + "0건이면 red"인 반-공허 단언을 같이 넣을 것.

### E. 나머지 (4건)

| 테스트 | 관측된 실패 |
|---|---|
| `test_integrations::TestSyncScheduler::test_run_not_due` | 스케줄러가 실행 안 돼야 하는데 결과 목록이 비지 않음 |
| `test_v33_emoji_sweep::test_user_template_has_no_emoji[bookmarklet.html]` | `이모지 잔존 ['⚡','⚡']` — 이모지 0 원칙 위반 |
| `test_v56_bookmarklet_loader::test_token_not_in_run_js` | `'TOK' not in …` — **토큰이 스크립트에 섞였는지 보는 보안 계약이라 우선순위 높음** |
| `test_v72b_recollect::test_recollect_updates_existing_no_new_row` | `assert '' == '12000'` — 재수집 시 가격 갱신 실패 |

---

## 우선순위 제안 (수리 착수 시)

1. **`test_v56_bookmarklet_loader::test_token_not_in_run_js`** — 토큰 노출 여부를 보는 계약이다.
   실제 노출인지 핀 노후화인지 **가장 먼저** 가려야 한다.
2. **D군(노드 하네스 4건)** — 빨간 채로 두면 그 경로의 회귀를 아무도 못 잡는다. 고치기도 싸다.
3. **C군(고정핀 5건)** — 동작 계약으로 재작성.
4. **A·B군(아이콘 3건)** — 사용자 영향 낮음. B는 테스트가 산출물을 건드리는 것부터.
5. **E 나머지** — 개별 판단.

## 하지 않은 것 (정직)

- 원인 규명·수리 **일절 안 했다**(오너 §5 "오늘 수리 금지").
- 위 사유는 실패 메시지 관측이며 근본 원인 단정이 아니다.
- 각 항목이 실제 사용자 영향으로 이어지는지는 미확인 — 우선순위는 제안일 뿐이다.
