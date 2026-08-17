# v87-W7 — 번역 다중 프로바이더 체인 + 병기 정책

## 오너 정책 (불변으로 기록)
- ① 상세 = 원문 + 한국어 **병기 허용**(동시 표기 OK). ② 제목 = 원문 유지 허용(키워드 번역/원문 무방).
- ③ KO/EN 혼재 금지 원칙은 **콘솔 UI 언어에 한정** — 상품 문안 병기는 예외.
- 번역 프로바이더 여러 개를 **체인**으로, 하나 실패하면 다음 시도.

## 1항(W7a) — OpenAI '미설정' 오귀인 수리 + 실패 사유 3분
**근원 한 줄**: env명 불일치가 아니다(OPENAI_API_KEY·OPENAI_MODEL 표준명 일치·env_present는 정제값 기반 정상).
AI 초안이 **OpenAI 호출 실패 시에도 provider="stub"로 폴백**해 UI(`collect_preview.html`)가 `provider!=='openai'`를
전부 "AI 키가 설정되지 않아…"로 뭉갠 것 — **키 있는데 호출 실패(모델·401·타임아웃)를 키 부재로 오귀인**.
- **수리**: `generate_description`이 `draft_status` 3분 반환 — `openai`(성공) / `no_openai_key`(env_present False) /
  `openai_error`(키 있으나 호출 실패 + `draft_error` 사유). 실패는 `translate_stats`에 적재(계측). 엔드포인트·UI가
  3분 문구 표시(키 미설정 / 키 있으나 실패+사유 / 성공). 키 값·마스킹 로그 0.

## 0. W7 회수 갱신 (오너 env 3종 등록·재배포 완료 — 2026-08-16)
오너가 `DEEPL_API_KEY`(기존재)·`AZURE_TRANSLATOR_KEY`+`AZURE_TRANSLATOR_REGION`·`NCP_PAPAGO_CLIENT_ID/SECRET`·`OPENAI_API_KEY`+`OPENAI_MODEL`(gpt-4o-mini)을 전부 등록. **후보 표 → 실배선 완료.**
- **확정 체인 순서**: `mymemory`(무료) → `papago`(NCP 공식) → `deepl` → `azure`(공식, 소스 자동감지) → `openai`(최후). 각 프로바이더는 해당 env가 있을 때만 체인 합류(`_provider_chain` 필터).
- **공식 엔드포인트만**(비공식/ToS 위반 0): Papago=`papago.apigw.ntruss.com/nmt/v1/translation`(헤더 `x-ncp-apigw-api-key-id`/`x-ncp-apigw-api-key`), Azure=`api.cognitive.microsofttranslator.com/translate?api-version=3.0&to=ko`(헤더 `Ocp-Apim-Subscription-Key`/`-Region`).
- **기존 DEEPL_API_KEY 경로 관계 = 흡수(병행 아님)**: 종전에도 `_translate_deepl`은 있었으나 이제 체인의 2·3순위 한 단계로 들어가 순차 폴백에 포함. 별도 DeepL 분기 없음(단일 체인).
- 계약 `test_v87_w7b_papago_azure`(5): 체인 순서·Papago 양키 필수·공식 엔드포인트·확정 env명 헤더·papago 실패→azure 폴백.

## 1. 프로바이더 체인
`translate_product`를 **체인**으로 재작성. 기본 순서(무료 우선 → 저가/키필요 → OpenAI 최후):
`mymemory` → `papago` → `deepl` → `azure` → `openai`. 첫 성공 반환, 실패 시 다음.
- **env 오버라이드** `TRANSLATE_PROVIDER_CHAIN`(쉼표): 예 `openai,mymemory`로 품질 우선. `TRANSLATE_DISABLE_MYMEMORY=1`로 무료 끄기.
- **MyMemory**(https://api.mymemory.translated.net) — 무키·무가입 무료 MT. 스크립트 기반 원문 언어 추정(ja/zh/en→ko).
- 레코드에 **사용 프로바이더**(`translation_provider`) + **시도 이력**(`translation_attempts:[{provider,ok,error}]`) 기록 → 드로어 표시.
- 전부 실패 시 원문 유지 + `{last}-fallback` + `translate_error`(정직 실패, W6 뱃지·재시도 연동).

### 무키·무가입 (지금 체인에 넣음)
| 프로바이더 | 무료 한도 | 신뢰도 | 채택 |
|---|---|---|---|
| **MyMemory** | ~1,000 words/day(익명)·~50,000/day(이메일 파라미터) | 공식 무료 API·안정. 품질 보통(일→한 준수) | **구현됨**(체인 무료 1순위) |
| **LibreTranslate 공용** | 공용 인스턴스는 현재 **키 요구/불안정**(libretranslate.com 유료화) | 낮음(공용 불안정·차단 리스크) | **미채택**(자가호스팅 시 env URL로 합류 — 별도) |

### 키/가입 필요 (보고만 — 임의 가입·발급 금지, 오너 결정 게이트)
| 프로바이더 | 무료 한도 | 가입/키 | 기존 키 재사용? | 일→한 품질 | 채택 방법 |
|---|---|---|---|---|---|
| **DeepL API Free** | 50만 자/월 | 가입 + `DEEPL_API_KEY` | — | 상급 | **키만 넣으면 즉시 체인 합류**(코드 지원). 상위 배치 권장 |
| **Azure Translator(F0)** | **200만 자/월 무료** | Azure 가입 + 키 + 리전 | — | 상급 | 배선 별도(env `AZURE_TRANSLATOR_KEY/REGION`). 무료 한도 최대 |
| **Papago (NCP)** | 무료 한도 축소/종량 | **NCP(네이버클라우드) 별도 가입** + `X-NCP-APIGW-API-KEY(-ID)` | **불가** — 기존 `NAVER_CLIENT_ID`/`NAVER_SEARCH_*`는 developers.naver.com/commerce 키라 **NCP와 별개**(재사용 안 됨) | **최상급**(한↔일) | NCP 가입·키 발급 후 배선(별도). 채택 시 체인 **최상위** 후보 |
| **Google Cloud Translation** | 첫 50만 자/월 무료 후 종량 | GCP 가입+결제+키 | — | 상급 | 배선 별도 |
> **권장 확정(근거)**: 일→한 품질은 **Papago·DeepL이 최상급**. 즉시 가능은 **DeepL(키만)**·**Azure(월 200만자 최대 무료)**. Papago는 NCP 별도 가입 필수(기존 NAVER 키 재사용 불가 — 실증). 오너가 DeepL/Azure 키를 주면 체인 상위 배치(`TRANSLATE_PROVIDER_CHAIN=deepl,mymemory,openai` 등).

## 2. 상세 병기
`compose_bilingual(ko, orig)` = 한국어 상단 + `───── 원문 (Original) ─────` + 원문 하단. 둘이 같거나 한쪽 비면 하나만.
- **저장 필드는 순수 유지**(`description`=원문, `description_ko`=번역) — 원문 항상 보존.
- **마켓 등록 시** `collect_upload`이 편집본+저장 원문으로 병기 합성 → **병기본이 마켓에 나감**.
- **드로어**: '마켓 전송 미리보기 — 한국어+원문 병기'(읽기 전용) + '번역 프로바이더: {name} (체인 N회)'.

## 3. 제목 정책
번역 실패·미시도로 원문 유지 시 목록 뱃지 = **'원문'**(정책 허용, W6), **실제 오류만 '번역 실패'** 뱃지. 시도 이력은 기록(체인 attempts).

## 4. AI 초안 무키 폴백 품질
`_structured_draft`가 `description`(원문 상세)을 받아 **원문 스펙 라인을 통째 보존**('■ 원문 상세'), UI 쓰레기·초단문·중복 라인 제외. **숫자 조각 리스트 금지**. (키 설정 후엔 W5 OpenAI 경로가 본선.)

## 5. 확장 업데이트 채널 (문서·안내 — 확장 코드 불가침)
확장 설치 페이지에 **버전 배너(manifest 버전) + 최신 내려받기 + chrome://extensions 새로고침 안내** 추가(서버 템플릿).
`extension-zip` CI 잡이 매 커밋 zip 빌드. **백로그 이슈 #603**(웹스토어 게시 or CI 아티팩트 자동 배포 — 오너 결정 게이트).

## 완료 4항 + 해시
1. **계약 그린**: `tests/test_v87_w7_translate_chain.py`(10) — 체인 순서·언어감지·폴백+attempts·전부실패 정직·
   extension_api attempts 저장·compose_bilingual·collect_upload 병기·드로어·무키 초안 원문라인·확장 배너.
   + 기존 v64/v66/w6 체인 정합 갱신. 전 스위트 그린.
2. **회귀 0**: 번역·업로드·초안 관련 그린.
3. **버전/해시**: 서버 전용(확장 무변경 — item5는 서버 템플릿). manifest 범프 없음.
4. **최종 판정 = 오너**: 키 설정·재배포 후 TSUMUGI 재번역(체인) + AI 초안 재클릭 → 병기 상세·프로바이더 표시 확인.

## 금지 구조 준수
- **번역 무료 쿼터 회계 무손대**(체인·계측은 별개) · **AI 예산 존중**(계약 requests 모킹, 실 API 호출 0) ·
  **유료 가입 임의 진행 0**(후보는 표로 보고만) · **확장 코드 불가침**(item5 서버 템플릿·문서만).

## 3. W7a 재개정 — '한도 초과' 발화 주체 4분 (오너 실증: OpenAI 잔액 $22.37 → 크레딧 고갈 기각)
현행 "사용량·결제 한도 초과" 한 줄이 **서로 다른 4가지를 뭉쳤다**. `classify_translate_reason(exc)`로 (사유코드, 문구) 4분:

| 코드 | 발화 주체 | 문구(핵심) |
|---|---|---|
| `budget` | **서버 내부 예산 가드**(AI_MONTHLY_BUDGET_USD) | "**서버 월 예산** 상한 … (**OpenAI 잔액 아님** · 상향/대기)" |
| `quota` | 프로바이더 429 `insufficient_quota` | "프로바이더 **크레딧·결제** 소진(플랜·결제 확인)" |
| `rate_limit` | 프로바이더 429 rate limit | "**요청 속도 제한**(**결제 아님** · 잠시 후 자동 재시도)" |
| `auth` | 401/403 | "API **키**가 잘못됐거나 만료" |

- **핵심 수리**: 오너가 본 429는 잔액 $22.37이므로 `rate_limit`(속도 제한) — 이제 "결제 아님"으로 명시(OpenAI 지갑 뒤지지 않게). 내부 가드 차단이면 반드시 "서버 월 예산".
- 각 사유는 별 문구 → `translate_stats`에 사유별 분리 집계(distinct reason).
- **발화 주체 실측**: 상품 번역 경로(`translate_product`)는 예산 가드 **미경유**(copywriter/AI카피만 `BudgetExceededError` — views.py 402 응답도 "서버 월 예산 … OpenAI 잔액 아님"으로 명시). 즉 번역 실패는 프로바이더 사유(rate_limit/quota/auth), 예산 차단은 AI카피 경로.
- **읽기전용 노출**: `/admin/diagnostics`에 "🧮 서버 AI 예산 가드" 카드(이번 달 누계·상한·%·차단 여부). 기존 `/seller/ai-budget` JSON도 존재.
- 계약 `test_v87_w7a_cause_split`(8): 4코드 유일·budget "서버 월 예산"·rate_limit "결제 아님"·quota 결제·auth 키·diagnostics 노출·빌더 읽기전용.

## 4. W7a 조사 범위 확정 (오너 구성 결백 실증: 예산 100 / OpenAI 한도 100 / 키 일치 / 잔액 $22.37)
"한도 초과" 발화 주체는 코드 내부 → 2갈래 조사.

### ① 내부 예산 추적기 감사 (오계산 여부 + 현재 누계 실측)
- **산식**: `BudgetGuard.month_to_date()` = Google Sheets `ai_spend` 워크시트에서 `date`가 이번 달(`YYYY-MM` 접두)인 행의 `cost_usd` **합**.
- **단위**: **USD**(Decimal). 기록측(copywriter `budget.record(total_cost)`)도 **USD**로 적재 — 달러/센트 혼용 **없음**(오계산 아님).
- **리셋**: 별도 리셋 잡 없음 — `date` 문자열 월접두 필터로 **월 경계 자동 구분**.
- **저장 위치**: **Google Sheets `ai_spend`** — **W3 PG 이관 대상 아님**(W3=collect_history·user_tokens·orders·market_links만). 시트 미연결/`ai_spend` 부재면 `month_to_date=0` → 절대 차단 안 함.
- **현재 누계 실측(이 컨테이너)**: `used_usd=0.00 / limit=100.00 / pct=0.0% / status=ok / blocked=False`. (서버 실값은 `/admin/diagnostics` "🧮 서버 AI 예산 가드" 카드가 라이브로 표기 — ai_spend 내용에 의존.)
- **결정적 사실**: 예산 가드는 **AICopywriter(/ai-create) 경로만** 게이트한다. **상품 번역(`translate_product`)·AI 상세초안(`generate_description`)은 예산 가드 미경유** → 번역/초안의 "한도 초과"는 예산 추적기가 **아니다**.

### ② 프로바이더 응답 오표기 → 원 응답 계측 적재 (branch②)
- 종전 429를 "사용량·결제 한도"로 뭉침(#609에서 rate_limit/quota/auth/budget 4분). 이제 **원 응답까지 보존**:
  `record_translate_failure(exc, provider)`가 `raw_error_meta`로 **HTTP status + 응답 바디(300자)**를 `translate_stats.recent`에, 사유코드를 `by_code`에 적재(시크릿 없음, 에러 바디만).
- 전 프로바이더(mymemory·papago·deepl·azure·openai·openai-draft) 실패 경로가 이 함수 경유 → **다음 실패부터 원문 사유가 남는다**.
- **읽기전용 노출**: `/admin/diagnostics` "🌐 번역 계측" 카드 = 사유코드별 카운트 + 최근 실패 8건(프로바이더·코드·HTTP·원 응답 바디). '한도 초과' 오귀인을 원 응답과 대조.
- 계약 `test_v87_w7a_raw_stats`(6): status·body 추출·원 응답 보존·링버퍼 상한·코드 분리·진단 노출·빌더 읽기전용.

**결론(발화 주체)**: 오너의 번역 429는 **OpenAI rate_limit**(잔액 $22 → 결제 아님)이 "결제 한도"로 오표기된 것. 예산 추적기(정상·미차단·번역 미경유)는 무관. 이제 원 응답이 계측에 남아 재발 시 즉시 대조.
