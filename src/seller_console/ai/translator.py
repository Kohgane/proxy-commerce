"""src/seller_console/ai/translator.py — 상품 번역 + 마켓별 광고 카피 자동 생성 (Phase 130).

번역 프로바이더 **체인**(v87-W7, 순차 폴백 — 하나 실패하면 다음). 기본 순서 = 무료 우선 → 저가/키필요 → OpenAI 최후:
1. mymemory  — 무키·무가입 무료(TRANSLATE_DISABLE_MYMEMORY=1로 차단)
2. papago    — NCP Papago NMT (NCP_PAPAGO_CLIENT_ID + NCP_PAPAGO_CLIENT_SECRET). ko·ja·zh 도메인 최적
3. deepl     — DeepL (DEEPL_API_KEY). 번역만, 카피는 template
4. azure     — Azure Translator (AZURE_TRANSLATOR_KEY + AZURE_TRANSLATOR_REGION). 소스 자동감지
5. openai    — GPT (OPENAI_API_KEY + OPENAI_MODEL=gpt-4o-mini). 번역 + 카피, 최후 폴백
전부 실패/키 전무 → 원본 유지(stub/-fallback, 정직 실패). `TRANSLATE_PROVIDER_CHAIN`(쉼표)로 순서·선택 오버라이드.
※ 기존 DEEPL_API_KEY 경로는 별도 분기가 아니라 이 체인의 한 단계로 **흡수**됨(2번째 순위, 병행 아님).

ADAPTER_DRY_RUN=1 시 실 API 호출 차단.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# v60 STEP4: AI 초안·키워드 오염어 차단(STEP1 스코프 공유) — 확장 UI 텍스트·챗패널·도메인·수집기 문구.
_CONTAM_RE = re.compile(
    r"(chat\s*history|채팅\s*기록|고가수집|고가브릿지|gogabridj|kgp[-_ ]|확장\s*프로그램|사이드\s*패널|"
    r"sidebar|assistant|copilot|rufus|번역까지\s*한\s*번에|수집\s*중|https?://|www\.|\.com\b|\.co\.[a-z]{2}|"
    r"수집기|브라우저\s*확장)",
    re.I,
)


def _is_contaminated(s: str) -> bool:
    """상품 텍스트가 아니라 확장 UI·페이지 크롬 오염어인지(초안·키워드에서 배제)."""
    return bool(s) and bool(_CONTAM_RE.search(str(s)))


# v87-W5: 마켓 페이지 UI 쓰레기(상품 정보가 아님) — 라쿠텐 등 상세에서 스펙/키워드에 섞여 들어와
#   AI 초안을 오염시켰다(오너 TSUMUGI: 不適切な商品を報告·レビュー·お気に入り·送料無料이 초안에 그대로).
#   상품 속성어(サイズ/素材/원산지/색상/무게 등)는 건드리지 않도록 **UI 액션·배너 문구만** 좁게 매칭한다.
_MARKET_UI_JUNK_RE = re.compile(
    r"("
    r"不適切|商品を報告|この商品を報告|通報|問い合わせ|お問い合わせ|"                       # JP: 신고·문의
    r"レビュー|口コミ|お気に入り|ブックマーク|カート|買い物かご|購入手続き|レジ|"           # JP: 리뷰·찜·장바구니·결제
    r"送料無料|あす楽|ポイント\d*\s*倍|楽天ポイント|クーポン|ランキング|売れ筋|再入荷|"     # JP: 배송/포인트/쿠폰/랭킹 배너
    r"楽天市場|ショップを?見る|この商品について|数量|在庫あり|在庫なし|"                    # JP: 몰/재고/수량
    r"리뷰|후기|리뷰\s*쓰기|신고|문의하기|장바구니|찜하기|즐겨찾기|쿠폰|무료\s*배송|배송비\s*무료|랭킹|재입고|재고\s*있음|"  # KO
    r"write\s*a?\s*review|report\s*(this|item)|add\s*to\s*cart|wish\s*list|add\s*to\s*favorites?|free\s*shipping|coupon|in\s*stock|out\s*of\s*stock|ranking"  # EN
    r")",
    re.I,
)


def _is_ui_junk(s: str) -> bool:
    """상품 속성이 아니라 마켓 페이지 UI 액션/배너 문구인지(초안·키워드·스펙에서 배제)."""
    return bool(s) and bool(_MARKET_UI_JUNK_RE.search(str(s)))


# v87-W8 item3: 제목 상용구(라쿠텐 등) — 번역 전 제목에서 제거할 마켓 판촉/배송 상용구.
#   제목 segment 단위로 검사(공백···| 구분). 상품 속성어는 매칭 안 되게 좁게(선물포장/배송/포인트/쿠폰).
_MARKET_TITLE_JUNK_RE = re.compile(
    r"("
    r"楽ギフ|ギフト対応|のし対応|熨斗|ラッピング(無料)?|包装(無料)?|"           # JP: 선물/포장 상용구
    r"あす着|あす楽|翌日配送|即日発送|当日発送|送料無料|送料込|代引|"            # JP: 배송 상용구
    r"ポイント\d*倍|楽天ポイント|買い回り|マラソン|スーパーSALE|"               # JP: 포인트/세일
    r"クーポン|レビュー特典|ランキング\d*位?|\d+冠|"                             # JP: 쿠폰/후기특전/랭킹
    r"무료\s*배송|배송비\s*무료|사은품|쿠폰|적립|"                                # KO 상용구
    r"free\s*shipping|gift\s*wrap(ping)?"                                       # EN 상용구
    r")",
    re.I,
)


# v87-W9 item2: 상용구 변형 내성 — 구분자(_·전각＿·전각공백·【】··) 무시. 楽ギフ 계열은 뒤따르는
#   _包装/包装/対応까지 함께 제거(언더스코어 변형 '楽ギフ_包装' 미제거 재발 방지 — 실증 픽스처).
_GIFT_RUN_RE = re.compile(r"[【\[]?楽ギフ[_＿\s　]*(包装|対応)?[】\]]?", re.I)
_TITLE_SEP_RE = re.compile(r"[\s・|/／　_＿]+")


def strip_market_boilerplate(title: str) -> str:
    """v87-W9 item2: 제목에서 마켓 판촉/배송 상용구를 제거(상품 속성어 보존). 구분자 변형에 내성.
    ① 楽ギフ 런(_包装 등 접미 포함) 직접 제거 ② 구분자 정규화 후 세그먼트 드롭. 전부 제거되면 원문 유지."""
    t = str(title or "").strip()
    if not t:
        return t
    # ① 楽ギフ_包装/楽ギフ包装/【楽ギフ_包装】 등 언더스코어·전각·괄호 변형을 통째로 제거.
    cleaned = _GIFT_RUN_RE.sub(" ", t)
    # ② 구분자(공백·_·전각·・|/) 정규화 후 세그먼트 단위로 상용구 드롭.
    parts = _TITLE_SEP_RE.split(cleaned)
    kept = [p for p in parts if p and not _MARKET_TITLE_JUNK_RE.search(p)]
    out = " ".join(kept).strip(" -_·|/【】[]")
    return out or t


def _is_input_junk(s: str) -> bool:
    """AI 초안 입력에서 버릴 오염(확장 크롬 + 마켓 UI 쓰레기) 통합 판정."""
    return _is_contaminated(s) or _is_ui_junk(s)


def _clean_specs_for_draft(specs) -> list:
    """스펙 표에서 UI 쓰레기 행 제거(라벨 또는 값이 UI 액션/배너면 상품 스펙 아님) — 초안 오염 차단."""
    out = []
    for sp in (specs or []):
        try:
            label, value = str(sp[0] or "").strip(), str(sp[1] or "").strip()
        except Exception:
            continue
        if not label or not value:
            continue
        if _is_input_junk(label) or _is_input_junk(value):
            continue
        out.append([label, value])
    return out


def _clean_keywords_for_draft(keywords) -> list:
    """키워드에서 UI 쓰레기 제거(리뷰/신고/송료무료 등 상품어 아님)."""
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    out = []
    for k in (keywords or []):
        s = str(k or "").strip()
        if s and len(s) > 1 and s not in out and not _is_input_junk(s):
            out.append(s)
    return out

# 마켓별 카피 톤앤매너 프롬프트 힌트
_MARKET_PROMPTS = {
    "coupang": "핵심 키워드 6개 + bullet list 형식. 간결하고 직접적.",
    "smartstore": "SEO 친화적. 상세 설명. 검색 키워드 포함. 신뢰감 강조.",
    "11st": "짧고 임팩트 있게. 가격 메리트와 특징 강조.",
}


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


# v87-W7: MyMemory langpair용 원문 언어 추정(스크립트 기반 휴리스틱). 한글=ko / 가나=ja /
#   가나 없는 한자=zh-CN / 그 외=en. 정밀 감지가 아니라 무료 MT 소스 지정용(틀리면 체인이 다음으로 폴백).
_BILINGUAL_DIVIDER = "───────── 원문 (Original) ─────────"


def compose_bilingual(ko: str, original: str) -> str:
    """v87-W7 item2: 상세 병기 — 한국어 번역 상단 + 구분선 + 원문 하단. 마켓 등록 시 이 병기본이 나간다.
    원문은 항상 보존(별도 저장 필드는 순수 유지, 병기는 표시·전송 시점에 합성). 둘이 같거나 한쪽이 비면
    중복 없이 하나만."""
    ko = str(ko or "").strip()
    original = str(original or "").strip()
    if not original or ko == original:
        return ko or original
    if not ko:
        return original
    return f"{ko}\n\n{_BILINGUAL_DIVIDER}\n{original}"


def _detect_src_lang(text: str) -> str:
    s = str(text or "")
    if not s.strip():
        return "en"
    has_hangul = any("가" <= c <= "힣" for c in s)
    if has_hangul:
        return "ko"
    has_kana = any(("぀" <= c <= "ゟ") or ("゠" <= c <= "ヿ") for c in s)
    if has_kana:
        return "ja"
    has_han = any("一" <= c <= "鿿" for c in s)
    if has_han:
        return "zh-CN"
    return "en"


def _route_src_lang(text: str) -> str:
    """v87-W9 item1: 체인·프로바이더 소스용 언어 감지 — **라틴 비율 무관**, 가나·한자 1자라도 있으면 ja.
    라쿠텐/아마존JP가 주 소스라 한자 제목(예 '玉渕')도 ja로 라우팅(zh 오판→mymemory 로마자화 방지).
    한글이 있으면 ko(번역 불필요), CJK 없으면 en."""
    s = str(text or "")
    if not s.strip():
        return "en"
    if any("가" <= c <= "힣" for c in s):
        return "ko"
    has_kana = any(("぀" <= c <= "ゟ") or ("゠" <= c <= "ヿ") for c in s)
    has_han = any("一" <= c <= "鿿" for c in s)
    if has_kana or has_han:      # 가나·한자 1자라도 → ja 체인(라틴 비율 무관)
        return "ja"
    return "en"


# v87-W6 item 2: 번역 실패 다발 조사 — **계측**(호출 n·성공 n·실패 n·사유별). 번역 무료 쿼터 회계와
#   완전히 별개인 읽기 전용 관측 카운터(쿼터 무손대). 프로세스 인메모리 누적, get_translate_stats()로 노출.
# v87-W7a 재개정(branch②): 실패 시 **원 응답 코드·바디를 계측에 적재** — 다음 실패부터 원문 사유가 남게.
#   by_code(사유코드별)·recent(최근 실패 원문: provider·status·body 스니펫)를 추가(쿼터 회계 무손대).
_TR_STATS = {"calls": 0, "ok": 0, "fail": 0, "by_reason": {}, "by_code": {}, "recent": []}
_TR_STATS_LOCK = threading.Lock()
_TR_RECENT_MAX = 25


def _record_translate(ok: bool, reason: str = "", provider: str = "",
                      code: str = "", status=None, body: str = "") -> None:
    with _TR_STATS_LOCK:
        _TR_STATS["calls"] += 1
        if ok:
            _TR_STATS["ok"] += 1
        else:
            _TR_STATS["fail"] += 1
            key = (reason or code or "원인 미상")[:80]
            _TR_STATS["by_reason"][key] = _TR_STATS["by_reason"].get(key, 0) + 1
            if code:
                _TR_STATS["by_code"][code] = _TR_STATS["by_code"].get(code, 0) + 1
            # 원 응답(코드·상태·바디 스니펫) 보존 — 오귀인 시 대조용. 시크릿 없음(에러 바디만, 300자).
            _TR_STATS["recent"].append({
                "provider": provider or "", "code": code or "", "status": status,
                "body": (body or "")[:300], "reason": (reason or "")[:120]})
            if len(_TR_STATS["recent"]) > _TR_RECENT_MAX:
                _TR_STATS["recent"] = _TR_STATS["recent"][-_TR_RECENT_MAX:]


def raw_error_meta(exc: Exception):
    """예외에서 원 응답 (status_code, body 스니펫) 추출 — 프로바이더 응답 원문 보존용."""
    status = None
    body = ""
    resp = getattr(exc, "response", None)
    if resp is not None:
        status = getattr(resp, "status_code", None)
        try:
            body = (getattr(resp, "text", "") or "")[:300]
        except Exception:
            body = ""
    if not body:
        body = str(exc or "")[:300]
    return status, body


def _is_rate_limit_exc(exc: Exception) -> bool:
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None) if resp is not None else None
    s = str(exc or "").lower()
    return code == 429 or "rate limit" in s or "rate_limit" in s or "too many requests" in s


def _post_with_429_retry(req, url, **kw):
    """v87-W8 item4: OpenAI 상시 429 대응 — rate_limit이면 **짧은 백오프 1회**만 재시도(과금·지연 최소).
    재시도도 실패하면 예외 전파 → 체인이 다음(또는 stub) 폴백. env OPENAI_RETRY_BACKOFF_SEC(기본 1.5, 0=끔)."""
    try:
        r = req.post(url, **kw)
        r.raise_for_status()
        return r
    except Exception as exc:
        if not _is_rate_limit_exc(exc):
            raise
        try:
            backoff = float(os.getenv("OPENAI_RETRY_BACKOFF_SEC", "1.5") or 0)
        except (TypeError, ValueError):
            backoff = 1.5
        if backoff > 0:
            import time as _t
            _t.sleep(min(backoff, 5))
        logger.warning("OpenAI 429(rate_limit) — %.1fs 백오프 후 1회 재시도", backoff)
        r = req.post(url, **kw)      # 1회만 재시도. 또 429면 raise → 폴백.
        r.raise_for_status()
        return r


def record_translate_failure(exc: Exception, provider: str) -> str:
    """분류(코드·문구) + 원 응답(status·body)을 계측에 적재하고 사람 문구를 반환(호출측 error 표시용)."""
    code, reason = classify_translate_reason(exc)
    status, body = raw_error_meta(exc)
    _record_translate(False, reason=reason, provider=provider, code=code, status=status, body=body)
    return reason


def get_translate_stats() -> dict:
    """번역 호출 계측 스냅샷(읽기 전용) — 호출/성공/실패/사유별·코드별·최근 실패 원문. 쿼터 회계와 무관."""
    with _TR_STATS_LOCK:
        return {"calls": _TR_STATS["calls"], "ok": _TR_STATS["ok"], "fail": _TR_STATS["fail"],
                "by_reason": dict(_TR_STATS["by_reason"]), "by_code": dict(_TR_STATS["by_code"]),
                "recent": list(_TR_STATS["recent"])}


def reset_translate_stats() -> None:
    """계측 리셋(테스트·리포트 구간 측정용)."""
    with _TR_STATS_LOCK:
        _TR_STATS["calls"] = 0
        _TR_STATS["ok"] = 0
        _TR_STATS["fail"] = 0
        _TR_STATS["by_reason"] = {}
        _TR_STATS["by_code"] = {}
        _TR_STATS["recent"] = []


# v87-W7 회수: 실패 메시지에 **프로바이더명 명시** — 체인 도입 후 어느 단이 죽었는지 오너가 바로 알아야 한다.
_PROVIDER_LABEL = {"mymemory": "MyMemory", "papago": "Papago", "deepl": "DeepL",
                   "azure": "Azure", "openai": "OpenAI"}


def provider_label(name: str) -> str:
    """체인 프로바이더 내부명 → 사람이 읽을 표기(‘-fallback’ 접미 제거)."""
    base = (name or "").replace("-fallback", "").strip().lower()
    return _PROVIDER_LABEL.get(base, base or "번역")


# v87-W7a 재개정: "한도 초과" 발화 주체를 4분한다(오너 실증 — OpenAI 잔액 $22.37, 크레딧 고갈 기각).
#   ①서버 내부 예산 가드(AI_MONTHLY_BUDGET_USD) 차단 → **"서버 월 예산"** 명시(OpenAI 지갑 아님)
#   ②프로바이더 429 insufficient_quota(크레딧·결제 소진) ③프로바이더 429 rate_limit(요청 속도 — 재시도)
#   ④401/403 무효 키. 각각 별 문구 + 짧은 사유코드(translate_stats 집계). 종전엔 ①③를 ②로 뭉갰다.
def classify_translate_reason(exc: Exception) -> tuple:
    """(사유코드, 사람 문구) 반환. 코드는 translate_stats 집계용(budget/quota/rate_limit/auth/model/timeout/network/http/unknown)."""
    s = str(exc or "").lower()
    status = None
    resp = getattr(exc, "response", None)
    if resp is not None:
        status = getattr(resp, "status_code", None)
    # ① 서버 내부 예산 가드(우리 코드가 막은 것) — OpenAI 결제와 무관. 오너가 지갑 뒤지지 않게 명시.
    if type(exc).__name__ == "BudgetExceededError" or "월 예산" in str(exc or "") or "monthly budget" in s:
        return ("budget", "서버 월 예산 상한에 도달해 AI 호출을 멈췄어요(OpenAI 잔액 아님 · AI_MONTHLY_BUDGET_USD 상향/대기)")
    # ④ 인증
    if status in (401, 403) or "unauthorized" in s or "invalid_api_key" in s or "authenticationerror" in s:
        return ("auth", "API 키가 잘못됐거나 만료됐어요(키 재발급 후 재설정)")
    # ② 프로바이더 크레딧·결제 소진(429 insufficient_quota) — 진짜 '결제' 문제.
    if "insufficient_quota" in s or ("quota" in s and "rate" not in s):
        return ("quota", "프로바이더 크레딧·결제가 소진됐어요(해당 프로바이더 결제·플랜 확인)")
    # ③ 프로바이더 요청 속도 제한(429 rate limit) — 결제 아님, 잠시 후 재시도.
    if status == 429 or "rate limit" in s or "rate_limit" in s or "too many requests" in s:
        return ("rate_limit", "요청 속도 제한에 걸렸어요(결제 아님 · 잠시 후 자동 재시도)")
    if (status in (404, 400) and "model" in s) or ("model" in s and ("does not exist" in s or "not found" in s)):
        return ("model", "설정한 모델명(OPENAI_MODEL)이 잘못됐어요")
    if "timeout" in s or "timed out" in s:
        return ("timeout", "번역 서버 응답이 지연됐어요(잠시 후 재시도)")
    if "connection" in s or "network" in s or "resolve" in s or "ssl" in s:
        return ("network", "번역 서버에 연결하지 못했어요(네트워크·프록시 확인)")
    if status:
        return ("http", f"번역 API 오류(HTTP {status})")
    return ("unknown", "번역 API 호출에 실패했어요")


def classify_translate_error(exc: Exception) -> str:
    """사람이 읽을 한 줄(무음 금지·오귀인 금지). 사유코드는 classify_translate_reason 참조."""
    return classify_translate_reason(exc)[1]


_CAT_LABEL = {
    "BAG": "가방", "CLO": "의류", "BTY": "뷰티", "FOD": "식품", "ELC": "가전", "DIG": "디지털",
    "HOM": "홈·리빙", "HLT": "건강", "SPT": "스포츠·레저", "TOY": "완구", "BBY": "유아", "PET": "반려동물",
    "OFC": "문구·오피스", "GEN": "",
}


def _structured_draft(title, category, keywords, specs, options, brand, description="") -> str:
    """v56 STEP3: 키 없음 모드 구조 초안 — **확인된 정보만** 실키·실값으로. 빈/플레이스홀더 행은 생략, 창작 0.
    v87-W7 item4: description(원문 상세)을 받으면 원문 스펙 라인을 **통째 보존**해 '숫자 조각 리스트' 대신
    사람이 읽는 원문 라인을 남긴다(무키 폴백 품질). UI 쓰레기 라인은 제외."""
    def _clean(v):
        return str(v or "").strip()

    lines = []
    t = _clean(title)
    # v60 STEP4: 제목이 오염어(Chat history 등)면 헤더로 쓰지 않음(STEP1이 근원 차단 — 방어적 이중 게이트).
    if t and _is_contaminated(t):
        t = ""
    if t:
        lines.append(t)
        # 후킹 1줄(항상 참인 일반 안내 — 없는 스펙 창작 아님).
        lines.append("해외 정품 · 국내 배송으로 편하게 만나보세요.")
    cat = _clean(category)
    cat_label = _CAT_LABEL.get(cat, cat)      # 코드면 라벨, 아니면 원문(GEN·미상은 빈값)
    head_bits = [b for b in (_clean(brand), cat_label) if b]
    if head_bits:
        lines.append(" · ".join(head_bits))

    # 특징(키워드 — 실데이터만 · v60 STEP4 오염어 배제)
    kws = []
    for k in (keywords or []):
        s = _clean(k)
        if s and len(s) > 1 and s not in kws and not _is_contaminated(s):
            kws.append(s)
    if kws:
        lines.append("")
        lines.append("■ 특징")
        for k in kws[:8]:
            lines.append(f"· {k}")

    # 옵션·상세(옵션 + 스펙 — 실키·실값, 'k'/'v' 류 1글자 플레이스홀더 배제)
    rows = []
    for opt in (options or []):
        if isinstance(opt, dict):
            name = _clean(opt.get("name"))
            vals = [_clean(v) for v in (opt.get("values") or []) if _clean(v)]
            if name and vals:
                rows.append((name, ", ".join(vals[:12])))
    for sp in (specs or []):
        try:
            label, value = _clean(sp[0]), _clean(sp[1])
        except Exception:
            continue
        if not label or not value or len(label) <= 1 or len(value) <= 1:
            continue      # ★ '- k: v' 플레이스홀더/빈 행 생략
        rows.append((label, value))
    if rows:
        lines.append("")
        lines.append("■ 옵션·상세")
        for name, val in rows:
            lines.append(f"· {name}: {val}")

    # v87-W7 item4: 원문 상세 라인을 통째 보존(숫자 조각 리스트 금지). 스펙 표가 빈약해도 원문 상세가
    #   있으면 사람이 읽는 라인을 그대로 남긴다(UI 쓰레기·중복 라인·초단문 제외). 창작 0.
    _desc = _clean(description)
    if _desc:
        _seen_rows = {(_clean(a) + ":" + _clean(b)) for a, b in rows}
        _desc_lines = []
        for _ln in _desc.replace("\r", "").split("\n"):
            _s = _clean(_ln)
            if len(_s) < 2 or _is_input_junk(_s) or _is_contaminated(_s):
                continue
            if _s in _desc_lines:
                continue
            _desc_lines.append(_s)
        if _desc_lines:
            lines.append("")
            lines.append("■ 원문 상세")
            for _s in _desc_lines[:40]:
                lines.append(_s)   # ★ 원문 라인 통째(숫자 조각으로 쪼개지 않음)

    # 확인된 상세(키워드·옵션·스펙·원문상세)가 하나도 없으면 창작 대신 입력 요청(정직).
    if not kws and not rows and not _clean(description):
        lines.append("")
        lines.append("· 확인된 상세 정보가 부족합니다. 소재·사이즈·용도 등을 직접 입력해 주세요.")
    # 안내 틀(정직 boilerplate — 없는 스펙 창작 아님, 항상 참인 일반 안내)
    lines.append("")
    lines.append("■ 배송·구매대행 안내")
    lines.append("· 해외 구매대행 상품으로, 주문 후 현지 배송·통관을 거쳐 발송됩니다.")
    lines.append("· 모니터·조명 환경에 따라 실제 색상과 차이가 있을 수 있습니다.")
    lines.append("· 정확한 사이즈·소재는 위 옵션·상세 정보를 확인해 주세요.")
    lines.append("· 교환·반품은 판매 마켓과 구매대행 정책을 따릅니다.")
    return "\n".join(lines).strip()


class AITranslator:
    """상품 메타데이터 → 한국어 번역 + 마켓별 광고 카피 생성."""

    def __init__(self) -> None:
        self.provider = self._select_provider()
        logger.info("AITranslator 초기화: provider=%s", self.provider)

    def _select_provider(self) -> str:
        """사용 가능한 AI 프로바이더 선택. v44 0-1: 값의 따옴표/공백을 제거해 읽는다."""
        from src.utils.env import env_present
        if env_present("OPENAI_API_KEY"):
            return "openai"
        if env_present("DEEPL_API_KEY"):
            return "deepl"
        return "stub"

    # v87-W7 item1: 번역 프로바이더 **체인** — 하나 실패하면 다음 시도. 기본 순서는 브리프대로 **무료 우선**
    #   (mymemory=무키·무가입) → 저가/키필요(deepl, 키 있을 때만) → OpenAI(키 있을 때만). env
    #   `TRANSLATE_PROVIDER_CHAIN`(쉼표구분)로 순서·선택 오버라이드(예: "openai,mymemory"로 품질 우선).
    #   mymemory는 `TRANSLATE_DISABLE_MYMEMORY=1`로 끌 수 있다(사설 프록시 등 외부호출 차단 환경).
    def _provider_chain(self, src_lang: str = None) -> list:
        from src.utils.env import env_present
        override = os.getenv("TRANSLATE_PROVIDER_CHAIN", "").strip()
        # v87-W7 회수: 무료 우선 → 저가/키필요(papago=ko·ja·zh 도메인 최적 → deepl 고품질 → azure 광역)
        #   → OpenAI 최후. Papago/Azure는 오너가 등록한 확정 env명으로 배선(공식 엔드포인트만).
        if override:
            names = [n.strip().lower() for n in override.split(",") if n.strip()]
        elif src_lang == "ja":
            # v87-W8 item3: ja는 mymemory 저품질(라쿠텐 상용구 오역) → papago/deepl 선행, mymemory 최후순위.
            names = ["papago", "deepl", "azure", "openai", "mymemory"]
        else:
            names = ["mymemory", "papago", "deepl", "azure", "openai"]
        chain = []
        for n in names:
            if n == "openai" and not env_present("OPENAI_API_KEY"):
                continue
            if n == "deepl" and not env_present("DEEPL_API_KEY"):
                continue
            # Papago(NCP)는 CLIENT_ID·SECRET 둘 다 있어야 호출 가능.
            if n == "papago" and not (env_present("NCP_PAPAGO_CLIENT_ID") and env_present("NCP_PAPAGO_CLIENT_SECRET")):
                continue
            if n == "azure" and not env_present("AZURE_TRANSLATOR_KEY"):
                continue
            if n == "mymemory" and os.getenv("TRANSLATE_DISABLE_MYMEMORY") == "1":
                continue
            if n in ("mymemory", "papago", "deepl", "azure", "openai"):
                chain.append(n)
        return chain

    def translate_product(self, source: dict) -> dict:
        """상품 메타데이터를 한국어로 번역하고 마켓별 카피 생성 — **프로바이더 체인**(순차 폴백).

        반환: {title_ko, description_ko, copy_*, provider, attempts:[{provider,ok,error}], (translate_error)}
        - 첫 성공 프로바이더의 결과 반환 + attempts(시도 이력). 전부 실패면 원문 유지 + provider="none" +
          translate_error(마지막 사유). 키/프로바이더 전무면 stub(원문 유지, 실패 아님).
        """
        # v87-W8 item3: 라쿠텐 상용구(楽ギフ_包装·あす着·送料無料 등)를 **번역 전** 제목에서 제거
        #   (상품 속성어 보존). 안 그러면 mymemory가 상용구를 오역해 "Rakugifu_포장 내일 착용 서신"류가 남는다.
        title = strip_market_boilerplate(source.get("title", ""))
        description = source.get("description", "")

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — AITranslator stub 모드")
            return {"title_ko": title, "description_ko": description, "provider": "stub",
                    "copy_coupang": f"[stub] {title}", "copy_smartstore": f"[stub] {title}",
                    "copy_11st": f"[stub] {title}", "attempts": []}

        # v87-W8 item3 / v87-W9 item1: 소스 언어별 체인 — 가나·한자 1자라도 있으면 ja(라틴 비율 무관).
        #   ja는 papago/deepl 선행, mymemory 후순위(저품질 로마자화 방지). 감지·체인을 결과에 기록(진단).
        _src = _route_src_lang((title or "") + " " + (description or ""))
        chain = self._provider_chain(src_lang=_src)
        if not chain:
            logger.warning("AI 번역 프로바이더 없음(키·무료 모두 불가) — 원본 반환 (stub 모드)")
            return {"title_ko": title, "description_ko": description, "provider": "stub",
                    "copy_coupang": f"[stub] {title}", "copy_smartstore": f"[stub] {title}",
                    "copy_11st": f"[stub] {title}", "attempts": []}

        import time as _time
        attempts = []
        for name in chain:
            _t0 = _time.time()
            try:
                if name == "mymemory":
                    res = self._translate_mymemory(title, description)
                elif name == "papago":
                    res = self._translate_papago(title, description)
                elif name == "deepl":
                    res = self._translate_deepl(title, description)
                elif name == "azure":
                    res = self._translate_azure(title, description)
                elif name == "openai":
                    res = self._translate_openai(title, description)
                else:
                    continue
            except Exception as exc:
                res = {"provider": name + "-fallback", "error": classify_translate_error(exc)}
            ok = str(res.get("provider") or "") == name and not res.get("error")
            attempts.append({"provider": name, "ok": bool(ok), "error": str(res.get("error") or ""),
                             "ms": int((_time.time() - _t0) * 1000)})   # v87-W7: 소요 시간 기록
            if ok:
                res["attempts"] = attempts
                res["detected_lang"] = _src          # v87-W9 item1: 감지 언어·선택 체인 기록(진단만으로 판독)
                res["chain"] = list(chain)
                return res
            logger.warning("[번역 체인] %s 실패(%s) → 다음 프로바이더", name, res.get("error") or "원인 미상")

        # 체인 전부 실패 → 원문 유지(정직 실패). 마지막 프로바이더·사유를 보존(드로어·하위호환 진단).
        _last = attempts[-1]["provider"] if attempts else ""
        _reason = (attempts[-1]["error"] if attempts else "") or "번역 실패"
        # v87-W7 회수: 실패 메시지에 프로바이더명 명시("OpenAI: 결제 한도 초과" 식) — 어느 단이 죽었는지 즉시 파악.
        _err = f"{provider_label(_last)}: {_reason}" if _last else _reason
        return {"title_ko": title, "description_ko": description,
                "provider": (_last + "-fallback") if _last else "none",
                "error": _err, "translate_error": _err, "attempts": attempts,
                "detected_lang": _src, "chain": list(chain),
                "copy_coupang": f"[fallback] {title}", "copy_smartstore": f"[fallback] {title}",
                "copy_11st": f"[fallback] {title}"}

    def translate_options(self, options: list) -> dict:
        """v87-W9 item3: 옵션명·값(ブラウン→브라운) 번역 + **원문 보존**. 체인 경유(ja면 papago 선두).

        입력: [{name, values:[...]}]. 반환: {"options":[{name, name_ko, values, values_ko}], "provider", "translated": bool}
        원문 보존: values/name은 그대로 두고 *_ko를 병기. 실패 시 *_ko=원문(가짜 번역 0).
        """
        opts = [o for o in (options or []) if isinstance(o, dict)]
        if not opts:
            return {"options": [], "provider": "none", "translated": False}
        # 고유 용어 수집(옵션명 + 값) → 한 번에 매핑(중복 호출 최소, 최대 40개).
        terms = []
        for o in opts:
            nm = str(o.get("name") or "").strip()
            if nm:
                terms.append(nm)
            for v in (o.get("values") or ([o.get("value")] if o.get("value") is not None else [])):
                sv = str(v or "").strip()
                if sv:
                    terms.append(sv)
        uniq = []
        for t in terms:
            if t not in uniq:
                uniq.append(t)
        uniq = uniq[:40]
        # 이미 한국어면 번역 불필요.
        src = _route_src_lang(" ".join(uniq))
        if src == "ko" or not uniq:
            mapping = {t: t for t in uniq}
            provider = "none"
            translated = False
        else:
            # 짧은 용어들을 개행으로 이어 1콜(체인)로 번역 → 줄 단위 매핑(수·순서 보존 시).
            #   제목이 아닌 **설명**으로 전달(제목 경로의 상용구 제거가 개행을 뭉개지 않게).
            joined = "\n".join(uniq)
            out = self.translate_product({"title": "", "description": joined})   # 빈 제목(감지 오염 방지)
            provider = out.get("provider", "none")
            translated = provider not in ("none", "stub", "") and not str(provider).endswith("-fallback")
            ko_lines = [l.strip() for l in str(out.get("description_ko") or "").split("\n") if l.strip()]
            if translated and len(ko_lines) == len(uniq):
                mapping = {uniq[i]: ko_lines[i] for i in range(len(uniq))}
            else:
                mapping = {t: t for t in uniq}      # 매핑 어긋나면 원문 유지(가짜 번역 금지)
                translated = False
        out_opts = []
        for o in opts:
            nm = str(o.get("name") or "").strip()
            vals = [str(v or "").strip() for v in (o.get("values") or ([o.get("value")] if o.get("value") is not None else [])) if str(v or "").strip()]
            out_opts.append({
                "name": nm, "name_ko": mapping.get(nm, nm),
                "values": vals, "values_ko": [mapping.get(v, v) for v in vals]})
        return {"options": out_opts, "provider": provider, "translated": translated}

    def _translate_mymemory(self, title: str, description: str) -> dict:
        """v87-W7: MyMemory 무료 번역 API(무키·무가입). 제목·상세 각각 요청, 한국어로.
        실패(HTTP·쿼터·파싱)면 error를 담아 반환 → 체인이 다음 프로바이더로 폴백."""
        import requests as _req

        src = _route_src_lang((title or "") + " " + (description or ""))
        if src == "ko":   # 이미 한국어면 번역 불필요(원문 유지, 실패 아님이지만 체인상 성공 처리).
            _record_translate(True, provider="mymemory")
            return {"title_ko": title, "description_ko": description, "provider": "mymemory",
                    "copy_coupang": self._copy_template(title, "coupang"),
                    "copy_smartstore": self._copy_template(title, "smartstore"),
                    "copy_11st": self._copy_template(title, "11st")}

        def _one(text: str) -> str:
            text = (text or "").strip()
            if not text:
                return text
            # MyMemory 단일 요청 상한(약 500자) — 초과분은 그대로 두지 않고 문장 경계로 잘라 앞부분만(정직: 부분).
            snippet = text[:480]
            r = _req.get("https://api.mymemory.translated.net/get",
                         params={"q": snippet, "langpair": f"{src}|ko"}, timeout=12)
            r.raise_for_status()
            j = r.json()
            if int(j.get("responseStatus") or 0) != 200:
                raise RuntimeError(f"MyMemory 응답 상태 {j.get('responseStatus')}")
            out = ((j.get("responseData") or {}).get("translatedText") or "").strip()
            if not out:
                raise RuntimeError("MyMemory 빈 응답")
            # 원문보다 길어진 미번역 잔여(원문 그대로 반환류)면 원문 유지.
            return out if out and out.lower() != snippet.lower() else text

        try:
            title_ko = _one(title) or title
            description_ko = _one(description) or description
            _record_translate(True, provider="mymemory")
            return {"title_ko": title_ko, "description_ko": description_ko, "provider": "mymemory",
                    "copy_coupang": self._copy_template(title_ko, "coupang"),
                    "copy_smartstore": self._copy_template(title_ko, "smartstore"),
                    "copy_11st": self._copy_template(title_ko, "11st")}
        except Exception as exc:
            reason = record_translate_failure(exc, "mymemory")   # v87-W7a: 원 응답 코드·바디까지 계측 적재
            logger.warning("MyMemory 번역 실패(%s): %s", reason, exc)
            return {"title_ko": title, "description_ko": description,
                    "provider": "mymemory-fallback", "error": reason}

    def generate_marketplace_copy(self, product: dict, marketplace: str) -> str:
        """마켓별 톤앤매너에 맞는 광고 카피 생성.

        Args:
            product: {"title": str, "description": str, ...}
            marketplace: "coupang" | "smartstore" | "11st"

        Returns:
            광고 카피 문자열
        """
        title = product.get("title", "")
        hint = _MARKET_PROMPTS.get(marketplace, "간결하게 작성.")

        if self.provider == "openai" and not _dry_run():
            return self._copy_openai(title, marketplace, hint)
        if self.provider == "deepl" and not _dry_run():
            # DeepL은 번역만 지원 — 카피는 template 기반
            return self._copy_template(title, marketplace)

        return self._copy_template(title, marketplace)

    def generate_description(self, product: dict) -> dict:
        """v39-E2 #3: 상세설명이 없거나 빈약할 때 한국어 상세 '초안'을 생성.

        입력: {title, category, specs:[(label,value)], keywords, brand}
        출력: {"text": str, "provider": "openai"|"stub", "is_draft": True}
        - 큐레이터 톤(건방지지만 공손한 높임말). 없는 수치·허위 스펙 지어내기 금지(확인된 정보만).
        - OPENAI 키 미설정/dry-run/실패 시 provider="stub" — 가짜 상세 생성 금지, 확인된 정보만 구조화.
        """
        title = (product.get("title") or "").strip()
        category = (product.get("category") or "").strip()
        brand = (product.get("brand") or "").strip()

        # v87-W5: 입력 전처리 — 마켓 UI 쓰레기(레ビュー·신고·송료무료 등)를 스펙/키워드에서 제거한 뒤
        #   초안에 넣는다. 종전엔 라쿠텐 UI 문구가 스펙/키워드에 섞여 초안이 오염됐다(오너 TSUMUGI).
        keywords = _clean_keywords_for_draft(product.get("keywords") or [])
        specs = _clean_specs_for_draft(product.get("specs") or [])

        # 옵션(색상/사이즈 등)을 스펙 힌트로 흡수해 두면 키없음 구조초안이 풍부해진다.
        options = product.get("options") or []
        description = str(product.get("description") or "").strip()   # v87-W7 item4: 원문 상세 라인 보존용

        # v87-W7a: 키 부재 vs 키 있으나 호출 실패를 **구분**한다. 종전엔 openai 실패도 provider="stub"로
        #   폴백해 UI가 "AI 키가 설정되지 않아…"로 뭉갰다(키 있는데 미설정 오귀인 = 오너 결함). draft_status로
        #   3분: openai(성공) / no_openai_key(키 부재) / openai_error(키 있으나 호출 실패+사유). 실패는 계측 적재.
        from src.utils.env import env_present
        draft_status = "no_openai_key"
        draft_error = ""
        if env_present("OPENAI_API_KEY") and not _dry_run():
            try:
                _res = self._describe_openai(title, category, specs, keywords, brand)
                _record_translate(True, provider="openai-draft")
                _res.setdefault("draft_status", "openai")
                return _res
            except Exception as exc:
                draft_error = record_translate_failure(exc, "openai-draft")   # v87-W7a: 원 응답 코드·바디 적재
                draft_status = "openai_error"
                logger.warning("AI 상세 생성 실패(%s) — 구조화 폴백(키 있음, 호출 실패): %s", draft_error, exc)

        # v56 STEP3: 키 없음/실패 모드 = 확인된 정보(제목·카테고리·키워드·옵션·스펙)만으로 **구조 초안**.
        #   ★ '- k: v' 플레이스홀더 버그 수리: 실키·실값만 렌더, 값 없는 행은 생략, 창작 0.
        #   v87-W7 item4: 원문 상세를 넘겨 '숫자 조각 리스트' 대신 원문 스펙 라인을 통째 보존.
        return {"text": _structured_draft(title, category, keywords, specs, options, brand, description),
                "provider": "stub", "is_draft": True,
                "draft_status": draft_status, "draft_error": draft_error}

    def _describe_openai(self, title, category, specs, keywords, brand) -> dict:
        import requests as _req
        api_key = __import__("src.utils.env", fromlist=["env_str"]).env_str("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        spec_txt = "\n".join(f"- {l}: {v}" for l, v in specs[:20]) or "(스펙 표 없음)"
        kw_txt = ", ".join(keywords[:15]) or "(없음)"
        # v39-E2 #3 + CLAUDE.md: humanizer 의도 적용 — 사람이 직접 쓴 것처럼(AI 티·번역체·과장 금지).
        prompt = (
            "다음 상품의 한국어 상세설명 '초안'을 작성하세요. "
            # v87-W5: 입력(상품명·스펙·키워드)이 외국어(일본어·중국어·영어)일 수 있다. 결과는 처음부터 끝까지
            #   **자연스러운 한국어 판매 문안**이어야 하며, 원문 언어 조각을 남기거나 스펙 라벨/값을 기계 직역하지 않는다.
            "입력 정보(상품명·스펙·키워드)가 외국어(일본어 등)일 수 있습니다. **결과물은 처음부터 끝까지 자연스러운 "
            "한국어 판매 문안**으로 작성하고, 원문 언어(일본어·중국어 등) 조각을 그대로 남기거나 스펙 라벨·값을 기계 "
            "번역기 말투로 직역하지 마세요. 스펙은 한국어로 자연스럽게 옮겨 정리하고, 소구점은 문장으로 풀어 주세요. "
            "쇼핑몰 UI 문구(리뷰/후기/신고/장바구니/찜/쿠폰/포인트/배송 배너 등)는 상품 정보가 아니므로 **무시**하세요. "
            "사람이 직접 쓴 것처럼 자연스럽게 — AI 특유의 정형 문장·번역체·진부한 도입(\"여러분~\", \"~를 소개합니다\")·"
            "감탄 남발을 피하고, 짧고 구체적인 문장으로. "
            "톤: 건방지지 않게 공손하되 군더더기 없는 큐레이터 높임말. "
            "확인된 정보만 사용하고, 없는 수치·소재·인증·원산지 등은 절대 지어내지 마세요(모르면 쓰지 않음). "
            "구성: 도입 1문장 → 특징 3~5(불릿) → 사용/주의 1~2 → 마무리 1문장. "
            "마켓 금지어(최고/최상/유일/100%/완벽/의학·과학 효능 단정 등) 회피. "
            "이모지·해시태그 금지.\n\n"
            f"상품명: {title}\n브랜드: {brand or '(미상)'}\n카테고리: {category or '(미상)'}\n"
            f"스펙:\n{spec_txt}\n키워드: {kw_txt}\n"
        )
        resp = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.5},
            timeout=20,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return {"text": text, "provider": "openai", "is_draft": True}

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _translate_openai(self, title: str, description: str) -> dict:
        """OpenAI GPT-4o-mini로 번역 + 카피 생성."""
        try:
            import requests as _req
            api_key = __import__("src.utils.env", fromlist=["env_str"]).env_str("OPENAI_API_KEY")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            # v60 STEP3: 이커머스 특화 프롬프트(직역투·음차 박멸). 브랜드/모델/규격 원문 보존, 자연 판매 문체.
            system = (
                "당신은 해외 상품을 한국 오픈마켓(쿠팡·스마트스토어)에 등록하는 전문 상품 번역가입니다. "
                "다음 규칙을 반드시 지키세요.\n"
                "1) 브랜드명·모델명·규격(치수·용량·재질·호환 기종 예: MagSafe, iPhone 15)은 **원문 그대로 보존**"
                " — 억지 음차(예: 안도빌)·직역 금지.\n"
                "2) 마케팅 수식어(ultra-thin, premium 등)는 **자연스러운 한국어 판매 문체**로(예: 초슬림, 프리미엄).\n"
                "3) 단위 변환 금지(inch·mm·g 원문 단위 유지). 없는 스펙 창작 금지.\n"
                "4) 상품명은 한국 관례 **브랜드 + 핵심 스펙 + 용도** 순, 자연스러운 명사구(어색한 조사·번역기 말투 금지).\n"
                "5) 설명은 원문 불릿(·) 구조를 유지하며 한국어로."
            )
            prompt = (
                "아래 상품을 위 규칙대로 한국어로 번역하고, 마켓용 판매 카피도 만드세요.\n"
                f"[제목]\n{title}\n\n[설명]\n{description}\n\n"
                "JSON으로만 답변:\n"
                '{"title_ko":"브랜드+핵심스펙+용도 자연문","description_ko":"불릿 유지 한국어",'
                '"copy_coupang":"...","copy_smartstore":"...","copy_11st":"..."}'
            )
            # v87-W6 item 2 근원: max_tokens=900 고정이 **긴 상세(일본어 721자 등) + 제목 + 마켓 카피 3종**을
            #   한 JSON으로 뽑을 때 출력이 잘려 json.loads 실패 → openai-fallback(원문 유지)로 '조용한 실패 다발'
            #   이었다. 입력 길이에 비례해 상한을 잡고(캡 3000 — AI 예산 존중), 타임아웃도 길이 대응해 늘린다.
            _in_len = len(title) + len(description)
            _max_tokens = max(900, min(3000, 1000 + _in_len))
            _timeout = 30 if _in_len > 400 else 15
            payload = {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": _max_tokens,
                "response_format": {"type": "json_object"},
            }
            resp = _post_with_429_retry(   # v87-W8 item4: 429면 짧은 백오프 1회 재시도
                _req, "https://api.openai.com/v1/chat/completions",
                headers=headers, json=payload, timeout=_timeout,
            )
            content = resp.json()["choices"][0]["message"]["content"]
            import json
            result = json.loads(content)
            result["provider"] = "openai"
            _record_translate(True, provider="openai")   # v87-W6 계측
            return result
        except Exception as exc:
            reason = record_translate_failure(exc, "openai")   # v87-W7a: 원 응답 코드·바디까지 계측 적재
            logger.warning("OpenAI 번역 실패(%s): %s", reason, exc)   # v64 STEP6: 원인 로깅(무음 금지)
            return {
                "title_ko": title,
                "description_ko": description,
                "copy_coupang": f"[openai-fallback] {title}",
                "copy_smartstore": f"[openai-fallback] {title}",
                "copy_11st": f"[openai-fallback] {title}",
                "provider": "openai-fallback",
                "error": reason,
            }

    def _translate_deepl(self, title: str, description: str) -> dict:
        """DeepL로 번역 (카피는 template 기반)."""
        try:
            import requests as _req
            api_key = __import__("src.utils.env", fromlist=["env_str"]).env_str("DEEPL_API_KEY")
            base_url = (
                "https://api-free.deepl.com/v2/translate"
                if api_key.endswith(":fx")
                else "https://api.deepl.com/v2/translate"
            )
            params = {
                "auth_key": api_key,
                "text": [title, description],
                "target_lang": "KO",
            }
            resp = _req.post(base_url, data=params, timeout=10)
            resp.raise_for_status()
            translations = resp.json().get("translations", [])
            title_ko = translations[0]["text"] if len(translations) > 0 else title
            description_ko = translations[1]["text"] if len(translations) > 1 else description
            _record_translate(True, provider="deepl")   # v87-W6 계측
            return {
                "title_ko": title_ko,
                "description_ko": description_ko,
                "copy_coupang": self._copy_template(title_ko, "coupang"),
                "copy_smartstore": self._copy_template(title_ko, "smartstore"),
                "copy_11st": self._copy_template(title_ko, "11st"),
                "provider": "deepl",
            }
        except Exception as exc:
            reason = record_translate_failure(exc, "deepl")   # v87-W7a: 원 응답 코드·바디까지 계측 적재
            logger.warning("DeepL 번역 실패(%s): %s", reason, exc)   # v64 STEP6: 원인 로깅(무음 금지)
            return {
                "title_ko": title,
                "description_ko": description,
                "copy_coupang": f"[deepl-fallback] {title}",
                "copy_smartstore": f"[deepl-fallback] {title}",
                "copy_11st": f"[deepl-fallback] {title}",
                "provider": "deepl-fallback",
                "error": reason,
            }

    def _translate_papago(self, title: str, description: str) -> dict:
        """v87-W7 회수: 네이버 클라우드(NCP) Papago NMT — 공식 엔드포인트. ko·ja·zh 도메인 최적.
        env: NCP_PAPAGO_CLIENT_ID / NCP_PAPAGO_CLIENT_SECRET. 실패면 error 담아 체인 폴백."""
        import requests as _req
        _env = __import__("src.utils.env", fromlist=["env_str"])
        cid = _env.env_str("NCP_PAPAGO_CLIENT_ID")
        secret = _env.env_str("NCP_PAPAGO_CLIENT_SECRET")
        src = _route_src_lang((title or "") + " " + (description or ""))
        if src == "ko":   # 이미 한국어 → 번역 불필요(성공 처리, 원문 유지).
            _record_translate(True, provider="papago")
            return {"title_ko": title, "description_ko": description, "provider": "papago",
                    "copy_coupang": self._copy_template(title, "coupang"),
                    "copy_smartstore": self._copy_template(title, "smartstore"),
                    "copy_11st": self._copy_template(title, "11st")}
        headers = {"x-ncp-apigw-api-key-id": cid, "x-ncp-apigw-api-key": secret}

        def _one(text: str) -> str:
            text = (text or "").strip()
            if not text:
                return text
            r = _req.post("https://papago.apigw.ntruss.com/nmt/v1/translation",
                          headers=headers, data={"source": src, "target": "ko", "text": text[:4900]},
                          timeout=10)
            r.raise_for_status()
            out = (((r.json() or {}).get("message") or {}).get("result") or {}).get("translatedText", "")
            if not out:
                raise RuntimeError("Papago 빈 응답")
            return out
        try:
            title_ko = _one(title) or title
            description_ko = _one(description) or description
            _record_translate(True, provider="papago")
            return {"title_ko": title_ko, "description_ko": description_ko, "provider": "papago",
                    "copy_coupang": self._copy_template(title_ko, "coupang"),
                    "copy_smartstore": self._copy_template(title_ko, "smartstore"),
                    "copy_11st": self._copy_template(title_ko, "11st")}
        except Exception as exc:
            reason = record_translate_failure(exc, "papago")   # v87-W7a: 원 응답 코드·바디까지 계측 적재
            logger.warning("Papago 번역 실패(%s): %s", reason, exc)
            return {"title_ko": title, "description_ko": description,
                    "provider": "papago-fallback", "error": reason}

    def _translate_azure(self, title: str, description: str) -> dict:
        """v87-W7 회수: Azure Translator(Cognitive Services) — 공식 엔드포인트, 소스 자동 감지.
        env: AZURE_TRANSLATOR_KEY (+ AZURE_TRANSLATOR_REGION, 지역 리소스면 필수). 실패면 체인 폴백."""
        import requests as _req
        _env = __import__("src.utils.env", fromlist=["env_str"])
        key = _env.env_str("AZURE_TRANSLATOR_KEY")
        region = _env.env_str("AZURE_TRANSLATOR_REGION")
        headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/json"}
        if region:
            headers["Ocp-Apim-Subscription-Region"] = region
        try:
            r = _req.post("https://api.cognitive.microsofttranslator.com/translate",
                          params={"api-version": "3.0", "to": "ko"}, headers=headers,
                          json=[{"Text": title or ""}, {"Text": description or ""}], timeout=10)
            r.raise_for_status()
            data = r.json()

            def _pick(i, fallback):
                try:
                    return (data[i].get("translations") or [{}])[0].get("text") or fallback
                except (IndexError, AttributeError, KeyError):
                    return fallback
            title_ko = _pick(0, title)
            description_ko = _pick(1, description)
            _record_translate(True, provider="azure")
            return {"title_ko": title_ko, "description_ko": description_ko, "provider": "azure",
                    "copy_coupang": self._copy_template(title_ko, "coupang"),
                    "copy_smartstore": self._copy_template(title_ko, "smartstore"),
                    "copy_11st": self._copy_template(title_ko, "11st")}
        except Exception as exc:
            reason = record_translate_failure(exc, "azure")   # v87-W7a: 원 응답 코드·바디까지 계측 적재
            logger.warning("Azure 번역 실패(%s): %s", reason, exc)
            return {"title_ko": title, "description_ko": description,
                    "provider": "azure-fallback", "error": reason}

    def _copy_openai(self, title: str, marketplace: str, hint: str) -> str:
        """OpenAI로 마켓별 카피 생성."""
        try:
            import requests as _req
            import json
            api_key = __import__("src.utils.env", fromlist=["env_str"]).env_str("OPENAI_API_KEY")
            prompt = f"상품명: {title}\n마켓: {marketplace}\n조건: {hint}\n광고 카피 1개만 작성."
            payload = {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 200,
            }
            resp = _req.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("OpenAI 카피 생성 실패: %s", exc)
            return self._copy_template(title, marketplace)

    @staticmethod
    def _copy_template(title: str, marketplace: str) -> str:
        """키 없을 때 template 기반 카피 생성."""
        templates = {
            "coupang": f"✅ {title} | 빠른 배송 | 최저가 보장 | 로켓배송 가능",
            "smartstore": (
                f"{title}\n"
                "정품 보장 · 당일 발송 · 무료 교환\n"
                "네이버 쇼핑 최저가 도전"
            ),
            "11st": f"[특가] {title} — 지금 구매하면 최대 할인!",
        }
        return templates.get(marketplace, f"{title} — 구매 추천")
