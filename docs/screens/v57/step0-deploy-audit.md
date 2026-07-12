# v57 STEP0 — v56 배포 감사 (선행)

## 감사표 (코드 = main 병합됨)
| 항목 | 확인 |
|---|---|
| v56 PR #452 | ✅ merge (main HEAD `699a2a6`) |
| 북마클릿 로더 구조 | `_bookmarklet_js` 인라인 코어 + `run.js` 주입(3곳) — main에 존재 |
| `/seller/bookmarklet/run.js` | 라우트 존재(CORS·인증불요, `window.__kgpRun`) |
| `/seller/bookmarklet/testpage` | 라우트 존재(ld+json 데모 + 토스트 감시 초록 판정) |
| build 메타 | `<meta name="build">` 존재 → `curl /health` build 해시로 라이브 판정 |

## 라이브 확인 (오너 — 프록시가 kohganepercentiii.com 차단)
```
curl -s https://kohganepercentiii.com/seller/bookmarklet/run.js | head -c 60   # window.__kgpRun( 이면 배포됨
curl -s https://kohganepercentiii.com/health                                    # build == 699a2a6(이후)면 최신
```
미배포면 Render Manual Deploy. **핵심: 코드는 main에 있음 → 재배포만 되면 로더 라이브.**

## 구버전 폐기 (경고 배너)
북마클릿 페이지 **최상단 경고 배너**: "이전에 설치한 북마클릿은 더 이상 작동하지 않습니다 — 새로 설치하세요."
→ 로더 전환으로 구 토큰·구 코드가 자연 폐기되므로 재설치 유도 + 설치 테스트 링크.

## 판정
감사표(위) + 오너 재배포 후 테스트페이지 초록 판정 캡처.
