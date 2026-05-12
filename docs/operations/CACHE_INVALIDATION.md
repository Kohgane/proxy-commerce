# CACHE_INVALIDATION.md — Phase 배포 후 캐시 무효화 절차 (Phase 151.1)

## 개요

Proxy Commerce의 AI listing 분석 결과는 인메모리 캐시에 저장됩니다.
Phase 151.1부터 캐시 키에 Phase 번호와 prompt_version이 포함되어 **Phase 배포 시 자동으로 새 결과를 생성**합니다.

---

## 캐시 키 구조

```
phase={CURRENT_PHASE}:prompt={prompt_version}:url={url_hash}:img={img_hash}
```

### 예시
```
phase=151:prompt=v2_explicit_fields:url=a3f8d...b1c2:img=e7b0c...a495
```

### 효과
| 변경 사항 | 동작 |
|-----------|------|
| Phase 번호 업 (e.g. 150 → 151) | 자동 캐시 무효화 |
| `AI_LISTING_PROMPT_VERSION` 변경 | 자동 캐시 무효화 |
| 동일 Phase + 동일 prompt + 동일 URL | 캐시 히트 (정상) |

---

## Phase 배포 후 운영자 액션

### 1. 자동 무효화 (코드 레벨)
`src/version.py`의 `CURRENT_PHASE`가 변경되면 모든 analysis 캐시 키가 달라짐 → 배포 즉시 새 결과 생성.

### 2. 수동 무효화 (운영자 버튼)
구버전 캐시 일소가 필요할 경우:

1. `/admin/diagnostics` 접속
2. **🤖 AI 상품등록** 카드 하단 → **🗑️ AI listing 캐시 전체 삭제** 버튼 클릭
3. 확인 다이얼로그 수락
4. `analysis: N건, scraper: N건` 삭제 메시지 확인

### 3. API를 통한 무효화
```bash
# POST /admin/diagnostics/ai-cache-clear (관리자 세션 필요)
curl -X POST https://your-domain.com/admin/diagnostics/ai-cache-clear \
  -b "session=<admin_session_cookie>"
```

---

## "다시 분석 (캐시 무시)" 버튼 동작

Phase 151.1부터 force_refresh=1 시 **analysis + scraper 캐시 모두** 무효화:

1. `url_scraper._scraper_cache` → 해당 URL 캐시 삭제
2. `analyzer._analysis_cache` → 동일 이미지/URL의 **모든 Phase/prompt 버전** 캐시 삭제

결과 카드의 `cache` 패널에서 확인:
```json
{
  "analysis": "miss",   ← 새로 분석됨
  "scraper": "miss",    ← 새로 가져옴
  "cache_badge": {"label": "🟢 새로 분석됨", "level": "miss"}
}
```

---

## 트러블슈팅

### analysis: hit인데 결과가 옛 Phase와 동일한 경우

1. Phase 번호가 실제로 변경됐는지 확인: `src/version.py::CURRENT_PHASE`
2. `/admin/diagnostics` → 캐시 키 Phase 포함: ✅ 확인
3. 수동으로 "AI listing 캐시 전체 삭제" 버튼 클릭
4. 재테스트

### scraper: miss, analysis: hit인 경우

- Phase 번호가 변경됐지만 구버전 키가 아직 캐시에 있을 때 발생하지 않음 (Phase 포함 키 덕분)
- 만약 발생하면: `/admin/diagnostics` → 캐시 전체 삭제 후 재시도

---

## 관련 파일

- `src/ai_listing/analyzer.py` — `_make_analysis_cache_key()`, `_evict_analysis_cache_for_image()`, `clear_all_analysis_cache()`
- `src/ai_listing/url_scraper.py` — `scrape_product_page(force_refresh=True)`, `_scraper_cache`
- `src/dashboard/admin_views.py` — `diagnostics_ai_cache_clear()` (POST /admin/diagnostics/ai-cache-clear)
- `src/version.py` — `CURRENT_PHASE`, `get_current_phase()`
