# v71 STEP1 — 통화 로케일 추론 (버그① 통화 빈 값)

## 증상 (오너 스냅샷 실측)
- 테무 Tier1 작동 확정(가격 11235·갤러리 22·옵션·리뷰 tier1 채택)인데 **통화 필드가 비어** sanity 게이트가 `needs_check`로 가격을 누락 처리 → '가격 미수집'의 실체.

## 수리 (`kgp-extractor.js`)
1. **통화 판정 사다리** (`_localeCurrency()`):
   - tier1 JSON 통화(`j.currency`) → DOM 통화 기호(`_domPrice`) → **어댑터 로케일 기본값** → 그래도 불명이면 기존 "통화 미확인" 유지.
   - 로케일 기본값 근거(무근거 추정 0): `html lang` / 경로(`/kr`·`/jp`) / 도메인 TLD.
     - ko·`/kr`·`kr.` → **KRW** (temu.com/kr·ko.aliexpress) / ja·`/jp`·`.co.jp` → **JPY** (amazon.co.jp·rakuten·yoshida·yahoo재팬) / zh·`.cn` → **CNY** (taobao·tmall·1688) / amazon.co.uk → GBP / amazon.de·fr·it·es·nl → EUR / amazon.* 기본 → USD.
2. **적용 위치**: 가격은 있는데 통화만 빌 때만(`if (price && !currency)`) 3번째 사다리로 채움 → sanity의 "통화 미확인" needs_check 해제.
3. **근거 추적**: 로케일 채택 시 수집 로그 `가격=11235 KRW(locale) (ok)` — 어느 근거인지 표기.

## 판정
- 가드 `tests/test_v71_currency_locale.py` (3): 소스계약 + **node로 사다리 실증**(temu/kr·ko.ali→KRW / amazon.com→USD / amazon.co.jp·rakuten·yoshida·yahoo→JPY / taobao→CNY / amazon.co.uk→GBP·de→EUR / 근거없음→"").
- **실페이지 하네스** `synthetic-temu-detail`(JSON-LD price 11235·통화 빔·lang ko·temu.com/kr): 실 크로미움에서 **price=11235·currency=KRW·needs_check 해제** 그린.
- manifest 1.5.82. 전체 그린.
- **실기기(오너 몫)**: 확장 1.5.82 재로딩 → 테무 1건 → 드로어 가격 탭 KRW 채움 + F12 `KRW(locale)` 로그. (개발 프록시 라이브 테무 차단.)

## 금지 준수
- 통화 무근거 추정 저장 0(로케일 표=근거) · 가짜 성공 0(근거 없으면 통화 미확인 유지).

적용 스킬: (확장 추출 로직 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
