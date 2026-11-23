# 고가브릿지 아이폰 앱 (mobile/ios)

번들 `org.kohgane.gogabridj` (+ 공유 확장 `org.kohgane.gogabridj.share`) · 팀 `J6TH5PRA9L` · XcodeGen 프로젝트.

## 빌드·배포 경로
맥이 없으므로 **깃허브 액션 맥 러너**가 묶어서 TestFlight 에 올린다.
- 소스 정본: 이 폴더(Kohgane/proxy-commerce `mobile/ios`).
- 빌드: Kohgane/kohgane-vault 의 `.github/workflows/gogabridj-testflight.yml` (App Store Connect API 키가 그 저장소 비밀값에 있음).
  채팅 쪽 블루호스트 잡이 이 폴더를 볼트 `apps/gogabridj-ios` 로 그대로 복사·푸시하면 빌드가 돈다.
- 빌드 번호 = 100 + 실행 번호(웹 셸 시절 빌드보다 항상 크게).

## 앱이 하는 일
| 기능 | 위치 |
|---|---|
| 셀러 콘솔 앱 셸: 시작 `/seller/m`, 배경·상태바 `#1a1714`, safe-area, 뒤로 스와이프, 당겨서 새로고침, 오프라인 화면, 바깥 링크는 시스템 브라우저 | `App/GogabridjApp.swift` |
| 구글·카카오·네이버 로그인 = `ASWebAuthenticationSession` (웹뷰 차단 회피) | 같은 파일 `startOAuth` |
| 공유 확장: 타오바오·사파리·쿠팡 → 「공유 → 고가브릿지」 → `/seller/collect/share` | `Share/ShareViewController.swift` |
| 본앱 ↔ 확장 로그인 공유(키체인 공유 그룹 `…org.kohgane.gogabridj.shared`) | `Shared/Shared.swift` |
| 푸시(APNs) 토큰 등록, 알림 누르면 `path` 화면으로 | `AppDelegate` |
| 패스키: `webcredentials:kohganepercentiii.com` | `project.yml` entitlements |
| 딥링크 `gogabridj://open?path=/seller/m/item/123` | `onOpenURL` |

웹에서 앱인지 알기: `window.KG_APP` (platform·version), `<html class="kg-app">`.
웹 → 앱: `window.webkit.messageHandlers.kg.postMessage({t:'haptic'})`, `{t:'share', text, url}`.

## 서버가 맞춰 줘야 하는 약속 (CC)
1. **소셜 로그인 앱 모드**: `/auth/<google|kakao|naver>/start?app=1&next=/seller/m` 로 시작하면, 콜백 끝에서 웹 리다이렉트 대신
   `gogabridj://auth?code=<1회용·60초>` 로 보낸다. 웹뷰가 `GET /auth/app/exchange?code=…&next=…` 를 열면 세션 쿠키를 심고 `next` 로 302.
2. **공유 수집 JSON**: `POST /seller/collect/share` (form: `text`, `url`, `title`, `src=ios-share`) + 헤더 `Accept: application/json`
   → `{"ok":true,"item_id":123,"title":"…","thumb":"https://…","path":"/seller/m/item/123","dup":false}`.
   인증은 세션 쿠키(앱이 넘김) 또는 `Authorization: Bearer <개인토큰>`. 미로그인은 401(JSON).
3. **개인 토큰 발급**(선택): `POST /api/app/token` (로그인 세션) → `{"token":"…"}` — 쿠키가 만료돼도 확장이 담을 수 있게.
4. **푸시 등록**: `POST /api/push/apns/register` `{token, env:"production", bundle}` (로그인 세션) 저장.
   보낼 때 payload 에 `path` 를 넣으면 앱이 그 화면을 연다. 이벤트: 수집 완료·사전검증 보류·등록 성공/실패·주문.
   APNs 발송 키(.p8, Keys → Apple Push Notifications service)는 오너가 개발자 계정에서 만들어 Render env 로 넣는다.
5. **AASA**: `/.well-known/apple-app-site-association` 에 `{"webcredentials":{"apps":["J6TH5PRA9L.org.kohgane.gogabridj"]},"applinks":{…}}`.
   (현재 코드는 `IOS_APP_ID` env 로 applinks 만 채운다 → webcredentials 추가 + env `IOS_APP_ID=J6TH5PRA9L.org.kohgane.gogabridj`.)

## 검수(오너 실기기)
① 타오바오 「공유 → 고가브릿지」 → 「담았어요」+썸네일 ② 누르면 앱에서 그 상품 화면 ③ 마켓 선택 → 사전검증 → 등록 직전까지.
