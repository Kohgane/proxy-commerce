# #617 드로어 개별 [한국어로 번역] 원문 소스 — 실측 증빙

드로어 개별 [한국어로 번역] 버튼(`collect_preview.html`)은 `/seller/collect/bulk-translate`를 단일 `item_ids`로 호출한다. W11 item①은 **제목** 재번역 소스를 원본(`title_en/title`)으로 고쳤으나 **상세** 소스는 `extra.description or extra.description_ko`라 원본이 없으면 **표시 번역본(description_ko, 한글)을 소스**로 써 한글→한글 재번역(상용구 잔존·왜곡)이 됐다.

## 근원 (실측 — test client 프로브)
| 케이스 | 상세 소스 (BEFORE) | 상세 소스 (AFTER) |
|---|---|---|
| A: `extra.description` 원본 있음 | `元の説明ＪＰ`(원본) ✓ | `元の説明ＪＰ`(원본) ✓ |
| B: 원본 없고 `description_ko`만 | **`이미번역된한글설명`(한글!)** ✗ | **빈값**(한글 소스 미전송) ✓ |

## 수리 (W11 item① 제목과 동형)
- 상세 재번역 소스 = **원본(`description`)만** — `description_ko`는 소스에서 제외.
- 원본이 없으면 소스 빈값 → 번역 미실행, **기존 `description_ko` 보존**(빈값 클로버 금지).

## 실측 후 (test client)
- CASE A: `description_ko` = 새 번역(원본에서). CASE B: `description_ko` = `보존되어야할한글설명`(기존 보존, 클로버 0).
- 회귀 0: W11·W9·W6 번역 계약 그린. 서버 로직 — UI 렌더 변경 없음(백엔드).
계약 `test_v87_617_drawer_translate_source`(4: 소스계약·드로어 엔드포인트·CASE A/B 실측).
