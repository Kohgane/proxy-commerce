# v53 STEP0 — 배포 감사 (최우선)

## 결론
**코드는 전부 main에 머지·반영됨. 라이브에 안 보이는 원인 = Render 재배포 누락**(코드/번들 문제 아님).
번들도 정상: Dockerfile이 `COPY src/`·`COPY extensions/` 둘 다 포함 → 재배포만 되면 라이브 반영됨.

## 감사표
| 항목 | PR | 머지 | main 반영 커밋 | 코드 마커(main 실측) | 번들 포함 |
|---|---|---|---|---|---|
| v51 Tier1 테무 API 인터셉트 | #447 | ✅ merge `3cd09eb` | `69494b3` | `extensions/chrome-collector/kgp-net.js` 존재 | `COPY extensions/` ✅ |
| v51 STEP2 풀·드로어 왕복 | #447 | ✅ | `aaaefc2` | `connected_markets`·풀 기본 ON | `COPY src/` ✅ |
| v52 STEP1 instant-nav | #448 | ✅ merge `a871d6f` | `f465808` | `_base.html`에 `kgp-page-js`·`X-KGP-Nav` (2곳) | ✅ |
| v52 STEP2 ld+json 가격 | #448 | ✅ | `b70d6bf` | `state_json.parse_ldjson` (1) | ✅ |
| v52 STEP3 테무 북마클릿 Tier2 | #448 | ✅ | `b70d6bf` | `_bookmarklet_js`에 `GX/BS/PP` | ✅ |

> main HEAD = `a871d6f`. 위 마커는 이 커밋의 워킹트리에서 grep으로 전부 확인됨(머지·반영 100%).

## 라이브 확인(오너 몫 — 에이전트 프록시가 kohganepercentiii.com 차단[403], 직접 curl 불가)
**신설 build 마커로 한 줄 판정:**
```
curl -s https://kohganepercentiii.com/health          # {"build":"a871d6f",...} 면 최신 배포
curl -s https://kohganepercentiii.com/ | grep 'name="build"'   # <meta name="build" content="a871d6f">
```
- `build` 값이 **`a871d6f`(현 main)이면 최신 배포됨** → 그래도 기능이 안 보이면 브라우저 캐시.
- **옛 커밋이거나 `unknown`이면 배포 누락** → Render 대시보드에서 **Manual Deploy**(또는 Auto-Deploy 설정 확인).
  세 번째 "그대로"의 유력 원인 = **Render Auto-Deploy가 꺼져 있어 main 머지가 배포로 이어지지 않음.**

## build 마커 규약(신설 — 앞으로 모든 배포에 적용)
- `src/utils/build_info.get_build_sha()`: `RENDER_GIT_COMMIT`(Render 런타임 자동) → `BUILD_SHA`/`GIT_COMMIT` env →
  빌드파일 → git → `unknown`. 값 없으면 정직하게 `unknown`(가짜 커밋 날조 0).
- 전 페이지 `<head>`에 `<meta name="build" content="{7자리}">`(both `_base.html`·`_base_app.html`) + `/health` `build` 필드.
- → 오너·다음 세션이 **curl 한 줄로 라이브 코드 버전 판정** → "머지했는데 그대로" 재발 시 즉시 원인 특정.

## 판정
- 로컬: `/health.build` == 페이지 `<meta build>` == `get_build_sha()` 일치(가드 test_v53_deploy_marker 4).
- 라이브 실증(오너): 재배포 후 `curl /health` 의 build == main HEAD → v51 확장 tier1·v52 ld+json 가격·prefetch 내비 각 1개 캡처.

## STEP 1~4 진행 조건
STEP0 게이트: **오너가 재배포 + `/health.build` 최신 확인** 전까지 STEP2(수집 필드 재판정)는 라이브 확정 불가.
단 STEP1(버튼 컨텍스트 감지)·STEP3(초가속)·STEP4(북마클릿 안내)는 배포와 독립인 신규 코드라 이어서 구현 가능.
