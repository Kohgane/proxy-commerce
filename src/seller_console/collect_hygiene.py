"""src/seller_console/collect_hygiene.py — 수집 목록 위생: 비상품 행 판별기 (v87-W1).

수집 경로로 잘못 유입된 비상품 페이지(iCloud Mail·ChatGPT·검색·문서 등)를 **후보로만** 제시한다.
자동 삭제/거부는 하지 않는다 — 점수+사유를 남기고, 실행(보관)은 오너 클릭이 결정한다.

설계 원칙(돈 걸린 매칭과 동일):
- **실상품 오탐 0 최우선.** 쇼핑 도메인(temu·amazon·aliexpress…) 행은 **절대 후보로 잡지 않는다**
  (early-return). 추출 실패로 필드가 비어도 쇼핑몰이면 상품으로 간주(거부보다 미검출을 택함).
- 판별은 두 갈래로만 후보 처리:
  (A) host가 **명백한 비쇼핑 서비스**(메일·챗/AI·문서·클라우드·검색·SNS·뱅킹 등)  → 확정 후보.
  (B) 쇼핑도 비쇼핑목록도 아닌 host인데 **가격·이미지 전무 + 상품 URL 마커 부재**       → 보수적 후보.
- 점수와 사유를 행에 남긴다(하한 높게). 놓친 건(미검출)은 정직하게 미검출로 둔다.

순수 함수(무 I/O) — 목록 뷰·유입 봉인·테스트가 공유하는 단일 소스.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

# 쇼핑 도메인(부분일치). 이 host면 상품으로 간주 → 절대 후보 아님(오탐 0 보증).
_SHOPPING_HOSTS = (
    "temu.com", "amazon.", "aliexpress.", "taobao.com", "tmall.com", "1688.com", "alibaba.com",
    "rakuten.co.jp", "rakuten.com", "coupang.com", "gmarket.co.kr", "auction.co.kr",
    "11st.co.kr", "smartstore.naver.com", "shopping.naver.com", "brand.naver.com",
    "mercari.com", "qoo10.", "dhgate.com", "iherb.com", "shopee.", "ebay.", "etsy.com",
    "shein.com", "yoshidakaban.com", "zozo.jp", "vvic.com", "paypaymall.yahoo.co.jp",
    "shopping.yahoo.co.jp", "store.shopping.yahoo.co.jp", "kohganemultishop", "wadiz.kr",
)

# 명백한 비쇼핑 서비스(부분일치). 이 host면 확정 후보(A).
_NON_PRODUCT_HOSTS = (
    # 메일/웹메일
    "mail.google.com", "mail.me.com", "icloud.com", "outlook.", "mail.yahoo.",
    "mail.naver.com", "mail.daum.net", "protonmail.", "proton.me",
    # 챗/AI
    "chatgpt.com", "chat.openai.com", "openai.com", "claude.ai", "gemini.google.com",
    "bard.google.com", "perplexity.ai", "copilot.microsoft.com", "poe.com",
    # 문서/오피스/노트
    "docs.google.com", "sheets.google.com", "slides.google.com", "notion.so", "notion.site",
    "office.com", "sharepoint.com", "onedrive.", "hwp.", "evernote.com",
    # 클라우드 스토리지
    "drive.google.com", "dropbox.com", "box.com", "mega.nz",
    # 검색/포털 홈
    "google.com/search", "bing.com/search", "duckduckgo.com", "search.naver.com",
    "search.daum.net", "search.yahoo.",
    # SNS/영상(쇼핑 탭 아님)
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "youtu.be", "tiktok.com", "reddit.com", "pinterest.",
    "threads.net", "cafe.naver.com", "blog.naver.com", "tistory.com", "brunch.co.kr",
    # 개발/지식
    "github.com", "gitlab.com", "stackoverflow.com", "wikipedia.org", "medium.com",
    # 뱅킹/정부/생산성
    "paypal.com", "toss.im", "kakaobank.com", "gov.kr", "hometax.go.kr",
    "calendar.google.com", "zoom.us", "meet.google.com", "slack.com", "trello.com",
)

# 상품 상세 URL 마커(있으면 상품 페이지일 가능성 ↑ → 후보 감점).
_PRODUCT_URL_MARKER_RE = re.compile(
    r"(/dp/|/gp/product|/g-\d|goods[_/]?id|/goods/|/item[/.]|/product[s]?/|/p/\d|/offer/|itemId=|productId=|/g-\d{6,})",
    re.I,
)

_CANDIDATE_THRESHOLD = 70


def _host_of(url: str) -> str:
    try:
        netloc = urlparse(url or "").netloc.lower()
    except Exception:
        netloc = ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _is_shopping_host(url: str) -> bool:
    host = _host_of(url)
    full = (host + urlparse(url or "").path).lower()
    return any(s in host or s in full for s in _SHOPPING_HOSTS)


def _matches_non_product_host(url: str) -> bool:
    host = _host_of(url)
    # 일부 항목은 host+path 조합(google.com/search 등)으로 판정.
    full = (host + urlparse(url or "").path).lower()
    for pat in _NON_PRODUCT_HOSTS:
        if "/" in pat:
            if pat in full:
                return True
        elif host == pat or host.endswith("." + pat) or host.startswith(pat) or pat in host:
            return True
    return False


def _has_price(row: dict) -> bool:
    raw = str(row.get("price") or "").replace(",", "").strip()
    if not raw:
        return False
    m = re.search(r"\d+(?:\.\d+)?", raw)
    try:
        return bool(m) and float(m.group(0)) > 0
    except ValueError:
        return False


def _image_count(row: dict) -> int:
    if str(row.get("image_url") or "").strip():
        return 1
    try:
        ex = row.get("extra") if isinstance(row.get("extra"), dict) else json.loads(row.get("extra_json") or "{}")
    except Exception:
        ex = {}
    imgs = ex.get("images") if isinstance(ex, dict) else None
    return len(imgs) if isinstance(imgs, list) else 0


def _option_count(row: dict) -> int:
    try:
        ex = row.get("extra") if isinstance(row.get("extra"), dict) else json.loads(row.get("extra_json") or "{}")
    except Exception:
        ex = {}
    opts = ex.get("options") if isinstance(ex, dict) else None
    return len(opts) if isinstance(opts, list) else 0


def classify_row(row: dict) -> dict:
    """행이 '비상품 정리 후보'인지 판별. {is_candidate, score, reasons} 반환.

    쇼핑 도메인이면 무조건 후보 아님(오탐 0). 그 외에만 A/B 규칙 적용.
    """
    url = str(row.get("url") or "")
    result = {"is_candidate": False, "score": 0, "reasons": []}

    # 오탐 0 보증: 쇼핑 도메인은 상품으로 간주(early-return).
    if not url or _is_shopping_host(url):
        return result

    score = 0
    reasons: list[str] = []
    has_price = _has_price(row)
    n_img = _image_count(row)
    n_opt = _option_count(row)
    has_product_marker = bool(_PRODUCT_URL_MARKER_RE.search(url))
    host = _host_of(url)

    # (A) 명백한 비쇼핑 서비스 → 확정 후보.
    if _matches_non_product_host(url):
        score += 80
        reasons.append("쇼핑몰이 아닌 사이트(메일·챗·문서·검색·SNS 등)")
        if not has_price and n_img == 0:
            score += 10
            reasons.append("가격·이미지 없음")
    else:
        # (B) 쇼핑도 비쇼핑목록도 아님: 상품 신호가 전무할 때만 보수적 후보.
        if not has_price and n_img == 0 and n_opt == 0 and not has_product_marker:
            score += 55
            reasons.append("소싱처 화이트리스트 밖")
            reasons.append("가격·이미지·옵션 전무")
            # 상품 URL 마커도 없음 → 상품 상세로 보기 어려움.
            score += 15
            reasons.append("상품 URL 형태 아님")

    result["score"] = score
    result["reasons"] = reasons
    result["is_candidate"] = score >= _CANDIDATE_THRESHOLD
    return result


def is_cleanup_candidate(row: dict) -> bool:
    return classify_row(row)["is_candidate"]


def summarize_candidates(rows) -> dict:
    """행 목록에 대해 정리 후보 요약을 낸다(오너가 보관 실행 전 3수치 판정용).

    {"total": N, "candidates": C, "kept": N-C, "samples": [{id,url,title,score,reasons}...]}
    — 삭제/보관을 하지 않는다. 후보 목록·수치만 계산(판단은 오너).
    """
    total = 0
    candidates = []
    for row in rows or []:
        total += 1
        c = classify_row(row)
        if c["is_candidate"]:
            candidates.append({
                "id": row.get("id"),
                "url": row.get("url"),
                "title": (row.get("title") or "")[:80],
                "score": c["score"],
                "reasons": c["reasons"],
            })
    return {
        "total": total,
        "candidates": len(candidates),
        "kept": total - len(candidates),
        "samples": candidates,
    }
