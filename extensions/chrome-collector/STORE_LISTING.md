# 고가수집기 — 크롬 웹스토어 게시 패키지 (v88-A)

> 오너 결정(2026-08-18): 크롬 웹스토어 **게시 채택**(CI zip은 보조 채널 병존). 목적 = "git pull→재로딩" 수동 루프 제거 + 자동 업데이트.
> **초기 공개 범위 = Unlisted(비공개)** — 검색 노출 없이 링크 설치만. 심사 제출·개발자 등록($5)은 **오너 클릭**(아래 오너 액션 표).
> 이 문서는 스토어 대시보드 등록정보 폼에 그대로 옮겨 붙이는 초안이다. 스크린샷·아이콘·개인정보 URL은 기존 자산 재사용(신규 발명 0).

---

## 1. 기본 등록정보 (Store listing)

| 필드 | 값 |
|---|---|
| 항목 이름(Name) | 고가수집기 (gogabridj Collector) |
| 요약(Summary, ≤132자) | 지정 소싱처에서 한 번의 클릭으로 상품을 고가브릿지로 수집 — 인페이지·리스트 다중 선택·자동 번역. |
| 카테고리(Category) | Shopping (대안: Workflow & Planning) |
| 언어(Language) | 한국어(기본) + English |
| 공개 범위(Visibility) | **Unlisted** (링크 설치만, 검색 미노출) |
| 아이콘(Store icon 128px) | `icons/128.png` — v8 브릿지 마스터(먹/금/청록/주황 키스톤) |

### 상세 설명 — 한국어
```
고가수집기는 고가브릿지(gogabridj) 셀러가 해외 소싱처(타오바오·아마존·라쿠텐 등, 사용자가 직접 등록한 사이트)에서
상품 정보를 한 번의 클릭으로 수집해 자신의 고가브릿지 작업공간으로 보내는 크롬 확장입니다.

• 인페이지 수집: 상품 상세 페이지에서 '수집' 버튼 한 번 → 제목·가격·이미지·옵션·상세를 렌더된 화면 그대로 수집.
• 리스트 다중 선택: 검색·목록 페이지에서 원하는 상품만 골라 한 번에 수집.
• 자동 번역: 수집 시 한국어로 번역(원문 보존).
• 지정 소싱처 한정: 사용자가 옵션에서 등록한 소싱처에서만 동작합니다.

고가브릿지 계정이 필요합니다. 수집한 데이터는 사용자 본인의 고가브릿지 작업공간에만 저장됩니다.
```

### 상세 설명 — English
```
gogabridj Collector lets gogabridj sellers capture product data from their chosen sourcing sites
(Taobao, Amazon, Rakuten, and any site the user adds) with a single click, into their own gogabridj workspace.

• In-page capture: one "Collect" button on a product page grabs title, price, images, options and details
  exactly as rendered.
• Multi-select on listings: pick only the products you want from a search or category page.
• Auto-translation into Korean (original text preserved).
• Runs only on the sourcing sites the user configures in Options.

Requires a gogabridj account. Captured data is stored only in the user's own gogabridj workspace.
```

### 단일 목적(Single purpose) — 심사 필수 문안
```
This extension has a single purpose: to collect product information from e-commerce sourcing sites that the
user designates, and send it to the user's own gogabridj seller workspace for translation and multi-market listing.
```

---

## 2. 권한 정당화 (Permission justifications) — 심사 폼에 항목별 그대로 입력

> 원칙: **현행 스코프 유지**(오너 결정 — 기능 보존이 게시 목적). 광범위 권한은 심사 지연 주범이므로 아래 문안으로 정당화한다.
> 런타임 이중 게이트: 콘텐츠 스크립트는 `<all_urls>`에 주입되나 `kgpHostAllowed()`가 **사용자가 등록한 소싱처에서만 활성화**한다(그 외 사이트는 아무것도 그리지 않음 — v10).

| 권한 | 정당화 문안 (영문, 심사 폼용) |
|---|---|
| `host_permissions: <all_urls>` | Sellers add their own sourcing sites (any e-commerce domain worldwide), so the collector must be able to read product DOM on user-designated sites. It activates only on sites the user configures in Options; on all other sites it is inert. |
| `content_scripts: <all_urls>` | Same reason — the "Collect" button and DOM extraction must run on whichever sourcing sites the user adds. A fixed match list cannot cover the open-ended set of sites sellers source from. Runtime host gating limits activation to configured sites. |
| `activeTab` | Read the currently focused product/listing tab's DOM when the user clicks Collect. |
| `storage` | Persist the user's configured sourcing sites, the collector on/off toggle, and the account token locally. |
| `scripting` | Inject the collection UI and read rendered DOM on the active sourcing tab (MV3 scripting). |
| `contextMenus` | Provide a right-click "Collect this product" entry as an alternative to the on-page button. |
| `notifications` | Inform the user of collect success/failure when the on-page toast is not visible. |

### 데이터 사용 공개(Privacy practices) — 심사 폼 체크
- **수집 데이터**: 사용자가 수집한 상품의 공개 페이지 정보(제목·가격·이미지 URL·옵션·상세)와 인증 토큰. → 사용자 본인의 gogabridj 서버로 전송·저장.
- **개인 식별 정보 판매·양도 없음.** 광고·트래킹 없음. 제3자 제공 없음(서비스 운영 목적 범위 내 사용자 본인 데이터만).
- **개인정보처리방침 URL**: `https://kohganepercentiii.com/privacy` (콘솔 기존 페이지 재사용, `/privacy.txt` 플레인텍스트 병존). ※오너 확인: 게시 시점 정본 도메인.

---

## 3. 스크린샷·프로모 (Screenshots)

> 규격: 1280×800 또는 640×400 PNG/JPG, 최소 1장·최대 5장. 아래는 촬영 대상(기존 화면 재사용, 신규 제작 0).

1. 소싱처 상품 상세에 뜬 '수집' 버튼(FAB) — 인페이지 수집 (`docs/screens/v42/e3-hover-collect.png` 계열 실촬영).
2. 리스트 페이지 다중 선택 바 — 전체/선택 수집 (`docs/screens/v45/p3p4p5-extension.png` 계열).
3. 수집 후 편집 드로어(제목·가격·이미지·옵션 7탭) (`docs/screens/v45/p9-drawer-tabs.png`).
4. 옵션 페이지 — 소싱처 관리 + 연결됨 배너 (`docs/screens/v42/e1-token-connected.png`).
5. (선택) 자동 번역 전/후 (`docs/screens/v39/D-translate-*.png`).

프로모 타일(선택, 440×280): v8 브릿지 마크 + 워드마크. 필수 아님(Unlisted).

---

## 4. 오너 액션 (심사 제출은 오너 클릭)

| # | 단계 | 화면/링크 | 결정·주의 |
|---|---|---|---|
| 1 | 개발자 등록 | chrome.google.com/webstore/devconsole | **1회 $5 등록비**(오너 결제). |
| 2 | 게시 명의 결정 | 동일 대시보드 | **명의 선택은 오너**: (a) 오너 개인 Google 계정 / (b) alaz 명의 계정. 확장 저작자 표기·문의 이메일이 이 명의로 노출됨. |
| 3 | 판매자 정보 | 대시보드 > Account | 연락 이메일 확인(현 `shanks8@hanmail.net` 또는 사업자 메일). |
| 4 | 제출 zip 받기 | GitHub(로그인) | **두 경로 중 택1**: (a) **즉시** — 최신 커밋의 Actions run > `extension-zip` 잡 > Artifacts `gogasujipgi-branch.zip`. (b) **영구** — `v*` 태그 푸시 시 Releases에 `gogabridj-collector-<tag>.zip` 자동 첨부(release.yml). 로컬은 `python scripts/build_extension_zip.py dist/goga.zip`. 현재 main 버전 **1.5.149**(manifest 무손대). |
| 5' | zip 업로드 | 대시보드 > New item | 위에서 받은 zip 업로드(manifest 루트 인식). |
| 5 | 등록정보 입력 | Store listing 탭 | 본 문서 §1·§3 복사·붙여넣기. 아이콘 128 자동 인식. |
| 6 | 권한 정당화 | Privacy practices 탭 | 본 문서 §2 표 항목별 입력 + 개인정보 URL. |
| 7 | 공개 범위 | Visibility | **Unlisted** 선택(검색 미노출·링크 설치). |
| 8 | 제출 | Submit for review | 심사 통상 수일. 승인 후 설치 링크를 셀러에게 배포. |

> ※ Unlisted라도 심사는 거친다. `<all_urls>` 사유(§2)를 정확히 입력하면 지연 위험이 준다.

---

## 5. 업데이트 흐름 (게시 후) — 요약, 상세 런북은 볼트 `런북/크롬 웹스토어 게시`

1. 확장 코드 변경 → `manifest.json` version bump(현행 관례, 테스트 핀 동반).
2. main 머지(배치 머지 관례와 동일 — 하루 1~2회 묶음).
3. `build_extension_zip.py`로 zip 생성(또는 CI 아티팩트).
4. 대시보드 > Package > Upload new package → **version이 스토어보다 높아야** 승인됨(manifest version이 곧 스토어 버전).
5. 승인 후 크롬이 **자동 업데이트** → "git pull→재로딩" 수동 루프 소멸.

> 보조 채널: CI zip(`gogasujipgi-branch.zip`)은 심사 전/개발용 '압축해제 로드'로 병존(오너 로컬 즉시 확인).
