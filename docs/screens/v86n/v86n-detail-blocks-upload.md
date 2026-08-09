# v86-N — 드로어 '상세페이지 꾸미기' → 마켓 실반영 (description_html 배선)

## 결함 (정직 데이터 위반: 저장-후-미사용)
collect_preview 드로어 [상세페이지] 탭의 **v40-C 블록 에디터**(마켓 프리셋 공통/쿠팡/스스/
Shopify/멀티샵 + 텍스트·이미지·강조박스·구분선 블록 + 실시간 미리보기)는 `detail_blocks`를
`views.py`가 저장은 했으나, **업로드 경로 어디서도 소비하지 않았다.**

- 채널 브리지 `to_collected`(단일 관문): `description_html = pd.description_html or pd.description`
  — **`detail_blocks`를 보지 않음.**
- 쿠팡 `_build_contents`: `description_html` 비면 **제목으로 폴백**(plain description도 아님).

→ 셀러가 상세페이지를 꾸미고 **미리보기까지 확인**한 뒤 저장·등록해도, 그 꾸미기가 마켓
등록 상세에 **조용히 유실**. 미리보기가 실제 등록물과 불일치(가짜 미리보기).

※ plain `description`은 브리지 폴백(line 74)으로 이미 반영됨(유실 아님) — 결함은 **블록 한정**.

## 수리
`upload_dispatcher._payload_for_market(product_data, market)`(마켓별 페이로드 복제 지점)에서
`detail_blocks`를 **이 마켓의 `description_html`로 렌더**:

- 마켓 오버라이드(`detail_blocks[market]`)가 있으면 그것을, 없으면 공통(`common`)을 렌더.
- 드로어 미리보기 `dpPreview`와 **동일 시맨틱**(text=`<p>`, highlight=`<div>`, image=`<img>`,
  divider=`<hr>`) → **'미리보기 = 실제 등록물'** 성립.
- 내용 전량 이스케이프(마크업 주입 0). 블록 없거나 렌더 결과 비면 미설정 → 기존 plain
  description 폴백 유지(**회귀 0**). AI 경로는 `detail_blocks`가 없어 무영향.
- 신규 UI·중복 에디터 0 — **기존 v40-C 에디터·미리보기를 실제로 작동**시키는 배선만.

소비 마켓: `description_html`을 읽는 **쿠팡·스마트스토어·11번가**(브리지 경유).
※ Shopify(plain `description` 사용)·WooCommerce(현재 상세설명 필드 자체 미배선)의 상세페이지
소비는 **별건 후속**(shopify body_html·woo description 매핑) — 이 PR 범위 밖(과확장·회귀 회피).
※ 옵션가표는 per-option-price 파이프라인 소비가 없어 **미구현(정직)** — 오너 스펙/파이프라인
지원 시 별건.

## before/after (실행 증거 — 쿠팡 contents)
동일 블록(자동 3단 우산 · 8K 살대 / 무료배송 강조 / 상세이미지 / 소재)으로:

**BEFORE** (배선 전 재현: `detail_blocks` 미소비)
```
coupang description_html: ''
coupang contents[0].contentsType: TEXT
coupang content(본문): '3단 접이식 우산'      ← 상세 꾸미기 유실, 제목 폴백
```

**AFTER** (v86-N)
```
coupang description_html len: 472
coupang contents[0].contentsType: HTML
coupang content(본문):
<p ...>자동 3단 우산 · 8K 강화 살대 · 발수 코팅</p>
<div ...(강조박스)>무료배송 · 당일출고</div>
<img src="https://img.example/umbrella-detail.jpg" ...>
<hr ...>
<p ...>소재: 폴리에스터 190T</p>
```

## 판정
- 가드 `tests/test_v86_n_detail_blocks_upload.py`(6): 렌더 시맨틱·이스케이프·마켓 오버라이드·
  `_payload_for_market` 주입·**블록 승리(plain 이김)**·**무블록/빈블록 폴백 회귀 0**.
- 회귀: upload/dispatch/channel 스위트 **384 passed**.
- 확장·추출기 무변경(서버 업로드 경로) → manifest bump·실페이지 하네스 불요.

적용 스킬: (백엔드 업로드 배선 — 앱 UI/CSS 렌더 변경 없음. 생성 HTML은 마켓 상세용 인라인
스타일이라 app.css 토큰 대상 아님. impeccable/humanizer CLI 미설치.)
