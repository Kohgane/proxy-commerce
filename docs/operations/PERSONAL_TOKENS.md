# PERSONAL_TOKENS.md — Personal Access Token 가이드

코가네 퍼센티 Personal Access Token(PAT) 발급·회수·활용 가이드.

---

## 개요

PAT는 크롬 확장 프로그램, 북마클릿, curl, 외부 자동화 스크립트에서  
서버 API를 인증하는 **장기 Bearer 토큰**입니다.

- 토큰 형식: `tok_<60자리 16진수>` (총 64자)
- 저장 방식: **SHA-256 해시만 저장** (원본 평문은 1회 표시 후 재조회 불가)
- 기본 만료: 365일 (발급 시 30일/90일/1년/10년 선택)

---

## 발급 방법

### UI (권장)

1. `https://kohganepercentiii.com/auth/login` 접속 → 로그인
2. 사이드바 **🔐 API 토큰** 클릭 (`/seller/me/tokens`)
3. 우측 상단 **＋ 새 토큰 발급** 클릭
4. 권한 스코프 선택 (아래 참고)
5. 만료 기간 선택
6. **발급하기** 클릭
7. 표시된 토큰(`tok_...`)을 즉시 복사 — **이후 다시 볼 수 없음**
8. 안전한 곳(1Password 등)에 보관

---

## 스코프 정의

| 스코프 | 설명 | 크롬 확장 필요? |
|---|---|---|
| `collect.write` | 상품 수집·카탈로그 등록 | ✅ 필수 |
| `catalog.read` | 카탈로그 조회 | 선택 |
| `markets.write` | 마켓 업로드 | 고급 |

**최소 권한 원칙**: 크롬 확장에는 `collect.write`만 부여 권장.

---

## 토큰 회수

1. `/seller/me/tokens` 접속
2. 해당 토큰 행 오른쪽 **회수** 버튼 클릭
3. 확인 팝업 → 회수 완료 (복구 불가)

---

## 외부 통합 예시

### curl

```bash
curl -X POST https://kohganepercentiii.com/api/v1/collect/extension \
  -H "Authorization: Bearer tok_여기에토큰입력" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.aloyoga.com/products/xxxx",
    "title": "상품명",
    "price": "89.00",
    "currency": "USD",
    "image_url": "https://cdn.aloyoga.com/..."
  }'
```

### JavaScript (fetch)

```javascript
const TOKEN = "tok_여기에토큰입력";
const SERVER = "https://kohganepercentiii.com";

const resp = await fetch(`${SERVER}/api/v1/collect/extension`, {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${TOKEN}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    url: window.location.href,
    title: document.title,
    price: "89.00",
    currency: "USD",
  }),
});
const data = await resp.json();
console.log(data.ok ? "✅ 수집 완료" : "❌ 오류: " + data.error);
```

### Python

```python
import requests

TOKEN = "tok_여기에토큰입력"
SERVER = "https://kohganepercentiii.com"

resp = requests.post(
    f"{SERVER}/api/v1/collect/extension",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "url": "https://www.aloyoga.com/products/xxxx",
        "title": "상품명",
        "price": "89.00",
        "currency": "USD",
    },
)
resp.raise_for_status()
print(resp.json())
```

---

## 보안 권고

1. **1Password, Bitwarden 등 비밀번호 매니저에 보관** — 메모장·노션 저장 금지
2. **환경변수로 전달** — 소스코드에 직접 입력 금지 (`git log`에 영구 기록됨)
3. **최소 스코프 부여** — 필요한 권한만 선택
4. **만료 기간 최소화** — 장기간 사용 안 할 경우 1년 이하
5. **유출 시 즉시 회수** — `/seller/me/tokens`에서 즉시 회수

---

## API 인증 방식

```
Authorization: Bearer tok_<token>
```

서버는 토큰을 SHA-256 해싱 후 Sheets와 비교합니다.  
인메모리 캐시(TTL 5분)로 Sheets API 호출을 최소화합니다.

---

## Sheets 워크시트 구조

`personal_tokens` 워크시트:

| 컬럼 | 내용 |
|---|---|
| token_hash | SHA-256 해시 (평문 없음) |
| user_id | 소유자 사용자 ID |
| scopes_json | JSON 배열 (예: `["collect.write"]`) |
| created_at | ISO 8601 UTC |
| last_used_at | 마지막 사용 시각 |
| expires_at | 만료 시각 |
| revoked | `"true"` / `"false"` |
