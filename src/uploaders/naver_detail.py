"""Y7-F(오너 2026-10-09) — 네이버 `detailContent` = 상세페이지 HTML 조립. 등록과 사전검증이 **같은 함수**.

13:32 KST 실측: 플리츠 세트 셰고가 등록 400 `originProduct.detailContent NotBlank`. 네이버 본문은 화면 폼의
`description_html or description`(상세 설명 텍스트)만 썼고, 그 상품은 텍스트가 비어 있었다(상세 이미지는 아예 안 실었다).

조립(위 → 아래):
  1. 상세 설명 텍스트(마켓용 — 한국어만·가게 줄 뺀 S2 결과) — 문단마다 `<p>`
  2. 상세 이미지 `<img>` — 등록이 보낼 그 목록(번역본 토글·CDN 반영 뒤)
  3. KC 구매대행 고지(`PURCHASE_AGENT_NOTICE`) — 이미 있으면 다시 넣지 않음
  플러그 고지는 국내 마켓 공통 필터(`korea_voltage_filter`)가 해당 SKU가 있을 때 맨 위에 얹는다(여기서 넣지 않음 — 두 번 안 붙게).

상세 이미지도 텍스트도 없으면 **빈 문자열**(고지만으로 본문을 채우지 않는다) — 사전검증이 `detail_blank`로 보류한다.
셀러가 「상세페이지 꾸미기」로 직접 만든 블록이 있으면 그것이 정본이다(호출부가 이 함수를 부르지 않는다).

Y7-G(오너 2026-10-09 15:56 KST — 사전검증 「통과」 → 등록 「상세 본문 비어 있음」):
- 판정은 **`judge()` 하나** — 사전검증과 등록이 같은 본문(`build`)을 같은 업로더로 네이버 CDN에 올린 **뒤** 잰다.
  예전 사전검증은 「상세 이미지 URL이 있다」로 통과시켰고, 등록은 그 장을 받아 → 변환 → 올리다 못 올려 빈 본문이 됐다.
- 셀러 텍스트가 없으면 `detail_auto`(사전검증이 자동으로 만든 상세 초안 — 텍스트 + 갤러리 사진)를 쓴다.
"""
from __future__ import annotations

import html as _html
from typing import Any, Dict, List


def _text_of(pd: Dict[str, Any]) -> str:
    """보낼 상세 설명 텍스트 — 이미 HTML이면 그대로, 아니면 마켓 규칙(한국어만·가게 줄 뺌)을 지난 평문."""
    raw = str(pd.get("description_html") or "").strip()
    if raw:
        return raw
    txt = str(pd.get("description") or pd.get("description_ko") or "").strip()
    if not txt:
        return ""
    try:
        from src.seller_console.upload_dispatcher import market_description
        txt = market_description(txt)
    except Exception:
        pass
    paras = [p.strip() for p in txt.replace("\r", "").split("\n\n") if p.strip()]
    return "".join('<p style="margin:0 0 12px;white-space:pre-wrap">' + _html.escape(p) + "</p>" for p in paras)


def auto_of(pd: Dict[str, Any]) -> Dict[str, Any]:
    """사전검증이 만든 상세 자동 초안 `{text, images, provider, at}` — 없으면 {}. 셀러 텍스트가 있으면 쓰지 않는다(호출부 판단)."""
    a = pd.get("detail_auto")
    return a if isinstance(a, dict) and (str(a.get("text") or "").strip() or a.get("images")) else {}


def _auto_text(pd: Dict[str, Any]) -> str:
    txt = str(auto_of(pd).get("text") or "").strip()
    if not txt:
        return ""
    try:
        from src.seller_console.upload_dispatcher import market_description
        txt = market_description(txt)
    except Exception:
        pass
    paras = [p.strip() for p in txt.replace("\r", "").split("\n\n") if p.strip()]
    return "".join('<p style="margin:0 0 12px;white-space:pre-wrap">' + _html.escape(p) + "</p>" for p in paras)


def _expand(urls) -> List[str]:
    out = []
    for u in urls or []:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith(("http://", "https://")) and u not in out:
            out.append(u)
    return out


def detail_images(pd: Dict[str, Any]) -> List[str]:
    """보낼 상세 이미지 — `//` 주소는 `https:`로 펴고, 가게 아이콘·추적 픽셀은 뺀다(등록 빌더와 같은 필터).

    13:32 그 상품: 상세 이미지 2장 = `//img.alicdn.com/…`(펴야 하는 주소) + 51×24 가게 아이콘 → 실제로 보낼 장은 1장.
    """
    out = _expand(pd.get("detail_images"))
    try:
        from src.collectors.collect_status import real_detail_images
        out = real_detail_images(out)
    except Exception:
        pass
    return out


def has_content(pd: Dict[str, Any]) -> bool:
    """상세 이미지 1장 이상 또는 텍스트(셀러 것 또는 자동 초안)가 있나 — **URL 기준**(올리기 전). 등록·사전검증 판정은 `judge`."""
    return bool(detail_images(pd)) or bool(_text_of(pd)) or bool(auto_of(pd))


def build(pd: Dict[str, Any]) -> str:
    """상세페이지 HTML — 이미지도 텍스트도 없으면 ''. 셀러 텍스트가 없으면 자동 초안(텍스트 + 갤러리 사진)을 얹는다."""
    text = _text_of(pd)
    imgs = detail_images(pd)
    if not text and auto_of(pd):
        text = _auto_text(pd)
        imgs = imgs + [u for u in _expand(auto_of(pd).get("images")) if u not in imgs]
    if not text and not imgs:
        return ""
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE
    parts = ['<div style="max-width:860px;margin:0 auto">']
    if text:
        parts.append(text)
    for u in imgs:
        parts.append('<img src="' + _html.escape(u, quote=True) + '" style="max-width:100%;display:block;margin:0 auto" alt="">')
    if PURCHASE_AGENT_NOTICE not in text:
        parts.append('<p class="kgp-agent-notice" style="margin-top:20px;font-size:12px;color:#666">'
                     + _html.escape(PURCHASE_AGENT_NOTICE) + "</p>")
    parts.append("</div>")
    return "".join(parts)


def judge(html_body: str, uploader=None, sku: str = "") -> Dict[str, Any]:
    """**등록과 사전검증이 같이 쓰는 판정** — 본문 이미지를 네이버 CDN에 올린 뒤(캐시 있으면 재사용) 내용이 남는지.

    반환 `{html, ok, dropped:[{url, reason}], kept, cached}`. 업로더가 없거나 업로드를 끈 환경(`image_upload_enabled`
    False)이면 올리지 않고 그대로 잰다(등록도 그 환경에선 올리지 않는다 — 같은 답).
    못 올린 장만 빠지고 텍스트가 있으면 그대로 보낸다(오너 2번).
    """
    body = str(html_body or "")
    rep: Dict[str, Any] = {"dropped": [], "kept": 0, "cached": 0}
    if uploader is not None and getattr(uploader, "image_upload_enabled", False) and "<img" in body:
        body = uploader._detail_to_cdn(body, sku, report=rep)
    return {"html": body, "ok": body_has_content(body), **rep}


def body_has_content(html_body: str) -> bool:
    """보낼 본문에 고지 말고 **내용**(이미지 또는 고지가 아닌 글자)이 있나 — 등록 직전 판정."""
    import re as _re
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE
    b = str(html_body or "")
    if _re.search(r"<img\b", b, _re.I):
        return True
    txt = _re.sub(r"<[^>]+>", " ", b)
    txt = _html.unescape(txt).replace(PURCHASE_AGENT_NOTICE, " ")
    try:
        from src.seller_console.notice_texts import PLUG_CN_LINES, PLUG_CN_TITLE
        for ln in (PLUG_CN_TITLE,) + tuple(PLUG_CN_LINES):
            txt = txt.replace(ln, " ")
    except Exception:
        pass
    return bool(txt.strip())
