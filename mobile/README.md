# 코고가네 모바일 양대 스토어 패키징 (v15)

코고가네는 **PWA(설치형 웹앱)**가 이미 동작합니다(`/seller/static/manifest.webmanifest` + 서비스워커 + 공유 수집).
이 폴더는 그 PWA를 **구글 플레이**·**앱 스토어**에 올리기 위한 **패키징 경로(설정/스크립트)**를 모아둡니다.
앱은 우리 서버(HTTPS)를 감싸는 얇은 네이티브 셸이라, 웹을 고치면 앱도 같이 갱신됩니다.

> 전제: 사이트가 HTTPS로 서비스되고, manifest/아이콘(192·512 maskable)/서비스워커가 정상이어야 합니다(현재 충족).

---

## 1) 구글 플레이 — TWA (Trusted Web Activity)

가장 쉬운 길은 **PWABuilder** 또는 **Bubblewrap**으로 TWA 앱을 만드는 것입니다.

### PWABuilder (웹, 가장 쉬움)
1. https://www.pwabuilder.com 접속 → 사이트 주소(`https://<도메인>`) 입력 → **Package For Stores → Android**.
2. 패키지 옵션은 `mobile/twa-manifest.json` 값을 참고해 채웁니다(패키지명/색/시작 URL).
3. 생성된 `.aab`(앱 번들)와 **서명 키의 SHA-256 지문**을 받습니다.
4. 그 지문을 서버 환경변수에 넣습니다(아래 §3) → `/.well-known/assetlinks.json`이 자동으로 검증값을 내보냅니다.
5. Google Play Console에 `.aab` 업로드 → 심사 제출.

### Bubblewrap (CLI)
```bash
npm i -g @bubblewrap/cli
bubblewrap init --manifest https://<도메인>/seller/static/manifest.webmanifest
# 패키지명/색은 mobile/twa-manifest.json 참고
bubblewrap build      # app-release-bundle.aab + 서명지문(SHA-256)
```
빌드가 출력한 SHA-256 지문을 §3 환경변수에 등록하세요.

---

## 2) 앱 스토어(iOS) — Capacitor 셸

iOS는 PWA를 스토어에 직접 못 올리므로 **Capacitor**로 웹뷰 셸을 만들어 우리 사이트를 띄웁니다.
`mobile/capacitor.config.json`이 그 설정(서버 URL을 가리킴)입니다. **Xcode가 설치된 macOS**가 필요합니다.

```bash
npm i -g @capacitor/cli
# mobile/ 에서:
npm init -y && npm i @capacitor/core @capacitor/ios
npx cap add ios
npx cap copy
npx cap open ios      # Xcode 열림 → 서명(Apple Developer 계정) → Archive → App Store Connect 업로드
```
- Universal Links를 쓰려면 `IOS_APP_ID`(=`TEAMID.com.bundle.id`)를 §3에 넣으면
  `/.well-known/apple-app-site-association`이 자동으로 채워집니다.

---

## 3) 서버 환경변수 (오너 액션 — 스토어 연동 검증)

| 환경변수 | 용도 | 예 |
|---|---|---|
| `TWA_PACKAGE_NAME` | 플레이 TWA 패키지명 | `com.kohgane.collector` |
| `TWA_SHA256_FINGERPRINTS` | TWA 서명 SHA-256(콤마로 다중) | `AA:BB:...:FF` |
| `IOS_APP_ID` | iOS 앱 식별자(TeamID.BundleID) | `ABCDE12345.com.kohgane.app` |

미설정 시 `/.well-known/assetlinks.json`은 `[]`, AASA는 빈 `details`로 응답합니다(**가짜 연동 금지** — 정직).

---

## 참고
- 웹 매니페스트: `src/seller_console/static/manifest.webmanifest` (name/short_name/아이콘/share_target/shortcuts 충족).
- 앱은 웹을 감싸는 셸 → 기능 업데이트는 **웹 배포만으로** 반영(스토어 재심사 최소화).
- 국내(한국) 우선: 기본 언어 `ko`. 글로벌(영문) i18n은 후속.
