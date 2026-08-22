"""src/pipeline/coupang_replicate.py — v88-C: 쿠팡 기등록 상품 → 고가브릿지 → 멀티채널 복제 파이프라인 코어.

오너 지시(v88-C): 신규 소싱 아님. 쿠팡 두 계정(고가네 A01381223·우주대행 A01504840) **판매중 상품**을
sourcing_map(ASIN→소싱 URL, LinkLynk/Bluehost 계보)으로 조인 → 소싱 URL을 고가브릿지 **수집 이력**으로
벌크 인입 → 번역·분류·가격까지 자동, **마켓 등록 직전 정지**(등록은 오너 클릭). 이 서버엔 sourcing_map·쿠팡
자격이 없으므로(정직) 라이브 조인/파일럿은 `access_status()`가 막고 **가짜 수치 0**으로 보고한다. 순수 로직은
전량 오프라인 테스트 가능.

불변(오너 금지):
  - 자동 등록 금지(사전검증까지만) · 쿠팡 데이터 무변경(읽기만) · 이미지 2장 초과 금지 · 라쿠텐 서버 크롤 강행 금지
    (차단 리스크 — 분리 보고만) · 별도 우회 경로 발명 금지(수집 5필드·번역 체인·분류는 기존 파이프라인 통과).
  - 가격 = **원가 기준 재계산**(쿠팡 판매가 역산 아님). 공식은 MarginCalculator.reverse_calculate 문서식 재사용:
      판매가 = 총비용 / (1 - 수수료율/100 - 마진율/100).  단 복제는 원가가 이미 랜딩코스트 → 총비용=원가
      (해외직구 국제배송 가산 없음). 채널 수수료: 멀티샵(WC 국내)=3.0(오너 확정), Shopify(글로벌)=env(오너 설정).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# 재사용: 수집 상품 정규화 키(중복 방지, v42 1-3) — 별 구현 금지.
from src.collectors.product_key import normalize_product_key
# 재사용: 금지어 사전(취급금지 term 필터).
from src.ai.forbidden_terms import check_forbidden_terms

# ── 상수 (오너 확정 사실) ──────────────────────────────────────────────────────
DEFAULT_MARGIN_RATE = 27.4          # 오너 확정 목표 마진율(%).
CHANNEL_FEE_RATES = {                # 채널 판매수수료율(%). 멀티샵만 오너 확정(3%).
    "woocommerce_multishop": 3.0,    # WC 멀티샵(국내, alaz).
    # "shopify_global": env SHOPIFY_FEE_RATE (오너 설정 — 미설정 시 None, 가짜 0 금지).
}
# 쿠팡에서 정리한 금지 카테고리(오너 확정 — 계정 간 동일 적용의 채널 확장판).
FORBIDDEN_CATEGORIES = ["향수", "캔들", "애플", "apple", "casetify"]
# 두 계정(오너 확정) — 계정별 자격 env 접두: COUPANG_GOGANE_{ACCESS,SECRET,VENDOR} · COUPANG_WOOJOO_*.
#   VENDOR_ID로 무접두 COUPANG_*(Render 기존 키, 마켓 Health 그린 실증)를 한 계정에만 흡수(이중화 금지).
COUPANG_ACCOUNTS = {
    "gogane": {"vendor_id": "A01381223", "label": "고가네", "prefix": "COUPANG_GOGANE"},
    "woojoo": {"vendor_id": "A01504840", "label": "우주대행", "prefix": "COUPANG_WOOJOO"},
}


def _prefixed_ready(prefix: str) -> bool:
    """계정 접두 자격(ACCESS/SECRET/VENDOR) 전부 존재?

    v88-C 결함: 오너가 **코드베이스 표준 접미**(`_ACCESS_KEY`/`_SECRET_KEY`/`_VENDOR_ID` — 무접두
    `COUPANG_ACCESS_KEY` 등과 동일 규약)로 넣었는데, 예전 이 함수는 축약형(`_ACCESS`/`_SECRET`/`_VENDOR`)만
    봐서 우주대행 자격을 놓쳐 live=false. → **두 규약 모두 허용**(어느 쪽으로 넣어도 감지).
    """
    def present(*names) -> bool:
        return any(os.getenv(f"{prefix}_{n}") for n in names)
    return (present("ACCESS_KEY", "ACCESS")
            and present("SECRET_KEY", "SECRET")
            and present("VENDOR_ID", "VENDOR"))


def resolve_base_account() -> Optional[str]:
    """무접두 COUPANG_*(ACCESS_KEY/SECRET_KEY/VENDOR_ID)가 있으면 **VENDOR_ID로 어느 계정인지 판별**.

    Render 기존 키를 두 계정 중 VENDOR_ID 일치하는 **하나에만** 귀속(양쪽 동시 ready·중복 이중화 금지).
    무접두 키 없음 or VENDOR_ID가 두 계정과 불일치 → None(미상 — 어느 계정에도 부여 안 함, 정직).
    반환: "gogane" | "woojoo" | None.
    """
    if not all(os.getenv(f"COUPANG_{k}") for k in ("VENDOR_ID", "ACCESS_KEY", "SECRET_KEY")):
        return None
    vid = os.getenv("COUPANG_VENDOR_ID", "").strip()
    for acct, meta in COUPANG_ACCOUNTS.items():
        if vid and vid == meta["vendor_id"]:
            return acct
    return None

# sourcing_map 후보 경로(LinkLynk/Bluehost 계보 — 이 서버엔 없을 수 있음).
_SOURCING_MAP_CANDIDATES = [
    os.getenv("SOURCING_MAP_PATH", ""),
    "data/sourcing_map.json",
    "assets/sourcing_map.json",
]


# ── 가격: 원가 기준 재계산 (MarginCalculator 문서식 재사용, 총비용=원가) ─────────
def channel_fee_rate(channel: str) -> Optional[float]:
    """채널 판매수수료율(%). 멀티샵=3.0(확정). shopify_global=env(오너 설정, 미설정=None=정직 미상)."""
    if channel in CHANNEL_FEE_RATES:
        return CHANNEL_FEE_RATES[channel]
    if channel == "shopify_global":
        raw = os.getenv("SHOPIFY_FEE_RATE", "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def recalc_channel_price(cost_krw: float, channel: str, margin_rate: float = DEFAULT_MARGIN_RATE) -> dict:
    """원가 기준 판매가 재계산 — 판매가 = 원가 / (1 - 수수료율/100 - 마진율/100), 100원 올림.

    쿠팡 판매가 역산 아님(오너 명시). 총비용=원가(랜딩코스트, 국제배송 미가산 — 복제이므로).
    수수료율 미상(shopify env 미설정)이면 가짜 0 대신 ok=False 정직 반환.
    """
    fee = channel_fee_rate(channel)
    if fee is None:
        return {"ok": False, "reason": f"채널 수수료율 미상({channel}) — SHOPIFY_FEE_RATE 등 오너 설정 필요",
                "channel": channel, "cost_krw": cost_krw}
    denom = 1 - (fee / 100.0) - (margin_rate / 100.0)
    if denom <= 0:
        return {"ok": False, "reason": f"마진율({margin_rate}%)+수수료율({fee}%) 합이 100% 초과",
                "channel": channel, "cost_krw": cost_krw}
    optimal = float(cost_krw) / denom
    rounded = int((optimal + 99) // 100) * 100          # 100원 올림(기존 관례)
    return {"ok": True, "channel": channel, "cost_krw": float(cost_krw), "fee_rate": fee,
            "margin_rate": margin_rate, "sale_price_krw": rounded, "optimal_krw": optimal}


# ── 취급금지 필터 (금지어 term + 금지 카테고리 + 주입 blacklist) ─────────────────
def _term_hit(term: str, text_lower: str) -> bool:
    """금지 term이 text에 걸리나. **오탐 방지(오너 승인):**
    - ASCII 토큰/구(bose·keen·ping·lodge·le creuset…) → **단어경계 매칭**(영숫자 인접 아닐 때만) →
      'shopping'의 'ping', 'dislodge'의 'lodge' 오탐 소멸.
    - 한글/CJK(롯지·나이키·몽클레르…) → **부분일치**(연접 대응: '롯지스킬렛'·'몽클레르패딩'도 잡음).
      등록 직전 정지(오너 검수)라 과탐은 안전, 미탐(롯지)이 위험 — 그래서 CJK는 부분일치 유지.
    """
    t = str(term).strip().lower()
    if not t:
        return False
    if t.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", text_lower) is not None
    return t in text_lower


# 한글 부분일치 오탐 예외([[한글 부분일치 오탐 지뢰]]) — 짧은 블랙리스트 한글이 삼키는 **별개 브랜드**(정탐 보호).
#   예: `보스`(bose)가 `보스미어`(Bossmeer)를 삼킴. 예외 브랜드 span 안에서만 매칭되면 무시(밖에 또 있으면 진짜 히트).
_KO_ALLOW_BRANDS = frozenset({"보스미어"})


def _covered_only_by_allow(term_lower: str, text_lower: str) -> bool:
    """term의 모든 출현이 예외 브랜드 span 안에 갇혀 있으면 True(과탐 → 무시). 밖에도 있으면 False(진짜 히트)."""
    allow_spans = []
    for brand in _KO_ALLOW_BRANDS:
        bl = brand.lower()
        if term_lower not in bl:            # 예외 브랜드가 이 term을 실제로 포함할 때만 의미
            continue
        start = 0
        while True:
            i = text_lower.find(bl, start)
            if i < 0:
                break
            allow_spans.append((i, i + len(bl)))
            start = i + 1
    if not allow_spans:
        return False
    start = 0
    while True:
        i = text_lower.find(term_lower, start)
        if i < 0:
            return True                     # 모든 term 출현이 예외 span에 갇힘
        if not any(s <= i and i + len(term_lower) <= e for s, e in allow_spans):
            return False                    # 예외 밖 출현 → 진짜 히트
        start = i + 1


def is_forbidden(title: str, category: str = "", blacklist: Optional[Iterable[str]] = None) -> Optional[str]:
    """취급금지면 사유 문자열, 아니면 None. blacklist(쿠팡 오너 자산)는 주입(하드코딩 금지)."""
    text = f"{title or ''} {category or ''}".lower()
    for kw in FORBIDDEN_CATEGORIES:
        if _term_hit(kw, text):
            return f"forbidden-category:{kw}"
    for bad in (blacklist or []):
        if _term_hit(bad, text):
            t = str(bad).strip().lower()
            # 한글 term이 예외 브랜드(보스미어 등)의 부분일치일 뿐이면 스킵(정탐 보호). ASCII는 이미 단어경계.
            if not t.isascii() and _covered_only_by_allow(t, text):
                continue
            return f"blacklist:{bad}"
    matches = check_forbidden_terms(title or "")
    if matches:
        return f"forbidden-term:{matches[0].term}"
    return None


# ── 제목 정제 (검수표 title_ko — sanitize_title 재사용 + 파일럿 잡문 제거 + 절단 플래그) ──
# 별점/평점 잡문(한글 + 영문). #검수: FELCO "4.8 out of 5 stars, rating details".
_RATING_RE = re.compile(
    r"[★☆⭐✩✰]+"
    r"|\(?\s*\d(?:\.\d)?\s*(?:out\s+of|/)\s*\d(?:\.\d)?\s*stars?\b"     # 4.8 out of 5 stars / 4.8/5 stars
    r"|,?\s*rating\s*details?\b"                                        # rating details
    r"|\b\d[\d,]*\s*(?:ratings?|reviews?)\b"                            # 1,234 ratings
    r"|\(?\s*(?:평점|별점|리뷰|review|rating)\s*[:：]?\s*\d(?:\.\d)?\s*(?:점|별|/\s*5)?\)?",
    re.I)
_PROMO_BRACKET_RE = re.compile(r"【[^】]*】|〔[^〕]*〕|\[[^\]]*(?:정품|공식|무료배송|특가|세일|쿠폰|이벤트|당일|사은품|送料無料|楽天|ポイント)[^\]]*\]", re.I)
_JP_KANA_RE = re.compile(r"[぀-ヿｦ-ﾟ]+")          # 히라가나·가타카나(반각 포함) — 일문 잔재
_CJK_IDEO_RE = re.compile(r"[㐀-䶿一-鿿]")   # CJK 한자(가나 제외) — 잔존 플래그만(삭제 금지)
_ELLIPSIS_RE = re.compile(r"(?:\.{3,}|…|…)\s*$")
_TRAIL_DASH_RE = re.compile(r"[–—-]\s*$")                    # 대시로 끝나면 절단
_TITLE_MAX = 100                                                     # 쿠팡/마켓 제목 실무 상한(넘으면 절단 의심)
# 지명 잡문 꼬리 제거(#검수: 덴버글라스 "– Denver, CO Map"). US 주(州) 코드일 때만(오탐 방지).
_US_STATES = frozenset("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
_PLACE_TAIL_RE = re.compile(r"\s*[–—-]\s*[A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*)*,\s*(?P<st>[A-Z]{2})\b.*$")
# 절단 판정용 — 완결로 인정하는 흔한 영문 꼬리어(사전 부재 → 화이트리스트). 미포함·단편이면 suspect(정직).
_COMPLETE_TAIL = frozenset("""
set kit bag box case cover stand holder mount clip strap band tool tools knife scissors brush
board mat tray rack shelf light lamp cable charger bottle mug bowl plate spoon fork wand hose
nozzle filter pump valve blade handle grip ring hook pad mask glove gloves sock socks hat cap
belt wallet watch clock mirror frame vase pot planter seed seeds toy game book map sign tag
label sticker magnet battery adapter plug socket switch sensor remote speaker camera phone
tablet laptop mouse keyboard monitor screen drive memory card reader steel stainless wood
wooden bamboo cotton leather metal plastic silicone glass ceramic titanium aluminum brass
copper merino wool nylon resin marble black white red blue green gray grey pink gold silver
brown beige navy teal orange yellow purple inch inches pack set pcs piece pieces count pair
pairs mini small large jumbo pro max plus ultra premium deluxe classic vintage modern portable
foldable adjustable reusable waterproof insulated wireless rechargeable digital smart compact
universal with for and the of trimmer blender cleaner printer scanner cutting sleeve roller
grater whistle cabinet storage massage blanket pillow curtain lantern thermos spatula strainer
organizer diffuser pruner cutter opener grinder slicer peeler whisk ladle tongs
""".split())


def _suspect_tail(s: str) -> bool:
    """영문 꼬리 단편이면 True(절단 의심). 사전 부재 → 완결 화이트리스트 대조.

    소싱맵 원본 name은 name_ko 자체가 절단원(더 긴 원본 없음)이라 대조 불가 → 라틴 꼬리 단편 휴리스틱.
    발명 금지: 확실치 않으면 suspect(정직). 한글 꼬리·완결어·긴 단어(8+)는 미판정(오탐 흡수).
    """
    m = re.search(r"([A-Za-z]+)\s*$", (s or "").strip())     # 마지막 라틴 토큰 전체(한글 꼬리는 무판정)
    if not m:
        return False
    tok = m.group(1).lower()
    # FELCO nit: 단일 문자 사이즈(S·M·L)·사이즈 약어(XS/XL/XXL)는 정상 꼬리 → 절단 아님.
    if tok in ("s", "m", "l", "xs", "xl", "xxl", "xxxl"):
        return False
    if len(tok) == 1:                            # 그 외 단일 라틴 문자 꼬리("… Aluminum W") = 절단 의심
        return True
    return 2 <= len(tok) <= 7 and tok not in _COMPLETE_TAIL


def clean_title_ko(title, url: str = "") -> dict:
    """검수표용 제목 정제. **조용히 자르지 않는다** — 절단은 truncated(하드)/truncated_suspect(소프트) 플래그.

    반환 {"title","truncated","truncated_suspect","cjk_residual","changed"}. sanitize_title(마켓/브랜드/카테고리 꼬리)
    재사용 후 별점·평점(한/영)·프로모괄호·지명꼬리·일문 가나 제거 + 인접 중복어 축약. CJK 한자는 **삭제 안 함**(번역 소관·
    브랜드 소실 위험) — 잔존만 cjk_residual로 표기. 전부 지워지면 원문 보존(빈 결과 금지).
    """
    raw = str(title if title is not None else "").strip()
    if not raw:
        return {"title": "", "truncated": False, "truncated_suspect": False, "cjk_residual": False, "changed": False}
    try:
        from src.collectors.collect_sanitize import sanitize_title
        s = sanitize_title(raw, url)
    except Exception:
        s = raw
    # 하드 절단 신호는 **정제 전**에 포착(말줄임표/대시끝은 정제로 지워지므로).
    hard_trunc = bool(_ELLIPSIS_RE.search(s) or _TRAIL_DASH_RE.search(s) or len(raw) > _TITLE_MAX)
    s = _ELLIPSIS_RE.sub("", s)
    s = _PROMO_BRACKET_RE.sub(" ", s)
    s = _RATING_RE.sub(" ", s)
    m = _PLACE_TAIL_RE.search(s)                                     # 지명 꼬리(US 주 코드일 때만)
    if m and m.group("st").upper() in _US_STATES:
        s = s[:m.start()].rstrip()
    s = _JP_KANA_RE.sub(" ", s)                                     # 일문(가나) 잔재 제거
    s = re.sub(r"[\[\]【】〔〕]", " ", s)                            # 빈 괄호 잔해
    s = re.sub(r"\b(\w{2,})(\s+\1\b)+", r"\1", s, flags=re.I)       # 인접 중복어 축약
    s = re.sub(r"\s+", " ", s).strip(" -–·|,")
    if not s:
        s = raw                                                     # 과도 제거 방어
    truncated = hard_trunc or bool(_TRAIL_DASH_RE.search(s))
    suspect = (not truncated) and _suspect_tail(s)                  # 하드면 suspect 중복 표기 안 함
    return {"title": s, "truncated": truncated, "truncated_suspect": suspect,
            "cjk_residual": bool(_CJK_IDEO_RE.search(s)), "changed": s != raw}


# ── 소싱 소스 분류 (파일럿 우선순위 + 라쿠텐 분리) ──────────────────────────────
def classify_source(url: str) -> str:
    """소싱 URL → shopify_d2c | amazon | rakuten | other. 라쿠텐=서버 크롤 차단(분리 대상)."""
    u = (url or "").lower()
    if "amazon." in u or "/dp/" in u or "/gp/product/" in u:
        return "amazon"
    if "rakuten.co.jp" in u or "r10s.jp" in u:
        return "rakuten"
    if ".myshopify.com" in u or "/products/" in u or "/products.json" in u:
        return "shopify_d2c"
    return "other"


# ── sourcing_map 로드 (없으면 정직 보고) ────────────────────────────────────────
def _best_source_url(entry) -> str:
    """sourcing_map 엔트리 → 수집 가능한 소스 URL 1개(우선순위 최상).

    v88-C 등록 사후 결함: 엔트리는 `{name_ko, sources:[{url, priority}...]}` 형식이라 **top-level url 없음**.
    예전 `v.get("url")`이 None을 반환해 enrich가 URL 미해석 → collect 미실행 → **이미지 0장**. → sources[]에서 해석.
    """
    if not isinstance(entry, dict):
        return str(entry or "")
    direct = entry.get("url") or entry.get("sourcing_url")
    if direct:
        return str(direct)
    sources = entry.get("sources")
    if isinstance(sources, list) and sources:
        def _pri(s):
            try:
                return int((s or {}).get("priority", 999))
            except (TypeError, ValueError):
                return 999
        best = min([s for s in sources if isinstance(s, dict) and s.get("url")], key=_pri, default=None)
        if best:
            return str(best.get("url"))
    return ""


def load_sourcing_map(path: str = "") -> dict:
    """sourcing_map.json 로드 → {available, path, count, map}. 없으면 available=False(가짜 0)."""
    candidates = [path] + _SOURCING_MAP_CANDIDATES if path else _SOURCING_MAP_CANDIDATES
    for cand in candidates:
        if cand and Path(cand).is_file():
            try:
                data = json.loads(Path(cand).read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            # 형식 관용: {asin: url} · [{asin, url}] · {asin: {sources:[{url,priority}]}}. 소스 URL은 _best_source_url로.
            m = {}
            if isinstance(data, dict):
                for k, v in data.items():
                    m[str(k).upper()] = _best_source_url(v)
            elif isinstance(data, list):
                for row in data:
                    if isinstance(row, dict) and row.get("asin"):
                        m[str(row["asin"]).upper()] = _best_source_url(row)
            return {"available": True, "path": cand, "count": len(m), "map": m}
    return {"available": False, "path": None, "count": 0, "map": {},
            "lookup": "LinkLynk/Bluehost 계보 자산 — 오너 액션: 서버에 data/sourcing_map.json 배치 또는 SOURCING_MAP_PATH 설정"}


@dataclass
class JoinRow:
    account: str
    seller_product_id: str
    asin: str
    title: str
    sourcing_url: str
    source: str


@dataclass
class JoinReport:
    on_sale: int = 0                 # 판매중 n
    matched: int = 0                 # 소싱 URL 매칭 m
    unmatched: int = 0               # 미매칭 k
    by_source: dict = field(default_factory=dict)   # 소스별 분포
    rows: list = field(default_factory=list)

    def as_table(self) -> dict:
        return {"판매중": self.on_sale, "매칭": self.matched, "미매칭": self.unmatched,
                "소스분포": self.by_source}


def join_inventory(coupang_items: list, sourcing_map: dict) -> JoinReport:
    """쿠팡 판매중 목록 × sourcing_map(ASIN→URL) 조인 → 수치 보고(1항 수치표).

    coupang_items: [{account, seller_product_id, external_vendor_sku(=ASIN), title}]
    매칭 키 = externalVendorSku(ASIN 계보). 순수 함수(라이브 호출 0) — 입력만으로 결정.
    """
    rep = JoinReport()
    smap = sourcing_map or {}
    for it in coupang_items or []:
        rep.on_sale += 1
        asin = str(it.get("external_vendor_sku") or it.get("asin") or "").upper()
        url = smap.get(asin, "") if asin else ""
        if url:
            src = classify_source(url)
            rep.matched += 1
            rep.by_source[src] = rep.by_source.get(src, 0) + 1
            rep.rows.append(JoinRow(account=str(it.get("account", "")),
                                    seller_product_id=str(it.get("seller_product_id", "")),
                                    asin=asin, title=str(it.get("title", "")),
                                    sourcing_url=url, source=src))
        else:
            rep.unmatched += 1
    return rep


# ── 중복 방지 (멱등) ────────────────────────────────────────────────────────────
def dedup_decision(sourcing_url: str, existing_source_keys: Iterable[str]) -> str:
    """재실행 멱등 — 같은 소스(정규화 키)가 기존에 있으면 'update', 없으면 'new'.

    existing_source_keys = 이미 수집/등록된 소스 URL의 normalize_product_key 집합.
    """
    key = normalize_product_key(sourcing_url or "")
    existing = {k for k in (existing_source_keys or [])}
    return "update" if key in existing else "new"


# ── 파일럿 계획 (등록 직전 정지 — 부작용 0) ─────────────────────────────────────
def plan_pilot(join_rows: list, n: int = 50, prefer: str = "shopify_d2c",
               exclude_sources: Iterable[str] = ("rakuten",)) -> dict:
    """파일럿 대상 선정 — 매칭분 중 prefer 소스 우선, 라쿠텐 제외(서버 크롤 차단). 부작용 0(계획만).

    반환: {selected:[JoinRow…], count, prefer, excluded_rakuten, by_source}. **등록은 하지 않는다.**
    """
    exclude = set(exclude_sources or [])
    usable = [r for r in (join_rows or []) if r.source not in exclude]
    usable.sort(key=lambda r: 0 if r.source == prefer else 1)     # prefer 소스 앞으로(안정 정렬)
    selected = usable[:max(0, int(n))]
    by_source = {}
    for r in selected:
        by_source[r.source] = by_source.get(r.source, 0) + 1
    excluded_rakuten = sum(1 for r in (join_rows or []) if r.source == "rakuten")
    return {"selected": selected, "count": len(selected), "prefer": prefer,
            "excluded_rakuten": excluded_rakuten, "by_source": by_source,
            "note": "마켓 등록 직전 정지 — 오너 검수 후 일괄 등록 클릭(비가역 게이트)"}


# ── 릴레이 감지 (단일 진실원천 = market_relay, 두 규약 모두) ─────────────────────
def relay_ready() -> dict:
    """쿠팡 IP 허용 릴레이가 설정됐는가 — market_relay를 단일 진실원천으로 두 규약 모두 감지.

    v88-C 결함: 파일럿 게이트가 구 `MARKET_RELAY_URL`만 봤는데, 오너가 실제 설치한 건 **mkt.php 릴레이**
    (`MARKET_API_RELAY_URL`)라 미감지 → live=false. → 두 경로 모두 인정.
      - mkt.php(현행, 오너 50.6.34.63 설치): `MARKET_API_RELAY_URL`(+`MARKET_API_RELAY_KEY`|`MARKET_RELAY_TOKEN`)
      - 구 /relay: `MARKET_RELAY_URL` + `MARKET_RELAY_TOKEN`
    """
    from src import market_relay as MR
    api = MR.api_relay_enabled()
    legacy = MR.relay_enabled("coupang")
    mode = "mkt.php(MARKET_API_RELAY_URL)" if api else ("relay(MARKET_RELAY_URL+TOKEN)" if legacy else None)
    return {"ready": bool(api or legacy), "mode": mode}


# ── 금지 85 블랙리스트 로드 (오너 자산 — env 우선, 파일 폴백; COPY 지뢰 회피) ──────
def load_blacklist85() -> dict:
    """금지 85 리스트 로드. 소스 우선순위 = env `COUPANG_BLACKLIST85` → 파일 `data/coupang_blacklist85.json`.

    env(권장 — Docker COPY 지뢰 회피, Render에 바로 넣음): JSON 배열 또는 개행/쉼표 구분 문자열.
    파일: JSON 배열 또는 `{"terms":[...]}`. 둘 다 없거나 0건이면 count 0(정직) — 라우트가 표 산출 전 가드.
    반환: {"terms":[...], "source": str, "count": n, "file_present": bool}.
    """
    raw = (os.getenv("COUPANG_BLACKLIST85") or "").strip()
    if raw:
        terms = None
        if raw[:1] in "[{":
            try:
                parsed = json.loads(raw)
                terms = parsed.get("terms") if isinstance(parsed, dict) else parsed
            except (ValueError, TypeError):
                terms = None
        if terms is None:                       # JSON 아니면 개행/쉼표 구분
            terms = [t.strip() for t in raw.replace("\n", ",").split(",")]
        terms = [str(t).strip() for t in (terms or []) if str(t).strip()]
        return {"terms": terms, "source": "env:COUPANG_BLACKLIST85", "count": len(terms),
                "file_present": Path("data/coupang_blacklist85.json").is_file()}
    path = Path(os.getenv("COUPANG_BLACKLIST85_PATH", "") or "data/coupang_blacklist85.json")
    if path.is_file():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            terms = parsed.get("terms") if isinstance(parsed, dict) else parsed
            terms = [str(t).strip() for t in (terms or []) if str(t).strip()]
            return {"terms": terms, "source": f"file:{path}", "count": len(terms), "file_present": True}
        except (ValueError, TypeError, OSError):
            return {"terms": [], "source": f"file:{path}(파싱실패)", "count": 0, "file_present": True}
    return {"terms": [], "source": "none(미설정)", "count": 0, "file_present": False}


# ── 접근성 게이트 (라이브 실행 전 정직 확인) ────────────────────────────────────
def access_status() -> dict:
    """라이브 조인/파일럿에 필요한 자산·자격 존재 여부 — 없으면 가짜 수치 대신 이 보고를 낸다."""
    sm = load_sourcing_map()
    # 무접두 COUPANG_*를 VENDOR_ID로 한 계정에 흡수(이중화 금지). 그 외는 계정 접두 자격.
    base_acct = resolve_base_account()          # "gogane"|"woojoo"|None
    accounts = {}
    for acct, meta in COUPANG_ACCOUNTS.items():
        accounts[meta["label"]] = _prefixed_ready(meta["prefix"]) or (base_acct == acct)
    base_label = COUPANG_ACCOUNTS[base_acct]["label"] if base_acct else None
    base_present = all(os.getenv(f"COUPANG_{k}") for k in ("VENDOR_ID", "ACCESS_KEY", "SECRET_KEY"))
    rr = relay_ready()
    relay = rr["ready"]
    ready = sm["available"] and any(accounts.values())
    return {
        "ready": ready,
        "sourcing_map": {"available": sm["available"], "path": sm.get("path"), "count": sm["count"]},
        "coupang_accounts": accounts,          # 계정별 자격 준비 여부(라벨→bool)
        # 무접두 COUPANG_* 판별 결과(정직): 어느 계정인지 or 미상. base_present이나 base_account None이면
        #   VENDOR_ID가 두 계정과 불일치 → 오너 확인 필요(가짜 귀속 0).
        "base_key": {"present": base_present, "resolved_account": base_label,
                     "note": None if not base_present or base_label
                             else "무접두 COUPANG_VENDOR_ID가 두 계정(A01381223/A01504840)과 불일치 — 오너 확인"},
        "relay": relay,                        # 쿠팡 IP 허용용 릴레이(고정 IP)
        "relay_mode": rr["mode"],              # 감지된 릴레이 규약(mkt.php or 구 /relay or None)
        "missing": [m for m, ok in [
            ("sourcing_map.json", sm["available"]),
            ("coupang 자격(2계정 중 1+)", any(accounts.values())),
            ("릴레이(MARKET_API_RELAY_URL 또는 MARKET_RELAY_URL+TOKEN)", relay),
        ] if not ok],
        "owner_action": "sourcing_map 배치(SOURCING_MAP_PATH) + 계정 접두 COUPANG_GOGANE_*/COUPANG_WOOJOO_*(또는 무접두 COUPANG_* 1계정) + 릴레이 IP 등록 후 라이브 조인 실행",
    }


def run_inventory_join(fetch_items_fn=None, sourcing_map: Optional[dict] = None) -> dict:
    """라이브 조인 진입점 — **접근성 게이트 통과 시에만** 실행. 미충족이면 가짜 수치 대신 access 보고.

    fetch_items_fn(): 쿠팡 판매중 목록을 [{account, seller_product_id, external_vendor_sku, title}]로
      반환하는 함수(주입 — 실제는 계정별 CoupangAdapter.fetch_inventory 래핑, 읽기 전용). 미주입이면
      라이브 어댑터가 필요하나 이 코어는 호출하지 않는다(우회/발명 금지) → not-ready 보고.
    sourcing_map: 미지정이면 load_sourcing_map()으로 로드.
    """
    sm = {"available": True, "map": sourcing_map} if sourcing_map is not None else load_sourcing_map()
    st = access_status()
    if not sm.get("available") or fetch_items_fn is None:
        return {"ok": False, "reason": "라이브 조인 미준비 — 자산/자격 필요(가짜 수치 0)", "access": st}
    items = fetch_items_fn() or []
    rep = join_inventory(items, sm.get("map") or {})
    return {"ok": True, "report": rep.as_table(), "rows": rep.rows, "access": st}


# ── 파일럿 인입 오케스트레이션 (작업 2+3 배선 — 등록 직전 정지) ──────────────────
IMAGE_CAP = 2                          # 오너: 이미지 상품당 2장(Bluehost 디스크 4중 재발방지).


def _cost_krw_of(draft: dict):
    """수집 draft에서 원가(KRW) 추출. KRW면 그 값, 외화면 None(정직 — fx 미상, 가짜 환산 0)."""
    price = draft.get("price")
    cur = (draft.get("currency") or "").upper()
    try:
        val = float(str(price).replace(",", "")) if price not in (None, "") else None
    except (TypeError, ValueError):
        val = None
    if val is None or val <= 0:
        return None
    return val if cur in ("KRW", "") else None


def run_pilot_ingest(pilot_rows, *, channel, collect_fn, prevalidate_fn=None,
                     existing_source_keys=None, blacklist=None,
                     margin_rate: float = DEFAULT_MARGIN_RATE, image_cap: int = IMAGE_CAP) -> dict:
    """파일럿 행을 **기존 수집 경로로 인입 → 가격 → 사전검증**까지, **등록은 하지 않는다**(비가역 게이트).

    의존성 주입(테스트/발명 금지): collect_fn(url)→draft(기존 `_collect_real_draft`), prevalidate_fn(draft)→result.
    각 행: 취급금지 스킵 → 기존 채널 중복 스킵 → collect → 이미지 2장 캡 → 원가기준 가격 → 사전검증. registered=False 불변.
    """
    existing = set(existing_source_keys or [])
    rows_out, summ = [], {"ingested": 0, "skipped_forbidden": 0, "skipped_duplicate": 0,
                          "failed_collect": 0, "prevalidate_ok": 0, "prevalidate_fail": 0}
    for r in (pilot_rows or []):
        url = getattr(r, "sourcing_url", None) or (r.get("sourcing_url") if isinstance(r, dict) else "")
        title = getattr(r, "title", None) or (r.get("title") if isinstance(r, dict) else "")
        fb = is_forbidden(title, blacklist=blacklist)
        if fb:
            summ["skipped_forbidden"] += 1
            rows_out.append({"url": url, "action": "skipped-forbidden", "reason": fb, "registered": False})
            continue
        if dedup_decision(url, existing) == "update":      # 이미 채널에 있음(SUPERONE 등) → 스킵
            summ["skipped_duplicate"] += 1
            rows_out.append({"url": url, "action": "skipped-duplicate", "registered": False})
            continue
        draft = None
        try:
            draft = collect_fn(url)
        except Exception as exc:                           # 수집 실패는 정직 실패(가짜 성공 0)
            draft = None
        if not draft:
            summ["failed_collect"] += 1
            rows_out.append({"url": url, "action": "failed-collect", "registered": False})
            continue
        imgs = list(draft.get("images") or [])[:max(0, int(image_cap))]   # 이미지 2장 캡
        draft["images"] = imgs
        cost = _cost_krw_of(draft)
        price = recalc_channel_price(cost, channel, margin_rate=margin_rate) if cost is not None else \
            {"ok": False, "reason": "원가 미상(외화/빈값) — fx 확인 필요"}
        pv = prevalidate_fn(draft) if prevalidate_fn else {"ok": None, "reason": "prevalidate 미주입"}
        pv_ok = bool(getattr(pv, "ok", None) if not isinstance(pv, dict) else pv.get("ok"))
        summ["prevalidate_ok" if pv_ok else "prevalidate_fail"] += 1
        summ["ingested"] += 1
        rows_out.append({"url": url, "action": "ingested-prevalidated", "images": len(imgs),
                         "price": price, "prevalidate_ok": pv_ok, "registered": False})
    return {"registered": False,                            # ★ 등록 안 함(오너 클릭 게이트)
            "summary": summ, "rows": rows_out,
            "note": "마켓 등록 직전 정지 — 오너 검수 후 일괄 등록 클릭(비가역 게이트)"}


# ── v88-C 파일럿: 모집단(dedupe) · 선정 · 하드 정지 게이트 ────────────────────────
# 오너 승인 모집단: coupang_sid truthy → sid 그룹핑 → sid당 대표 1건 = distinct 396.
# 대표 선정은 **결정적**(난수 금지): ① krw+usd 모두 보유 ② sources[] ship_usd 보유 ③ ASIN 사전순.

# ★ 하드 정지 게이트 — 코드 레벨. env로 못 뚫는다.
#   오너 최종 승인("전부가라", 2026-08-20) → **해제**. 안전은 카나리 게이트(register_pilot_rows batch_ok)로 이관:
#   승인돼도 batch_ok 없으면 1건(카나리)만 등록. 47 전량은 오너 육안 확인 후 batch_ok=True로만. draft 등록.
PILOT_REGISTER_APPROVED = True


def pilot_register_guard() -> None:
    """파일럿 등록 직전 강제 게이트. 승인 안 됐으면 차단(env 오버라이드 불가)."""
    if PILOT_REGISTER_APPROVED is not True:
        raise RuntimeError("PILOT_REGISTER_APPROVED=False — 파일럿 자동 등록 하드 정지(오너 검수 후 별도 커밋으로만 해제)")


def _rep_sort_key(asin: str, entry: dict):
    """대표 선정 정렬 키(결정적). 오름차순 min이 대표 — 우선순위 높을수록 작은 키."""
    has_both = 0 if (entry.get("krw") and entry.get("usd")) else 1        # 0 우선
    has_ship = 0 if any((s or {}).get("ship_usd") is not None
                        for s in (entry.get("sources") or [])) else 1     # 0 우선
    return (has_both, has_ship, str(asin))                                # ASIN 사전순 타이브레이커


def build_pilot_population(sourcing_map: dict) -> dict:
    """모집단 산출 — coupang_sid truthy 그룹핑 → sid당 대표 1. 원본 불변(읽기전용).

    반환: {population:[{sid, asin, krw, usd, name_ko, primary_url, source, reason}], count,
           reduction:{truthy, distinct_sid, dropped_dup}}.
    """
    groups = {}
    truthy = 0
    for asin, e in (sourcing_map or {}).items():
        sid = e.get("coupang_sid")
        if not sid:
            continue
        truthy += 1
        groups.setdefault(sid, []).append(asin)
    pop = []
    for sid, asins in groups.items():
        # 결정적 대표: 정렬 키 min.
        rep_asin = min(asins, key=lambda a: _rep_sort_key(a, sourcing_map[a]))
        e = sourcing_map[rep_asin]
        srcs = sorted(e.get("sources") or [], key=lambda s: s.get("priority", 99))
        prim = srcs[0] if srcs else {}
        e_has_both = bool(e.get("krw") and e.get("usd"))
        e_has_ship = any((s or {}).get("ship_usd") is not None for s in (e.get("sources") or []))
        reason = ("krw+usd" if e_has_both else "") + ("|ship_usd" if e_has_ship else "") + \
                 (f"|asin사전순(그룹 {len(asins)})" if len(asins) > 1 else "|단일")
        pop.append({"sid": sid, "asin": rep_asin, "krw": e.get("krw"), "usd": e.get("usd"),
                    "name_ko": e.get("name_ko"), "primary_url": prim.get("url"),
                    "source": classify_source(prim.get("url"), ),
                    "group_size": len(asins), "reason": reason.lstrip("|")})
    # 결정적 정렬(sid 오름차순) — 재현 가능.
    pop.sort(key=lambda r: r["sid"])
    return {"population": pop, "count": len(pop),
            "reduction": {"truthy": truthy, "distinct_sid": len(groups),
                          "dropped_dup": truthy - len(groups)}}


def select_pilot(population: list, n: int = 50) -> list:
    """396 → n건 **결정적** 샘플(sid 오름차순 stride). 난수 금지 — 같은 입력이면 같은 n건."""
    pop = sorted(population or [], key=lambda r: r["sid"])
    L = len(pop)
    if L <= n:
        return list(pop)
    stride = L / float(n)
    return [pop[int(i * stride)] for i in range(n)]


def build_review_row(entry: dict, *, channel: str = "woocommerce_multishop",
                     blacklist=None, translate_fn=None, price_override=None,
                     margin_rate: float = DEFAULT_MARGIN_RATE) -> dict:
    """검수표 1행. 번역=원본에서 재처리(표시본 재처리 금지). 가격=현행가 주입(없으면 sourcing krw 기준).

    금지 85 필터 **강제 통과** — 미통과는 excluded=True + reason(조용한 탈락 금지). 등록은 하지 않는다.
    """
    title_src = entry.get("name_ko") or ""
    fb = is_forbidden(title_src, blacklist=blacklist)
    # 가격: 현행가(price_override, 라이브 조인 시 재조회) 우선, 없으면 sourcing krw(원가).
    cost = price_override if price_override is not None else entry.get("krw")
    price = recalc_channel_price(cost, channel, margin_rate=margin_rate) if cost else \
        {"ok": False, "reason": "원가 미상"}
    # 번역: 원본에서(주입 translate_fn — 라이브 시 체인, 오프라인 미주입이면 원문 유지).
    title_ko = title_src
    if translate_fn:
        try:
            out = translate_fn({"title": title_src, "description": ""})
            title_ko = (out.get("title_ko") or "").strip() or title_src
        except Exception:
            title_ko = title_src
    # 제목 정제(별점·프로모괄호·일문·중복어 제거) + 절단 플래그(조용히 자르지 않음).
    ct = clean_title_ko(title_ko, url=entry.get("url", "") or "")
    return {
        "sid": entry.get("sid"), "asin": entry.get("asin"),
        "title_ko": ct["title"], "title_truncated": ct["truncated"],
        "title_truncated_suspect": ct["truncated_suspect"], "title_cjk_residual": ct["cjk_residual"],
        "title_cleaned": ct["changed"], "cost_krw": cost,
        "sale_krw": price.get("sale_price_krw") if price.get("ok") else None,
        "margin_pct": price.get("margin_rate") if price.get("ok") else None,
        "target_channel": channel, "source": entry.get("source"),
        "forbidden": fb, "excluded": bool(fb),
        "dedup_reason": entry.get("reason"), "registered": False,
    }


# ── 파일럿 등록 실행 (카나리 게이트 · draft · 롤백 금지 · 행별 정직 결과) ──────────
def register_pilot_rows(rows, *, dispatch_fn, n: int = 1, batch_ok: bool = False,
                        status: str = "draft", enrich_fn=None, sleep_fn=None,
                        sleep_sec: float = 0.6, markets=("woocommerce",)) -> dict:
    """검수 통과 행을 마켓에 **실등록**. 오너 승인(PILOT_REGISTER_APPROVED) 필수.

    **카나리 게이트:** `batch_ok=False`면 첫 1행(review_table[0] = Ystudio)만 등록. 47 전량은 오너 육안
    확인 후 `batch_ok=True`(+n)로만. **롤백 금지**(부분 실패 시 성공분 유지) · **조용한 실패 금지**(행별
    registered+사유) · draft 등록(되돌림성). suspect/cjk 플래그 행도 등록하되 상품 비노출 메타(`_kgp_*`)에
    남겨 후속 제목 보정 배치 대상으로. dispatch_fn/enrich_fn 주입(발명 0·오프라인 테스트).
    """
    pilot_register_guard()                                   # 승인 안 됐으면 raise
    import time as _t
    sleep_fn = sleep_fn or _t.sleep
    passable = [r for r in (rows or []) if not r.get("excluded")]
    passable = passable[:1] if not batch_ok else passable[:max(0, int(n))]
    results = []
    for i, r in enumerate(passable):
        if i and sleep_sec:
            sleep_fn(sleep_sec)                              # 레이트리밋 예의(호출 간격)
        images, desc, src_url = [], "", r.get("url", "") or ""
        if enrich_fn:
            try:
                e = enrich_fn(r) or {}
                images = list(e.get("images") or [])
                desc = e.get("description_html") or ""
                src_url = e.get("sourcing_url") or src_url
            except Exception as exc:                          # 수집 실패는 정직 실패(등록 안 함), 다음 행 계속
                results.append({"sid": r.get("sid"), "asin": r.get("asin"), "title": r.get("title_ko"),
                                "registered": False, "reason": f"collect 실패: {exc}", "image_count": 0,
                                "url": None, "status": status})
                continue
        meta = [{"key": "_kgp_pilot_sid", "value": str(r.get("sid"))}]
        if r.get("title_truncated") or r.get("title_truncated_suspect"):
            meta.append({"key": "_kgp_title_suspect", "value": "1"})
        if r.get("title_cjk_residual"):
            meta.append({"key": "_kgp_cjk_residual", "value": "1"})
        product_data = {
            "title_ko": r.get("title_ko"), "sell_price_krw": r.get("sale_krw"),
            "images": images, "description_html": desc, "url": src_url,
            "status": status, "pilot_meta": meta, "source": r.get("source"),
            # 재고: 무재고 구매대행 모델 — 재고관리 off + 항상 구매가능(instock).
            "manage_stock": False, "stock_status": "instock",
            # 상품 타입: 자사 결제형(simple) — external(외부 링크형) 아님.
            "product_type": "simple",
        }
        try:
            dr = dispatch_fn(product_data, list(markets))
        except Exception as exc:                              # 롤백 금지 — 실패분만 기록하고 계속
            results.append({"sid": r.get("sid"), "asin": r.get("asin"), "title": r.get("title_ko"),
                            "registered": False, "reason": f"dispatch 예외: {exc}", "image_count": len(images),
                            "url": None, "status": status})
            continue
        wr = next((rr for rr in (getattr(dr, "results", None) or []) if getattr(rr, "market", "") == "woocommerce"), None)
        ok = bool(wr and getattr(wr, "success", False))
        # 조용한 실패 가드: 등록 성공인데 이미지 0장이면 warning으로 표기(백필 대상) — reason:null 성공으로 묻지 않음.
        img_warn = "이미지 0장 — 백필 필요" if (ok and len(images) == 0) else None
        results.append({
            "sid": r.get("sid"), "asin": r.get("asin"), "title": r.get("title_ko"),
            "registered": ok, "status": status, "image_count": len(images), "sale_krw": r.get("sale_krw"),
            "url": (getattr(wr, "external_url", None) if wr else None),
            "reason": None if ok else (getattr(wr, "message", None) if wr else "woo 결과 없음"),
            "warning": img_warn,
            "title_suspect": bool(r.get("title_truncated") or r.get("title_truncated_suspect")),
            "cjk_residual": bool(r.get("title_cjk_residual")),
        })
    return {
        "mode": "canary" if not batch_ok else "batch",
        "target": len(passable), "batch_ok": bool(batch_ok), "status": status,
        "registered": sum(1 for x in results if x["registered"]),
        "failed": sum(1 for x in results if not x["registered"]),
        "no_image": sum(1 for x in results if x.get("registered") and x.get("image_count") == 0),
        "results": results,
        "note": ("카나리(1건 · Ystudio) — 육안 확인 후 batch_ok=1로 46건 속행"
                 if not batch_ok else f"배치({len(passable)}건, draft)"),
    }


# ── 이미지 백필 (기존 draft 상품 UPDATE — 재등록 아님, _kgp_pilot_sid 매칭, 멱등) ──
def backfill_images(rows, *, enrich_fn, list_products_fn, update_fn,
                    image_cap: int = IMAGE_CAP, stock_patch=None, sleep_fn=None, sleep_sec: float = 0.5) -> dict:
    """기존 draft 상품에 이미지(+재고) 백필. **재등록 아님 — WC UPDATE.** `_kgp_pilot_sid` 메타로 상품 매칭.

    list_products_fn() → draft 상품 목록([{id, meta_data:[{key,value}]}]). update_fn(pid, patch)→ok.
    이미 이미지 있는 상품은 스킵(멱등). 매칭 실패·수집 0장은 정직 표기(조용한 성공 금지). 상품당 image_cap(2)장.
    """
    import time as _t
    sleep_fn = sleep_fn or _t.sleep
    by_sid = {}
    for p in (list_products_fn() or []):
        for m in (p.get("meta_data") or p.get("meta") or []):
            if (m or {}).get("key") == "_kgp_pilot_sid":
                by_sid[str(m.get("value"))] = p
                break
    results, passable = [], [r for r in (rows or []) if not r.get("excluded")]
    for i, r in enumerate(passable):
        p = by_sid.get(str(r.get("sid")))
        if not p:
            results.append({"sid": r.get("sid"), "matched": False, "updated": False,
                            "reason": "WC draft 매칭 실패(_kgp_pilot_sid)"})
            continue
        if int(p.get("images_count") or len(p.get("images") or [])) > 0:
            results.append({"sid": r.get("sid"), "product_id": p.get("id"), "matched": True,
                            "updated": False, "skipped": True, "reason": "이미 이미지 있음(멱등 스킵)"})
            continue
        try:
            e = enrich_fn(r) or {}
        except Exception as exc:
            results.append({"sid": r.get("sid"), "product_id": p.get("id"), "matched": True,
                            "updated": False, "reason": f"collect 실패: {exc}"})
            continue
        imgs = list(e.get("images") or [])[:image_cap]
        patch = {}
        if imgs:
            patch["images"] = [{"src": u, "position": j} for j, u in enumerate(imgs)]
        if stock_patch:
            patch.update(stock_patch)
        if not patch:
            results.append({"sid": r.get("sid"), "product_id": p.get("id"), "matched": True,
                            "updated": False, "image_count": 0, "reason": "수집 이미지 0장(소스 확인 필요)"})
            continue
        if i and sleep_sec:
            sleep_fn(sleep_sec)
        try:
            ok = bool(update_fn(p.get("id"), patch))
        except Exception as exc:
            results.append({"sid": r.get("sid"), "product_id": p.get("id"), "matched": True,
                            "updated": False, "image_count": len(imgs), "reason": f"WC update 예외: {exc}"})
            continue
        results.append({"sid": r.get("sid"), "product_id": p.get("id"), "matched": True,
                        "updated": ok, "image_count": len(imgs),
                        "reason": None if ok else "WC update 실패"})
    return {
        "target": len(passable),
        "updated": sum(1 for x in results if x.get("updated")),
        "skipped": sum(1 for x in results if x.get("skipped")),
        "failed": sum(1 for x in results if not x.get("updated") and not x.get("skipped")),
        "unmatched": sum(1 for x in results if not x.get("matched")),
        "results": results,
    }


# ── 쿠팡 원본 이미지 소스 (봇차단 회피 · "쿠팡→멀티채널 복제" 정합) ─────────────────
#   sid별 소속 계정 판별 → 맞는 키로 GET seller-products/{sid}(릴레이 경유·페이싱) → images[].
_COUPANG_API_BASE = "https://api-gateway.coupang.com"
_COUPANG_SP_PATH = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{sid}"
_COUPANG_ACCOUNT_META = "_kgp_pilot_account"   # 판별된 소속 계정 캐시(재틱 재판별 방지)


def _account_creds(account: str):
    """계정(gogane/woojoo) → (access, secret, vendor_id). 접두(표준/축약 접미) 우선 + 무접두 base 폴백."""
    meta = COUPANG_ACCOUNTS.get(account) or {}
    pfx = meta.get("prefix", "")

    def pick(*names):
        for n in names:
            v = os.getenv(f"{pfx}_{n}", "").strip()
            if v:
                return v
        return ""
    access = pick("ACCESS_KEY", "ACCESS")
    secret = pick("SECRET_KEY", "SECRET")
    vendor = pick("VENDOR_ID", "VENDOR") or meta.get("vendor_id", "")
    if (not access or not secret) and resolve_base_account() == account:  # 무접두 COUPANG_* 흡수 계정
        access = access or os.getenv("COUPANG_ACCESS_KEY", "").strip()
        secret = secret or os.getenv("COUPANG_SECRET_KEY", "").strip()
        vendor = vendor or os.getenv("COUPANG_VENDOR_ID", "").strip()
    return access, secret, vendor


def ready_accounts() -> list:
    """자격(access+secret) 준비된 계정 목록(고가네 우선). 판별 시도 순서."""
    return [a for a in ("gogane", "woojoo") if all(_account_creds(a)[:2])]


def _coupang_sign(secret: str, method: str, path: str, date: str) -> str:
    import hashlib
    import hmac
    msg = date + method + path
    return hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _coupang_image_urls(data) -> list:
    """seller-products GET 응답에서 이미지 URL 수집. 절대 http(s) 우선, cdnPath는 env base로 절대화.

    쿠팡 응답 스키마 변형 대비 재귀 수집(images[].{vendorPath,cdnPath} 등). 정직: 못 만들면 버림.
    """
    base = os.getenv("COUPANG_IMAGE_CDN_BASE", "https://image.coupangcdn.com").rstrip("/")
    out, seen = [], set()

    def _abs(v: str):
        v = str(v or "").strip()
        if not v:
            return None
        if v.startswith("http://") or v.startswith("https://"):
            return v
        return base + ("" if v.startswith("/") else "/") + v

    def _walk(node):
        if isinstance(node, dict):
            for k, val in node.items():
                if isinstance(val, str) and ("path" in k.lower() or "image" in k.lower() or "url" in k.lower()):
                    u = _abs(val)
                    if u and u not in seen and any(u.lower().endswith(e) for e in
                                                   (".jpg", ".jpeg", ".png", ".webp", ".gif")):
                        seen.add(u)
                        out.append(u)
                else:
                    _walk(val)
        elif isinstance(node, list):
            for it in node:
                _walk(it)

    _walk(data)
    return out


def fetch_coupang_images(sid, *, accounts=None, account_hint=None, request_fn=None, now_fn=None) -> dict:
    """쿠팡 GET seller-products/{sid} → 원본 이미지 URL. 계정 라우팅(힌트 우선, 없으면 준비된 계정 순차).

    - 계정 혼동 금지: hint 있으면 그 계정만, 없으면 ready_accounts() 순차 시도(200+이미지면 확정·캐시).
    - 호출 예의: request_fn=relay_request(페이싱·429 백오프 내장) 기본. now_fn 주입(테스트 결정성).
    - 정직: 자격/이미지 없으면 images=[] + 사유. 조용한 실패 금지(status·account·reason 반환).
    """
    from datetime import datetime, timezone
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    if request_fn is None:
        from src.market_relay import relay_request as request_fn  # 페이싱·릴레이·백오프 관문
    try_accts = [account_hint] if account_hint else (accounts if accounts is not None else ready_accounts())
    try_accts = [a for a in try_accts if a]
    if not try_accts:
        return {"ok": False, "images": [], "account": None, "reason": "쿠팡 자격 없음(계정 미준비)"}
    path = _COUPANG_SP_PATH.format(sid=sid)
    last = "미상"
    for acct in try_accts:
        access, secret, vendor = _account_creds(acct)
        if not (access and secret):
            last = f"{acct} 자격 미비"
            continue
        date = now_fn().strftime("%y%m%dT%H%M%SZ")
        sig = _coupang_sign(secret, "GET", path, date)
        headers = {"Authorization": f"CEA algorithm=HmacSHA256, access-key={access}, "
                                    f"signed-date={date}, signature={sig}",
                   "Content-Type": "application/json;charset=UTF-8"}
        try:
            resp = request_fn("GET", _COUPANG_API_BASE + path, headers=headers,
                              market="coupang", key=str(vendor or ""))
        except Exception as exc:                       # 릴레이/네트워크 실패 — 다음 계정/정직 반환
            last = f"{acct} 호출 실패: {exc}"
            continue
        status = getattr(resp, "status_code", 0)
        if status == 404 or status == 403:             # 이 계정 소유 아님 → 다음 계정
            last = f"{acct} {status}(미소유)"
            continue
        if status != 200:
            last = f"{acct} HTTP {status}"
            continue
        try:
            body = resp.json()
        except Exception as exc:
            last = f"{acct} 응답 파싱 실패: {exc}"
            continue
        imgs = _coupang_image_urls(body.get("data") if isinstance(body, dict) else body)
        if imgs:
            return {"ok": True, "images": imgs, "account": acct, "reason": None}
        last = f"{acct} 200·이미지 0"
    return {"ok": False, "images": [], "account": None, "reason": last}


# ── 자동 마감 (크론 피기백 · 청크 · 멱등 · WC 상태=진행상태 · 오너 개입 0) ──────────
_NO_IMAGE_META = "_kgp_no_image"          # 이미지 0장 → 재시도 방지 플래그(draft 잔류)
_NO_IMAGE_GEN = "coupang"                 # 현 세대 플래그값 — 쿠팡 소스까지 시도한 종결 표식.
#   구세대 플래그(value="1", 아마존 재수집만 시도)는 재시도 대상(쿠팡 소스 신규 → 멱등 재개).


def _pilot_sid_of(product) -> Optional[str]:
    for m in (product.get("meta_data") or []):
        if (m or {}).get("key") == "_kgp_pilot_sid":
            return str(m.get("value"))
    return None


def _pilot_flag_value(product, key) -> Optional[str]:
    for m in (product.get("meta_data") or []):
        if (m or {}).get("key") == key:
            return str(m.get("value"))
    return None


def _pilot_has_flag(product, key) -> bool:
    return any((m or {}).get("key") == key and str(m.get("value")) in ("1", "true", _NO_IMAGE_GEN)
               for m in (product.get("meta_data") or []))


def _pilot_account_hint(product) -> Optional[str]:
    v = _pilot_flag_value(product, _COUPANG_ACCOUNT_META)
    return v if v in ("gogane", "woojoo") else None


def _pilot_img_count(p) -> int:
    try:
        return int(p.get("images_count") if p.get("images_count") is not None else len(p.get("images") or []))
    except (TypeError, ValueError):
        return len(p.get("images") or [])


def pilot_finish_tick(rows, *, list_products_fn, update_fn, enrich_fn, chunk: int = 5,
                      image_cap: int = IMAGE_CAP, stock_patch=None, sleep_fn=None, sleep_sec: float = 0.5) -> dict:
    """자동 마감 1틱(크론). **draft 이미지 백필(2장캡) → 실패 사유 기록 후 스킵 → 전행 처리 완료 시 자동 publish.**

    - 진행상태 = WC 자신(멱등·재개). `_kgp_pilot_sid` 매칭, 이미지 0장 draft는 no_image 플래그+**draft 잔류**(안 팔릴 상품 공개 방지).
    - 등록분 `type=simple` 강제(자사 결제형 — external 아님). **조용한 실패 금지**(행별 action+사유: collect_fail/sideload_fail/no_image).
    - list_products_fn(status)/update_fn(pid,patch)/enrich_fn(row) 주입(발명 0·오프라인 테스트). publish는 전행 처리 완료 시만.
    """
    import time as _t
    sleep_fn = sleep_fn or _t.sleep
    by_sid = {}
    for p in (list_products_fn("draft") or []):
        sid = _pilot_sid_of(p)
        if sid:
            by_sid[sid] = p
    passable = [r for r in (rows or []) if not r.get("excluded")]
    # pending: 이미지 0장 draft 중 **현 세대(_NO_IMAGE_GEN)로 종결 안 된** 것.
    #   구세대 플래그("1" — 아마존만 시도)·미플래그는 쿠팡 소스로 재시도(멱등 재개, 오너 지시 3).
    pending = [r for r in passable
               if str(r.get("sid")) in by_sid
               and _pilot_img_count(by_sid[str(r.get("sid"))]) == 0
               and _pilot_flag_value(by_sid[str(r.get("sid"))], _NO_IMAGE_META) != _NO_IMAGE_GEN]
    processed = []
    for i, r in enumerate(pending[:chunk]):
        p = by_sid[str(r.get("sid"))]
        if i and sleep_sec:
            sleep_fn(sleep_sec)
        # 소속 계정 힌트(캐시)를 enrich에 전달 — 계정 혼동·재판별 방지(오너 지시 2).
        r_aug = dict(r)
        hint = _pilot_account_hint(p)
        if hint:
            r_aug["coupang_account"] = hint
        try:
            e = enrich_fn(r_aug) or {}
        except Exception as exc:
            processed.append({"sid": r.get("sid"), "action": "collect_fail", "reason": f"수집 실패: {exc}"})
            continue
        imgs = list(e.get("images") or [])[:image_cap]
        acct = e.get("account") or hint          # enrich가 판별한 소속 계정
        acct_meta = ([{"key": _COUPANG_ACCOUNT_META, "value": acct}]
                     if acct in ("gogane", "woojoo") and acct != hint else [])
        if imgs:
            patch = {"images": [{"src": u, "position": j} for j, u in enumerate(imgs)], "type": "simple"}
            if acct_meta:
                patch["meta_data"] = list(acct_meta)   # 판별 계정 캐시(다음 틱 재판별 0)
            if stock_patch:
                patch.update({k: v for k, v in stock_patch.items() if k != "meta_data"})
            try:
                ok = bool(update_fn(p.get("id"), patch))
            except Exception as exc:
                processed.append({"sid": r.get("sid"), "product_id": p.get("id"),
                                  "action": "sideload_fail", "reason": f"WC 사이드로드 실패: {exc}"})
                continue
            processed.append({"sid": r.get("sid"), "product_id": p.get("id"),
                              "action": "backfilled" if ok else "sideload_fail",
                              "image_count": len(imgs), "source": e.get("source"), "account": acct,
                              "reason": None if ok else "WC update 실패"})
        else:
            # 쿠팡·소싱 둘 다 0 → 현 세대로 종결 플래그(다음 틱 재시도 제외, 재개 멱등).
            try:
                update_fn(p.get("id"), {"meta_data": [{"key": _NO_IMAGE_META, "value": _NO_IMAGE_GEN}] + acct_meta,
                                        "type": "simple"})
            except Exception:
                pass
            processed.append({"sid": r.get("sid"), "product_id": p.get("id"), "action": "no_image",
                              "image_count": 0, "reason": (e.get("reason") or "쿠팡·소싱 이미지 0장 — draft 잔류(공개 안 함)")})
    remaining = max(0, len(pending) - chunk)
    published = []
    if remaining == 0:                        # 전행 처리 완료 → 이미지 있는 draft만 자동 publish(오너 사전 승인)
        for p in (list_products_fn("draft") or []):
            if _pilot_sid_of(p) is None or _pilot_img_count(p) == 0:
                continue                       # 이미지 0 draft는 publish 안 함(안 팔릴 상품 공개 방지)
            try:
                if update_fn(p.get("id"), {"status": "publish"}):
                    published.append({"sid": _pilot_sid_of(p), "product_id": p.get("id")})
            except Exception:
                pass
    return {
        "pending_before": len(pending), "processed": len(processed),
        "backfilled": sum(1 for x in processed if x["action"] == "backfilled"),
        "no_image": sum(1 for x in processed if x["action"] == "no_image"),
        "failed": sum(1 for x in processed if x["action"] in ("collect_fail", "sideload_fail")),
        "remaining_pending": remaining, "published_this_tick": len(published),
        "done": remaining == 0, "results": processed, "published": published,
    }


def _pilot_product_url(p) -> str:
    """WC 상품 공개 URL(permalink) — 없으면 link/guid 폴백, 그것도 없으면 빈 문자열."""
    for k in ("permalink", "link"):
        v = p.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    g = p.get("guid")
    if isinstance(g, dict) and str(g.get("rendered", "")).startswith("http"):
        return g["rendered"]
    return ""


def pilot_status(rows, *, list_products_fn) -> dict:
    """조회 전용 진행 상태 — 대기/이미지있음 draft/no_image draft/publish/미매칭(WC 실측).

    unmatched_rows(sid·asin·이름)로 미매칭 행을 **식별**하고(추정 금지), published_samples(sid·url) 3개로
    실 게시물 URL을 함께 반환한다 — 오너가 status 1회 호출로 완료 수치+미매칭 정체+URL 샘플을 다 확인.
    """
    passable = [r for r in (rows or []) if not r.get("excluded")]
    drafts = {}
    for p in (list_products_fn("draft") or []):
        s = _pilot_sid_of(p)
        if s:
            drafts[s] = p
    pubs = {}
    for p in (list_products_fn("publish") or []):
        s = _pilot_sid_of(p)
        if s:
            pubs[s] = p
    published = with_images = no_image = pending = unmatched = 0
    unmatched_rows, published_samples = [], []
    for r in passable:
        sid = str(r.get("sid"))
        if sid in pubs:
            published += 1
            if len(published_samples) < 3:
                url = _pilot_product_url(pubs[sid])
                if url:
                    published_samples.append({"sid": sid, "url": url})
        elif sid in drafts:
            p = drafts[sid]
            if _pilot_img_count(p) > 0:
                with_images += 1              # 이미지 있음(다음 완료 틱에 publish)
            elif _pilot_flag_value(p, _NO_IMAGE_META) == _NO_IMAGE_GEN:
                no_image += 1                 # 현 세대(쿠팡까지 시도) 종결 · draft 잔류
            else:
                pending += 1                  # 미처리/구세대 플래그 — 쿠팡 소스로 재시도 대상
        else:
            unmatched += 1
            unmatched_rows.append({"sid": sid, "asin": r.get("asin"),
                                   "name": r.get("title_ko") or r.get("name_ko")})
    return {"target": len(passable), "published": published, "with_images_draft": with_images,
            "no_image_draft": no_image, "pending": pending, "unmatched": unmatched,
            "unmatched_rows": unmatched_rows, "published_samples": published_samples,
            "done": pending == 0}


def default_pilot_rows(select_n: int = 50) -> list:
    """모집단→검수표 review_pass 행(라우트 공용, Flask-free). 블랙리스트 0건이면 [](빈 필터 처리 금지 — 등록 세트 유지)."""
    pf = Path("data/pilot_population.json")
    if pf.is_file():
        try:
            pop = json.loads(pf.read_text(encoding="utf-8")).get("population", [])
        except (ValueError, OSError):
            pop = []
    else:
        try:
            sm = json.loads(Path("data/sourcing_map.json").read_text(encoding="utf-8"))
        except (ValueError, OSError):
            sm = {}
        pop = build_pilot_population(sm)["population"] if sm else []
    if not pop:
        return []
    bl = load_blacklist85()
    if bl["count"] == 0:
        return []
    report = build_pilot_report(pop, n=select_n, channel="woocommerce_multishop",
                                blacklist=bl["terms"], access=access_status(), relay=relay_ready())
    return report.get("review_table") or []


def make_enrich_fn(collect_fn, image_cap: int = IMAGE_CAP):
    """소싱맵 URL 해석 → collect_fn(url) → {images(캡), description_html, sourcing_url}. collect_fn 주입(발명 0)."""
    smap = load_sourcing_map().get("map") or {}

    def _enrich(row):
        asin = str(row.get("asin") or "").upper()
        url = smap.get(asin) if isinstance(smap.get(asin), str) else ""
        if not url:
            return {"images": [], "sourcing_url": "", "source": "sourcing"}
        try:
            draft = collect_fn(url) or {}
        except Exception:
            return {"images": [], "sourcing_url": url, "source": "sourcing"}
        return {"images": (draft.get("images") or [])[:image_cap],
                "description_html": draft.get("description_html") or draft.get("description") or "",
                "sourcing_url": url, "source": "sourcing"}
    return _enrich


def make_coupang_first_enrich_fn(collect_fn, *, image_cap: int = IMAGE_CAP,
                                 fetch_images_fn=None, request_fn=None):
    """이미지 소스 **①쿠팡 sid 원본(봇차단 회피) → ②소싱처 수집(폴백)**. (오너 지시 1·v88-C 피벗)

    - 쿠팡 GET seller-products/{sid} 이미지 우선. 계정 힌트(row['coupang_account']) 있으면 그 계정만.
    - 쿠팡 0장/실패 시 기존 소싱맵 수집으로 폴백. 반환 account/source로 pilot_finish_tick가 캐시·계측.
    - fetch_images_fn 주입(오프라인 테스트). 기본=fetch_coupang_images(릴레이·페이싱·계정라우팅).
    """
    fetch_images_fn = fetch_images_fn or fetch_coupang_images
    sourcing = make_enrich_fn(collect_fn, image_cap=image_cap)

    def _enrich(row):
        sid = row.get("sid")
        hint = row.get("coupang_account")
        cp = {}
        if sid is not None:
            try:
                cp = fetch_images_fn(sid, account_hint=hint, request_fn=request_fn) or {}
            except Exception as exc:
                cp = {"ok": False, "images": [], "account": None, "reason": f"쿠팡 조회 예외: {exc}"}
        imgs = list(cp.get("images") or [])[:image_cap]
        if imgs:
            return {"images": imgs, "account": cp.get("account") or hint,
                    "source": "coupang", "reason": None}
        fb = sourcing(row) or {}                      # 폴백: 기존 소싱처 수집
        fb_imgs = list(fb.get("images") or [])[:image_cap]
        return {"images": fb_imgs, "account": cp.get("account") or hint,
                "description_html": fb.get("description_html") or "",
                "sourcing_url": fb.get("sourcing_url") or "",
                "source": "sourcing" if fb_imgs else "none",
                "reason": None if fb_imgs else (f"쿠팡 {cp.get('reason') or '이미지 0'} · 소싱 폴백도 0")}
    return _enrich


# ── 파일럿 검수표 산출 (라우트/테스트 공용 — price_fn 주입으로 라이브 경로 계약 검증) ──
def build_pilot_report(population, *, n: int = 50, channel: str = "woocommerce_multishop",
                       blacklist=None, access: Optional[dict] = None, relay: Optional[dict] = None,
                       price_fn=None, translate_fn=None,
                       margin_rate: float = DEFAULT_MARGIN_RATE) -> dict:
    """파일럿 검수표(등록 없음). `live = access.ready and relay.ready`.

    live + price_fn이면 각 행 **현행가 재조회**(price_fn(sid)) → 마진 재계산 → price_basis="coupang live".
    아니면 sourcing krw(원가). registered=False 불변. price_fn/translate_fn/access/relay는 주입(테스트·라우트 공용).
    """
    access = access if access is not None else access_status()
    relay = relay if relay is not None else relay_ready()
    selected = select_pilot(population, n=n)
    live = bool(access.get("ready")) and bool(relay.get("ready"))
    use_live_price = bool(live and price_fn)
    price_basis = "coupang live(현행가 재조회)" if use_live_price else "sourcing krw(원가 — 현행가 아님)"
    review, excluded = [], []
    for e in selected:
        override = None
        if use_live_price:
            try:
                override = price_fn(e.get("sid"))
            except Exception:
                override = None
        row = build_review_row(e, channel=channel, blacklist=blacklist,
                               translate_fn=translate_fn, price_override=override,
                               margin_rate=margin_rate)
        (excluded if row["excluded"] else review).append(row)
    return {
        "population_count": len(population), "selected": len(selected),
        "review_pass": len(review), "excluded_forbidden": len(excluded),
        "live": live, "price_basis": price_basis,
        "live_price_used": use_live_price,
        "review_table": review, "excluded_table": excluded,
        "access": {"ready": access.get("ready"), "missing": access.get("missing"),
                   "relay_mode": access.get("relay_mode"),
                   "coupang_accounts": access.get("coupang_accounts")},
    }
