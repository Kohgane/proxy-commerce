# D0 — 이미지 내 텍스트 번역 공급사 실측 (2026-09-13)

목표: 중국어(및 일/영) 텍스트가 박힌 상품 이미지를 **자연스러운 한국어 이미지**로.
원칙 둘 — **만들지 말고 사고, 실측으로 고른다.** 자체 OCR+인페인팅 구축은 하지 않는다.

---

## ⚠️ 이 문서가 어디까지 실측인가 (먼저 읽으세요)

이 세션의 네트워크가 **공급사 문서 사이트를 막습니다.** 실측:

```
000  help.aliyun.com          000  www.alibabacloud.com
000  cloud.tencent.com        000  www.tencentcloud.com      000  intl.cloud.tencent.com
000  fanyi-api.baidu.com      000  ai.youdao.com             000  openapi.youdao.com
200  cloud.google.com
```

프록시 상태: `gateway answered 403 to CONNECT (policy denial)` — 정책 차단입니다.

**그래서 기억으로 쓰지 않았습니다.** 대신 도달 가능한 **공식 SDK 소스**(GitHub)에서
요청·응답 스키마를 원문으로 읽었습니다. 스키마는 문서보다 오히려 정확합니다 —
공급사가 실제로 그 필드로 통신하기 때문입니다.

| 항목 | 어디까지 |
|---|---|
| 액션 이름 · 요청/응답 필드 · 지원 언어 · 인페인팅 여부 | ✅ **공식 SDK 소스로 확정** |
| 텐센트 가입 요건 | ✅ **오너 실측(2026-09-14)** — 한국 리전은 한국 PG 카드 바인딩 필수 |
| 장당 단가 · 월 무료량 · RPM | ❌ **미확인** — 문서 사이트가 막힘 |
| 바이두 · 유다오 | ❌ **미확인** — 공식 공개 SDK를 찾지 못했고 문서도 막힘 |

미확인 칸은 **오너가 열어야 할 URL**을 함께 적었습니다. 채워 주시면 표가 완성됩니다.

---

## 1. 공급사 비교 (확정분)

### ① 텐센트 클라우드 TMT — `ImageTranslateLLM` ★ 현행 확인

출처: `TencentCloud/tencentcloud-sdk-python-intl-en`
`tencentcloud/tmt/v20180321/{models.py, tmt_client.py}` (공식 국제판 SDK)

```
_endpoint   = 'tmt.intl.tencentcloudapi.com'
_apiVersion = '2018-03-21'
_service    = 'tmt'
액션        : ImageTranslateLLM        ← 국제판 SDK의 유일한 액션
```

> **중요 — 오너가 지목한 `ImageTranslate`는 현행 SDK에 없습니다.**
> 국제판·중국판 SDK 모두 `ImageTranslateLLM`만 노출합니다. 옛 액션 이름으로 붙이면
> 안 됩니다. (이것이 「현행 여부 확인」이 필요했던 이유입니다.)

**요청** (`ImageTranslateLLMRequest`)

| 필드 | 뜻 |
|---|---|
| `Data` | 이미지 base64. **인코딩 후 9MB 이하.** 600×800 이상 권장. PNG/JPG/JPEG |
| `Url` | 이미지 URL(쓰면 `Data`에 `""`). 10MB 미만 |
| `Target` | 대상 언어 — **`ko` 지원**. 총 18종(zh·zh-TW·zh-HK·en·ja·**ko**·th·vi·ru·de·fr·ar·es·it·id·ms·pt·tr) |
| `Mode` | `0` = pro(기본), `1` = lite |

**`Source`(원본 언어) 파라미터가 없습니다 — 자동 감지입니다.** 즉 zh→ko가 **직접**이고
영어 경유가 아닙니다(응답이 감지된 `Source`를 돌려줍니다).

**응답** (`ImageTranslateLLMResponse`)

| 필드 | 뜻 |
|---|---|
| `Data` | **번역된 이미지 base64 (JPG)** ← 렌더까지 해서 돌려준다 = 인페인팅 있음 |
| `Source` / `Target` | 감지된 원본 언어 / 대상 언어 |
| `SourceText` / `TargetText` | 이미지 안 원문 전체 / 번역문 전체 |
| `Angle` | 이미지 기울기(0–359) |
| `TransDetails` | 줄별 상세(`TransDetail`, 좌표 `BoundingBox`·`Coord` 포함) |
| `RequestId` | 문제 추적용 |

`TargetText`가 따로 오는 것이 우리에게 큽니다 — **번역문을 이미지에 굽기 전에
금칙어 검사를 할 수 있습니다**(D0-4 ③).

**⚠️ 가입 요건 (오너 실측 2026-09-14)**

| 리전 | 가입 |
|---|---|
| **한국 리전** | **한국 PG 카드 바인딩 필수 — Skip 불가** |
| 미국 리전 | **우회 가능한지 검토 중**(오너) |

이 한 줄이 **추천을 뒤집을 수 있습니다.** 스키마가 아무리 맞아도 **계정을 못 만들면 못 씁니다** —
D0-1에서 「국제 계정 가입 요건」을 따로 물으라고 한 이유가 이것이었고, 저는 그 칸을
「미확인」으로 비워 둔 채 텐센트를 1번으로 꼽았습니다. 그 순위는 이 칸이 채워져야 확정됩니다.

**미확인(남음)**: 단가 · 무료량 · RPM.
→ 오너 확인 URL: `https://www.tencentcloud.com/document/product/1130` (가격 탭)

---

### ② 알리바바 클라우드 기계번역(alimt) — `TranslateImage` 계열

출처: `aliyun/alibabacloud-python-sdk`
`alimt-20181012/alibabacloud_alimt20181012/models.py` (공식 SDK)

액션이 **넷**입니다 — 동기 1 + 배치 2 + 조회 1:

| 액션 | 쓰임 |
|---|---|
| `TranslateImage` | 동기 1장 |
| `TranslateImageBatch` → `GetTranslateImageBatchResult` | **배치**(우리 파이프라인에 맞음) |
| `CreateImageTranslateTask` → `GetImageTranslateTask` | 비동기 작업 |
| `GetImageTranslate` | 조회(OCR 결과 포함) |

**요청** `TranslateImageRequest`: `image_url` | `image_base_64`, `source_language`,
`target_language`, `field`(분야 힌트), `ext`
**배치** `TranslateImageBatchRequest`: `image_urls`(복수), `source_language`,
`target_language`, `custom_task_id`, `field`, `ext`

**응답** `TranslateImageResponseBodyData` / `…BatchResultResponseBodyDataResult`:

| 필드 | 뜻 |
|---|---|
| `final_image_url` | **최종 번역 이미지** |
| `in_painting_url` | **인페인팅(글자 지운 배경)만** — 따로 받을 수 있다 |
| `template_json` | 재편집용 템플릿(글자·위치) |
| `source_image_url` · `success` · `code` · `message` | 배치 결과 식별·성패 |

> `in_painting_url` + `template_json`이 **따로** 온다는 것이 강점입니다 —
> 번역문이 마음에 안 들 때 **배경은 살리고 글자만 다시 얹을** 수 있습니다.
> 텐센트는 구운 JPG 하나만 옵니다.

`source_language`가 **요청에 있습니다** — zh 고정으로 보낼 수 있고, `auto`가 되는지는 미확인.

**미확인**: zh→ko 직접 지원 여부(언어 목록) · 단가 · 무료량 · RPM · 가입 요건.
→ 오너 확인 URL: `https://www.alibabacloud.com/help/en/machine-translation/`

※ 별개 제품으로 **Model Studio의 `qwen-mt-image`**(LLM 기반 이미지 번역)가 있습니다.
검색 결과상 중/영 → 한국어 포함 12개 언어, 결과 이미지는 OSS에 **24시간만** 유효,
계정당 **5 RPM**이라고 소개됩니다 — 다만 이건 **검색 결과 발췌이지 원문 확인이 아닙니다.**
→ 오너 확인 URL: `https://www.alibabacloud.com/help/en/model-studio/qwen-mt-image-api`

---

### ③ 바이두 · ④ 유다오 — **확인 불가**

공식 공개 SDK를 GitHub에서 찾지 못했고 문서 사이트가 막힙니다.
둘 다 중국 본토 서비스라 **실명 인증·중국 결제수단**이 필요할 가능성이 높지만,
**그것도 확인한 사실이 아니라 추정이라 표에 쓰지 않습니다.**

→ 오너 확인 URL: 바이두 `https://fanyi-api.baidu.com/doc/25` ·
유다오 `https://ai.youdao.com/DOCSIRMA/html/trans/api/tup/index.html`

---

### ⑤ 구글 Cloud Vision + Translate — **비교 기준선(인페인팅 없음)**

Vision은 텍스트와 좌표를, Translate는 번역문을 돌려줍니다. **번역된 이미지를
만들어 주지 않습니다** — 지우고 다시 얹는 일은 우리가 해야 하고, 그게 바로
「자체 구축 금지」로 접은 부분입니다. 품질 비교의 바닥선으로만 씁니다.

---

## 2. 오너 결정 대기 (계정은 오너가)

**추천: 텐센트 `ImageTranslateLLM` 1곳으로 시작, 알리바바 alimt를 2번째 후보로.**

근거(확정된 것만):

| | 텐센트 | 알리바바 |
|---|---|---|
| zh→ko 직접 | ✅ (자동 감지 + `Target=ko`) | ❓ 언어 목록 미확인 |
| 렌더된 번역 이미지 | ✅ `Data`(JPG) | ✅ `final_image_url` |
| 배경만 따로 | ❌ | ✅ `in_painting_url` |
| 재편집 템플릿 | ❌ | ✅ `template_json` |
| 번역문 텍스트 별도 | ✅ `TargetText` (금칙어 검사 가능) | ❓ |
| 배치 | ❌ (1장씩) | ✅ |
| 액션 현행성 | ✅ 확인 | ✅ 확인 |

텐센트를 먼저 꼽는 이유는 **zh→ko가 확정**이고 `TargetText`로 **금칙어 검사가 가능**해서입니다.
알리바바는 `in_painting_url` + `template_json`이 매력적이라, 텐센트 품질이 모자라면 바로 2번째로.

### ⚠️ 이 추천은 **가입 요건에 걸려 있습니다** (2026-09-14 실측 반영)

텐센트 **한국 리전은 한국 PG 카드 바인딩이 필수**(Skip 불가)입니다. 오너가 미국 리전 우회를
검토 중입니다. 그래서 순위는 이렇게 갈립니다:

| 미국 리전 가입이 | 1번 | 2번 |
|---|---|---|
| **된다면** | 텐센트(zh→ko 확정 · `TargetText`로 금칙어 검사) | 알리바바 |
| **안 된다면** | **알리바바** — 대신 zh→ko 언어 목록을 **먼저 확인**해야 합니다(현재 ❓) | (없음) |

> **좋은 API보다 쓸 수 있는 API가 먼저입니다.** 스키마 비교는 가입이 되는 곳들 사이에서만
> 의미가 있습니다 — 못 만드는 계정의 스키마가 아무리 좋아도 0점입니다.

알리바바로 가게 되면 **먼저 확인할 것**은 zh→ko 지원 여부 하나입니다
(요청에 `source_language`/`target_language`가 있으니 값 목록만 확인하면 됩니다).

**계정·결제는 오너가 합니다. 이 세션에서 계정을 만들지 않았습니다.**

---

## 3. 채점 준비 (계정이 오면 바로)

### 픽스처 12장

| 상품 | 장수 | 성격 |
|---|---|---|
| `617129397971` (SPORTLINK) | 5 | **로고 + 큰 중문 + 빨간 주의문** — 어려운 쪽 |
| `946378497679` (슬리퍼) | 5 | 텍스트 적음 — 쉬운 쪽 |
| 상세 이미지 | 2 | **텍스트 빽빽** — 레이아웃 붕괴 시험 |

> 이 세션에서는 **이미지를 내려받을 수 없습니다**(타오바오 CDN도 프록시가 막습니다).
> 픽스처는 보강(확장)이 채운 뒤 서버 저장본에서 가져옵니다 — 그래서 D0-3은
> **보강 완료 이후**에 돕니다. 지금 순서상 그게 자연스럽습니다.

### 채점표 (각 1~5, 장당)

| 축 | 무엇을 보나 |
|---|---|
| 번역 정확도 | 뜻이 맞나. 상품명·스펙 숫자가 살아 있나 |
| 배경 복원 | 글자 지운 자리가 자연스럽나(번짐·잔상·색 끊김) |
| 폰트/정렬 | 한국어가 칸에 맞나. 줄바꿈·잘림·겹침 |
| 로고·워터마크 보존 | **브랜드 로고를 번역·삭제하지 않았나** |
| 금칙어 발생 | 번역문에 쿠팡 금칙어가 생겼나 |

장당 단가·응답시간은 **실측**해서 같이 적습니다.

### 반례 미리 검사 (D0-4)

1. **텍스트 비율 30%↑ 상세 이미지** — 레이아웃이 무너지는지. 무너지면 그 장은 `skipped`로 두고
   원본을 쓴다(억지로 번역한 이미지가 원본보다 나쁘면 안 하느니만 못하다).
2. **브랜드 로고** — 번역하거나 지우면 **상표권 반려가 재발한다**. 로고를 건드리는 공급사는
   그 사실만으로 탈락 후보다.
3. **마케팅어** — `爆款`·`必备` 류가 「최고」·「필수」로 직역되면 쿠팡 금칙어다.
   → **번역 후 금칙어 필터 통과를 필수 단계로** 둔다(아래 파이프라인 ④).

---

## 4. 파이프라인 위치 (설계 — 코드는 D1)

```
보강 완료(이미지 확보)
   ↓
① 이미지 2장 규칙 (기존 등록 규칙)
   ↓
② 장별 텍스트 유무 판정 → 텍스트 없으면 skipped(원본 그대로, 돈 안 씀)
   ↓
③ 번역 호출 (장별)
   ↓
④ 금칙어 검사 ← TargetText 기준. 걸리면 그 장 failed(원본 유지)
   ↓
⑤ 등록 — images_ko 우선, 없으면 images
```

### 저장 규칙

| 필드 | 뜻 |
|---|---|
| `images` | **원본 — 영구 보존.** 절대 덮어쓰지 않는다 |
| `images_ko` | 번역본(장별) |
| `images_ko_state` | 장별 `done` / `failed` / `skipped`(텍스트 없음) |
| `images_ko_reason` | failed·skipped 사유(금칙어·레이아웃 붕괴·API 오류) |
| `images_ko_vendor` | 어느 공급사가 만들었나(나중에 재처리할 때 필요) |

> **원본을 덮어쓰지 않는 이유**: 번역이 마음에 안 들 때 되돌릴 데가 있어야 하고,
> 공급사를 바꿔 다시 돌릴 때도 원본이 유일한 진본입니다.
> (C-F13-3에서 이미 같은 이유로 저장본을 따로 두었습니다.)

등록 시 `images_ko` 우선, 그 장이 `done`이 아니면 그 장만 원본으로 — **장 단위**입니다.
전부 아니면 전부가 아닙니다.

---

## 5. 비용 추적 (필드 설계 — 요금제는 D3)

| 필드 | 뜻 |
|---|---|
| `image_tr_pages` | 이 상품에서 번역한 장수 |
| `image_tr_vendor` | 공급사 |
| `image_tr_cost_micros` | 원가(마이크로 단위 정수 — 부동소수 반올림 누적 방지) |
| `image_tr_at` | 시각 |

사용자별 집계는 이 행들을 더해서 냅니다 — **따로 카운터를 두지 않습니다**
(카운터와 실제가 갈리면 어느 쪽이 맞는지 알 수 없게 됩니다).

---

## 다음 (오너 액션)

1. **텐센트 미국 리전 가입 가능 여부** — 이게 1번을 정합니다(한국 리전은 카드 바인딩 필수 확정).
   안 되면 알리바바로 가고, 그때는 **zh→ko 지원 여부**를 먼저 확인해 주세요.
2. 남은 **미확인 칸**(단가·무료량·RPM)을 문서에서 확인 → 이 표에 채움
3. 공급사 **1곳(최대 2곳)** 선택 → 계정·결제
4. 키가 오면 D0-3(12장 채점) — 콘솔 임시 화면에 원본/번역 나란히
