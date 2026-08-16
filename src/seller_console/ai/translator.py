"""src/seller_console/ai/translator.py — 상품 번역 + 마켓별 광고 카피 자동 생성 (Phase 130).

우선순위:
1. OPENAI_API_KEY 활성 → GPT-4o-mini 사용
2. DEEPL_API_KEY 활성 → DeepL (번역만, 카피는 template 기반)
3. 둘 다 없음 → 원본 반환 + warning 로그

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


# v87-W6 item 2: 번역 실패 다발 조사 — **계측**(호출 n·성공 n·실패 n·사유별). 번역 무료 쿼터 회계와
#   완전히 별개인 읽기 전용 관측 카운터(쿼터 무손대). 프로세스 인메모리 누적, get_translate_stats()로 노출.
_TR_STATS = {"calls": 0, "ok": 0, "fail": 0, "by_reason": {}}
_TR_STATS_LOCK = threading.Lock()


def _record_translate(ok: bool, reason: str = "", provider: str = "") -> None:
    with _TR_STATS_LOCK:
        _TR_STATS["calls"] += 1
        if ok:
            _TR_STATS["ok"] += 1
        else:
            _TR_STATS["fail"] += 1
            key = (reason or "원인 미상")[:80]
            _TR_STATS["by_reason"][key] = _TR_STATS["by_reason"].get(key, 0) + 1


def get_translate_stats() -> dict:
    """번역 호출 계측 스냅샷(읽기 전용) — 호출/성공/실패/사유별. 진단·리포트용(쿼터 회계와 무관)."""
    with _TR_STATS_LOCK:
        return {"calls": _TR_STATS["calls"], "ok": _TR_STATS["ok"], "fail": _TR_STATS["fail"],
                "by_reason": dict(_TR_STATS["by_reason"])}


def reset_translate_stats() -> None:
    """계측 리셋(테스트·리포트 구간 측정용)."""
    with _TR_STATS_LOCK:
        _TR_STATS["calls"] = 0
        _TR_STATS["ok"] = 0
        _TR_STATS["fail"] = 0
        _TR_STATS["by_reason"] = {}


def classify_translate_error(exc: Exception) -> str:
    """v64 STEP6: 번역 실패 원인을 사람이 읽을 한 줄로 분류(무음 금지·오귀인 금지).

    키가 설정돼 있는데 실패한 경우, '키 미설정'으로 오귀인하지 않고 실제 원인을 표기한다.
    - 인증(401/403) → 키가 잘못됐거나 만료됨
    - 모델(404/400 model) → 모델명(OPENAI_MODEL)이 잘못됨
    - 쿼터(429) → 사용량/결제 한도 초과
    - 타임아웃 → 응답 지연
    - 네트워크 → 연결 실패
    """
    s = str(exc or "").lower()
    status = None
    resp = getattr(exc, "response", None)
    if resp is not None:
        status = getattr(resp, "status_code", None)
    if status in (401, 403) or "unauthorized" in s or "invalid_api_key" in s or "authenticationerror" in s:
        return "API 키가 잘못됐거나 만료됐어요(키 재발급 후 재설정)"
    if status == 429 or "rate limit" in s or "quota" in s or "insufficient_quota" in s:
        return "API 사용량·결제 한도를 초과했어요(플랜·결제 확인)"
    if status in (404, 400) and "model" in s:
        return "설정한 모델명(OPENAI_MODEL)이 잘못됐어요"
    if "model" in s and ("does not exist" in s or "not found" in s):
        return "설정한 모델명(OPENAI_MODEL)이 잘못됐어요"
    if "timeout" in s or "timed out" in s:
        return "번역 서버 응답이 지연됐어요(잠시 후 재시도)"
    if "connection" in s or "network" in s or "resolve" in s or "ssl" in s:
        return "번역 서버에 연결하지 못했어요(네트워크·프록시 확인)"
    if status:
        return f"번역 API 오류(HTTP {status})"
    return "번역 API 호출에 실패했어요"


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
    def _provider_chain(self) -> list:
        from src.utils.env import env_present
        override = os.getenv("TRANSLATE_PROVIDER_CHAIN", "").strip()
        names = ([n.strip().lower() for n in override.split(",") if n.strip()]
                 if override else ["mymemory", "deepl", "openai"])
        chain = []
        for n in names:
            if n == "openai" and not env_present("OPENAI_API_KEY"):
                continue
            if n == "deepl" and not env_present("DEEPL_API_KEY"):
                continue
            if n == "mymemory" and os.getenv("TRANSLATE_DISABLE_MYMEMORY") == "1":
                continue
            if n in ("mymemory", "deepl", "openai"):
                chain.append(n)
        return chain

    def translate_product(self, source: dict) -> dict:
        """상품 메타데이터를 한국어로 번역하고 마켓별 카피 생성 — **프로바이더 체인**(순차 폴백).

        반환: {title_ko, description_ko, copy_*, provider, attempts:[{provider,ok,error}], (translate_error)}
        - 첫 성공 프로바이더의 결과 반환 + attempts(시도 이력). 전부 실패면 원문 유지 + provider="none" +
          translate_error(마지막 사유). 키/프로바이더 전무면 stub(원문 유지, 실패 아님).
        """
        title = source.get("title", "")
        description = source.get("description", "")

        if _dry_run():
            logger.info("ADAPTER_DRY_RUN=1 — AITranslator stub 모드")
            return {"title_ko": title, "description_ko": description, "provider": "stub",
                    "copy_coupang": f"[stub] {title}", "copy_smartstore": f"[stub] {title}",
                    "copy_11st": f"[stub] {title}", "attempts": []}

        chain = self._provider_chain()
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
                elif name == "deepl":
                    res = self._translate_deepl(title, description)
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
                return res
            logger.warning("[번역 체인] %s 실패(%s) → 다음 프로바이더", name, res.get("error") or "원인 미상")

        # 체인 전부 실패 → 원문 유지(정직 실패). 마지막 프로바이더·사유를 보존(드로어·하위호환 진단).
        _last = attempts[-1]["provider"] if attempts else ""
        _err = (attempts[-1]["error"] if attempts else "") or "번역 실패"
        return {"title_ko": title, "description_ko": description,
                "provider": (_last + "-fallback") if _last else "none",
                "error": _err, "translate_error": _err, "attempts": attempts,
                "copy_coupang": f"[fallback] {title}", "copy_smartstore": f"[fallback] {title}",
                "copy_11st": f"[fallback] {title}"}

    def _translate_mymemory(self, title: str, description: str) -> dict:
        """v87-W7: MyMemory 무료 번역 API(무키·무가입). 제목·상세 각각 요청, 한국어로.
        실패(HTTP·쿼터·파싱)면 error를 담아 반환 → 체인이 다음 프로바이더로 폴백."""
        import requests as _req

        src = _detect_src_lang((title or "") + " " + (description or ""))
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
            reason = classify_translate_error(exc)
            _record_translate(False, reason=reason, provider="mymemory")
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
                draft_error = classify_translate_error(exc)
                draft_status = "openai_error"
                _record_translate(False, reason=draft_error, provider="openai-draft")
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
            resp = _req.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=_timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            import json
            result = json.loads(content)
            result["provider"] = "openai"
            _record_translate(True, provider="openai")   # v87-W6 계측
            return result
        except Exception as exc:
            reason = classify_translate_error(exc)
            _record_translate(False, reason=reason, provider="openai")   # v87-W6 계측(사유별 집계)
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
            reason = classify_translate_error(exc)
            _record_translate(False, reason=reason, provider="deepl")   # v87-W6 계측(사유별 집계)
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
