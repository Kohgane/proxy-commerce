# GitHub Issue 라벨 체계 (Label Taxonomy)

> 이 문서의 라벨을 GitHub에 등록하면 이슈/PR 필터링·우선순위 관리가 즉시 가능합니다.  
> 아래 `gh` CLI 명령어를 순서대로 실행하세요.

---

## 1. Priority 라벨

| 라벨 | 색상 | 설명 |
|------|------|------|
| `P0` | `#d73a4a` (빨강) | 이번 주 반드시 완료 (블로커 수준) |
| `P1` | `#e4a033` (주황) | 다음 주 완료 목표 |
| `P2` | `#0075ca` (파랑) | 확장/개선 (시간 여유 시) |

---

## 2. Type 라벨

| 라벨 | 색상 | 설명 |
|------|------|------|
| `type:feature` | `#a2eeef` (민트) | 새 기능 구현 |
| `type:bug` | `#d73a4a` (빨강) | 버그 수정 |
| `type:ops` | `#fef2c0` (연노랑) | 운영/인프라 작업 |
| `type:docs` | `#c5def5` (연파랑) | 문서 작성/수정 |
| `type:refactor` | `#e4e669` (연녹색) | 코드 리팩터링 |
| `type:test` | `#d4c5f9` (연보라) | 테스트 추가/수정 |

---

## 3. Component 라벨

| 라벨 | 색상 | 설명 |
|------|------|------|
| `component:schema` | `#bfd4f2` | 상품 스키마/데이터 모델 |
| `component:collector` | `#bfd4f2` | 수집기 (ALO, lululemon, 타오바오 등) |
| `component:pricing` | `#bfd4f2` | 가격 엔진 (마진/환율/수수료) |
| `component:publisher` | `#bfd4f2` | WooCommerce 업로드 |
| `component:monitoring` | `#bfd4f2` | 재고/가격 모니터링 + 알림 |
| `component:cs` | `#bfd4f2` | CS 자동화 템플릿 |
| `component:taobao-gate` | `#bfd4f2` | 타오바오 판매자 화이트리스트 게이트 |
| `component:infra` | `#bfd4f2` | 환경설정/CI/Docker/배포 |
| `component:scheduler` | `#bfd4f2` | 스케줄러/백그라운드 작업 |

---

## 4. Status 라벨

| 라벨 | 색상 | 설명 |
|------|------|------|
| `status:ready` | `#0e8a16` (녹색) | 즉시 착수 가능 |
| `status:in-progress` | `#fbca04` (노랑) | 현재 작업 중 |
| `status:blocked` | `#b60205` (진빨강) | 블로킹 이슈 존재 |
| `status:review` | `#6f42c1` (보라) | 리뷰/검수 대기 |
| `status:done` | `#c2e0c6` (연녹색) | 완료 (Close 전 확인용) |

---

## 5. Risk / Business 라벨

| 라벨 | 색상 | 설명 |
|------|------|------|
| `risk:payment` | `#ee0701` | 결제/정산 리스크 |
| `risk:policy` | `#ee0701` | 브랜드/플랫폼 정책 위반 리스크 |
| `risk:shipping` | `#e4a033` | 배송/반품 관련 리스크 |
| `biz:revenue` | `#0e8a16` | 매출 직결 작업 |
| `biz:conversion` | `#0e8a16` | 전환률 영향 작업 |

---

## 6. 네이밍 컨벤션

- **구분자**: `:` (콜론) 사용 — 예: `component:collector`, `type:feature`
- **소문자 kebab-case**: 공백 없이 `-` 연결
- **Priority는 단독 대문자**: `P0`, `P1`, `P2`
- 이슈당 라벨 조합 권장: `Priority` 1개 + `Type` 1개 + `Component` 1~2개 + `Status` 1개

---

## 7. gh CLI 라벨 생성 명령어

> 아래 명령어를 그대로 복붙해서 터미널에서 실행하면 라벨이 한 번에 생성됩니다.

```bash
# === Priority ===
gh label create "P0" --color "d73a4a" --description "이번 주 반드시 완료 (블로커 수준)" --repo Kohgane/proxy-commerce
gh label create "P1" --color "e4a033" --description "다음 주 완료 목표" --repo Kohgane/proxy-commerce
gh label create "P2" --color "0075ca" --description "확장/개선 (시간 여유 시)" --repo Kohgane/proxy-commerce

# === Type ===
gh label create "type:feature"   --color "a2eeef" --description "새 기능 구현"         --repo Kohgane/proxy-commerce
gh label create "type:bug"       --color "d73a4a" --description "버그 수정"             --repo Kohgane/proxy-commerce
gh label create "type:ops"       --color "fef2c0" --description "운영/인프라 작업"      --repo Kohgane/proxy-commerce
gh label create "type:docs"      --color "c5def5" --description "문서 작성/수정"        --repo Kohgane/proxy-commerce
gh label create "type:refactor"  --color "e4e669" --description "코드 리팩터링"         --repo Kohgane/proxy-commerce
gh label create "type:test"      --color "d4c5f9" --description "테스트 추가/수정"      --repo Kohgane/proxy-commerce

# === Component ===
gh label create "component:schema"       --color "bfd4f2" --description "상품 스키마/데이터 모델"              --repo Kohgane/proxy-commerce
gh label create "component:collector"    --color "bfd4f2" --description "수집기 (ALO, lululemon, 타오바오 등)" --repo Kohgane/proxy-commerce
gh label create "component:pricing"      --color "bfd4f2" --description "가격 엔진 (마진/환율/수수료)"         --repo Kohgane/proxy-commerce
gh label create "component:publisher"    --color "bfd4f2" --description "WooCommerce 업로드"                   --repo Kohgane/proxy-commerce
gh label create "component:monitoring"   --color "bfd4f2" --description "재고/가격 모니터링 + 알림"            --repo Kohgane/proxy-commerce
gh label create "component:cs"           --color "bfd4f2" --description "CS 자동화 템플릿"                     --repo Kohgane/proxy-commerce
gh label create "component:taobao-gate"  --color "bfd4f2" --description "타오바오 판매자 화이트리스트 게이트"  --repo Kohgane/proxy-commerce
gh label create "component:infra"        --color "bfd4f2" --description "환경설정/CI/Docker/배포"              --repo Kohgane/proxy-commerce
gh label create "component:scheduler"    --color "bfd4f2" --description "스케줄러/백그라운드 작업"             --repo Kohgane/proxy-commerce

# === Status ===
gh label create "status:ready"        --color "0e8a16" --description "즉시 착수 가능"          --repo Kohgane/proxy-commerce
gh label create "status:in-progress"  --color "fbca04" --description "현재 작업 중"            --repo Kohgane/proxy-commerce
gh label create "status:blocked"      --color "b60205" --description "블로킹 이슈 존재"        --repo Kohgane/proxy-commerce
gh label create "status:review"       --color "6f42c1" --description "리뷰/검수 대기"          --repo Kohgane/proxy-commerce
gh label create "status:done"         --color "c2e0c6" --description "완료 (Close 전 확인용)"  --repo Kohgane/proxy-commerce

# === Risk / Business ===
gh label create "risk:payment"     --color "ee0701" --description "결제/정산 리스크"           --repo Kohgane/proxy-commerce
gh label create "risk:policy"      --color "ee0701" --description "브랜드/플랫폼 정책 위반 리스크" --repo Kohgane/proxy-commerce
gh label create "risk:shipping"    --color "e4a033" --description "배송/반품 관련 리스크"      --repo Kohgane/proxy-commerce
gh label create "biz:revenue"      --color "0e8a16" --description "매출 직결 작업"             --repo Kohgane/proxy-commerce
gh label create "biz:conversion"   --color "0e8a16" --description "전환률 영향 작업"           --repo Kohgane/proxy-commerce
```

> **팁**: 이미 같은 이름의 라벨이 있으면 `gh label edit` 명령어로 색상/설명을 업데이트하세요.  
> 예: `gh label edit "bug" --new-name "type:bug" --color "d73a4a" --repo Kohgane/proxy-commerce`
