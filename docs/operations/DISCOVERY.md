# DISCOVERY.md — Discovery 봇 운영 가이드 (Phase 135)

키워드 기반으로 새로운 쇼핑몰을 자동 발견하는 봇의 운영 가이드.

---

## 동작 원리

```
DISCOVERY_KEYWORDS (env + Sheets)
    ↓
각 키워드로 Reddit 패션/요가 서브레딧 검색
    ↓
외부 링크 URL 추출 → 도메인 파싱
    ↓
이미 등록된 도메인 / 대형 플랫폼 필터링
    ↓
신규 도메인 → Sheets `discovery_candidates` 저장
    ↓
텔레그램 알림: "🔍 신규 사이트 발견: ..."
    ↓
관리자 승인/거부 → /seller/discovery
```

---

## 키워드 관리

### 방법 1: 웹 UI
`/seller/discovery/keywords` 페이지에서 추가/삭제.

### 방법 2: 환경변수 (env)
```bash
DISCOVERY_KEYWORDS=yoga wear brand,outdoor gear,streetwear brand,PORTER bag
```
쉼표로 구분. Sheets 키워드가 있으면 Sheets 우선 사용.

### 방법 3: Google Sheets
`discovery_keywords` 워크시트에 직접 입력:
```
keyword | category | created_at
yoga wear brand | yoga | 2026-05-06T00:00:00Z
```

---

## 후보 승인 흐름

1. `/seller/discovery` 페이지 접속
2. 발견된 도메인 목록 확인
3. **승인** → `discovery_candidates` 상태 = "approved"
   - 어댑터 개발 후보로 관리
4. **거부** → 상태 = "rejected"
   - 이후 동일 도메인 재발견 시 skip

---

## 수동 실행

```bash
# curl로 수동 트리거
curl -X POST https://kohganepercentiii.com/cron/discovery

# 또는 /seller/discovery 페이지에서 "Discovery 실행" 버튼
```

---

## 자동 실행 (Render Cron Job)

Render 대시보드에서 Cron Job 설정:
- **명령**: `curl -X POST $RENDER_EXTERNAL_URL/cron/discovery`
- **스케줄**: `0 6 * * *` (매일 오전 6시 KST)

---

## 필터링 기준

자동으로 제외되는 도메인:
- amazon.com, rakuten.co.jp (API 방식으로 별도 처리)
- taobao.com, tmall.com, aliexpress.com
- instagram.com, pinterest.com, youtube.com
- 이미 등록된 어댑터 도메인
- reddit.com, google.com, wikipedia.org

---

## Sheets 워크시트 구조

### `discovery_keywords`
```
keyword | category | created_at
```

### `discovery_candidates`
```
domain | keyword | source | status | discovered_at
```
- status: `pending` / `approved` / `rejected`

---

## 어댑터 개발 촉진

승인된 도메인에 대해 어댑터 개발:
1. `src/collectors/adapters/<domain_name>_adapter.py` 생성
2. `BrandAdapter` 상속
3. `src/collectors/dispatcher.py` 어댑터 등록
4. 테스트 작성
