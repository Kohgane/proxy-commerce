# v87-W10 — 서비스 안정성 트리아지 (긴급)

## 근원 (실측 확정)
- **워커 구성**: `gunicorn.conf.py` = **workers 2 · gthread · threads 4 → 동시 8슬롯**, timeout 120s.
- **동기 번역이 워커를 장기 점유**: 요청 경로 내 번역 체인(mymemory→papago→deepl→azure→openai, 각 10~30s timeout + 429 백오프)이 순차 실행 → **최악 한 항목 ~125s**, 벌크는 항목수 배수. 8슬롯이 금방 고갈 → **저부하(CPU~0%·메모리 25~40%)에서도 전면 저속**(오너 Render 실측과 일치 — 동기 I/O 블로킹).
- 증상 매핑: 드로어 간헐 로드 실패("네트워크 불안정")=워커 대기/타임아웃 · 화면 떴다-사라짐=요청 큐 적체.

## 실측 전후 (워커 점유 시간, ja 체인·각 프로바이더 timeout 소요 시뮬)
| | 워커 점유(한 항목) |
|---|---|
| BEFORE(무캡, timeout 120) | **50.0s** (5프로바이더×10s) — 실 최악 ~125s |
| AFTER(8초 캡) | **8.0s** |
- p50(정상 번역 첫 프로바이더 즉시 성공): ~0.5–1s, **캡 영향 0**(불변).
- p95(느린/실패 폴백): 50s+ → **≤8s(항목)** · 벌크 요청 **≤20s**.

## 수리 (체인 로직 무손대 — 시간 가드만)
1. **item2 요청 예산 캡**: `translate_product`에 요청 예산(env `TRANSLATE_REQUEST_BUDGET_SEC`=8) — 각 프로바이더 소켓 timeout을 **남은 예산으로 클램프**(`_clamp_timeout`), 예산 소진 시 다음 프로바이더 **시도 중단**(skipped 기록) 후 정직 실패 반환. 체인 순서·프로바이더 **불변**. AI 초안(`_describe_openai`)도 동일 캡.
2. **item2 벌크 요청 예산**: `collect_bulk_translate`에 요청 전체 예산(env `TRANSLATE_BULK_BUDGET_SEC`=20) — 소진 시 남은 항목은 **'지연(deferred)'** 정직 반환(원문 유지, 다음 재시도). 워커를 무한정 잡지 않음.
3. **item3 부분 요청 오류 = JSON**: `_wants_json_error`가 `Sec-Fetch-Dest: empty`(fetch/XHR)·`X-Requested-With: XMLHttpRequest`도 인식 → 드로어/AJAX 오류는 **JSON**(전체 페이지 HTML 중첩 렌더 금지). 문서 내비게이션(`Sec-Fetch-Dest: document`)은 기존 HTML 페이지 유지.

## item4 — W9 배포 확인
- 오너 실측: **라이브 = 61d51600 (W9) 배포 확인.** 따라서 배포가 1번 수리에 선행할 필요 없음(이미 최신).

## ja 재번역이 여전히 mymemory였던 이유 — 레코드 판독 결정표
W9 이후 레코드에 `detected_lang`·`translation_provider`·`translation_attempts`가 저장된다. 아래로 판독:
- **①감지 놓침**: `detected_lang != "ja"` (제목이 순수 라틴/로마자였던 경우). → route는 kana·han 1자면 ja이므로, 이 경우 제목에 CJK가 없었음.
- **②체인은 ja인데 폴백**: `detected_lang=="ja"` **and** `translation_provider=="mymemory"` → chain=[papago,deepl,azure,openai,mymemory]에서 **papago·deepl·azure·openai가 전부 실패**하고 mymemory(최후)가 성공한 것. **실패 사유는 `translation_attempts`의 각 provider `error` + `/admin/diagnostics` "번역 계측" `by_code`/최근 원 응답(W7a)** 에 있음(예: papago NCP 키/리전 오류=`auth`, 또는 **W10 이전 워커 혼잡으로 타임아웃**=`timeout`). ← **가장 유력**(키가 있는데 mymemory로 떨어졌다면 상위 프로바이더 실패가 원인).
- **③표시만 옛값**: `translation_provider`가 비었거나 옛 값 — 재번역이 실제로 안 돌고 목록 제목만 과거 mymemory 결과가 남은 경우(W9 뱃지 소거 전 레코드).
> 판독 위치: 그 상품의 `extra_json`(`translation_provider`·`detected_lang`·`translation_attempts`) 또는 `/admin/diagnostics` 번역 계측. ②면 papago 실패 `error`가 키/리전인지 timeout인지로 후속 결정.

## 배포 정책 (제안만 — 오너 결정, 강제 아님)
- 현재 자동배포는 **머지마다 즉시 재시작**(오너 활동 시간대에 세션 끊김·순단 유발 가능).
- 제안: **배치 머지**(하루 1~2회 묶음) 관례 — 급한 핫픽스만 즉시, 나머지는 저녁/새벽 배치. 코드 아님(운영 관례).

## 후속(제안) — 진짜 백그라운드 분리
캡은 워커 고갈을 **차단**(≤8s)하지만, 이상적 형태는 번역을 **백그라운드 작업**으로 빼고 즉시 응답(진행 중)+폴링. 이는 작업 저장소·폴링 계약·상태 전이 설계가 필요(별도 트랙). 이번 긴급 트리아지는 **캡으로 안정성 확보**(오너 '최소 8초 캡' 승인선), 백그라운드는 후속 스코프.
