"""공유 텍스트 → 수집 초안. **있는 것만 넣고, 없는 것은 없다고 적는다.**

공유 텍스트가 주는 건 **제목과 링크뿐**이다. 가격·이미지·옵션은 거기 없다.
그래서 이 경로가 만드는 초안은 **부분 초안**이고, 그 사실을 화면이 말한다 —
기존 '간이 수집' 상태(`SIMPLE_COLLECT_MODES`)를 그대로 쓴다. 새 상태를 만들지 않는다.

없는 값을 0·빈 문자열로 채워 "수집됨"으로 보이게 하는 것이 이 파일이 막으려는 바로 그 일이다
(가격 0원짜리 상품이 목록에 앉으면 그건 수집이 아니라 오염이다).

## 두 갈래 — 어느 쪽인지 화면이 말한다

폰의 iOS 단축어 「URL 확장」이 단축 링크를 펴 주면 **최종 URL에 `id`·`price`가 실려 온다**
(실측 2026-09-11 상하이: 리다이렉트만으로 온다 — 로그인도 페이지 렌더도 불요.
단 **폰이 중국 사이트로 직접 나갈 때만**이다).

| 폰이 폈나 | 초안이 갖는 것 | 미수집 | 등록 |
|---|---|---|---|
| ✅ 폈다 | 제목 · itemId · **가격(CNY)** · 링크 | 이미지 · 옵션 · 상세 | **가능** |
| ❌ 못 폈다 | 제목 · 단축 링크(tk) | 가격 · 이미지 · 옵션 · 상세 | 닫힘 |

**우리는 왜 못 폈는지 모른다 — 그래서 단정하지 않는다**(C-F9-1).
이전 문구는 VPN 설정 때문이라고 **단정**했는데, 오너 실측에서 **VPN이 꺼진 채로**
같은 결과가 나와 그 문장이 그대로 오진이 됐다. 서버가 아는 건 셋뿐이다 —
최종 URL이 왔나 · 거기 상품번호가 있었나 · 가격이 있었나(`resolve_gap`).
원인은 「링크 진단」(`link_diag`)이 실제로 재서 말한다.

두 갈래를 섞지 않는다 — 한쪽을 다른 쪽인 척 하면 그게 가짜 성공이다.

**가격은 공유 시점 값이다.** 실시간 시세가 아니라 그 링크가 만들어진 순간의 값이라
`price_source='share_link'`로 표시하고 화면이 그대로 밝힌다.

## 서버는 타오바오에 나가지 않는다 (C-T4'' 최종, 실측)

`m.intl.taobao.com` 상세는 **IP 무관 로그인 벽**이다(VPN 온 +82 / 오프 +852 동일).
단축 링크도 해외 IP에선 연결 거부다. **서버측 경로는 0** — 플래그조차 두지 않았다.
실측이 닫은 문 앞의 "혹시" 코드는 보험이 아니라 **부채**이기 때문이다.
**펴는 일은 폰이 한다**(중국망에 있으니까). 나머지는 확장이 한다(세션이 거기 있으니까).

## 식별자

`id`가 있으면 `taobao:item:<id>` — 단축 링크로 담은 것과 편 링크로 담은 것이 **한 상품으로 합쳐진다**.
없으면 `tbshare:<토큰>:<tk>`(링크 자체가 그 상품이다). 우선순위는 **itemId > tk**.

## 보강은 PC 확장이 한다 (C-T4')

이미지·옵션은 어느 갈래에서도 안 온다. '보강 대기' 초안을 **로그인된 브라우저**에서 열어
tier1 추출 → 초안 병합. 퍼센티가 같은 구조인 이유다.
가격이 없는 동안 **마켓 등록은 닫아 둔다**: 마진을 못 내고, 0으로 채우면 그게 날조다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 공유 텍스트로 만든 초안이 채우지 **못하는** 필드 — 화면이 '보강 필요'로 읽는 근거.
UNCOLLECTED_FIELDS = ("price", "images", "options", "description")


def collect_from_share_text(raw: str, *, seller_id: str = "", source: str = "share_text",
                            translate: bool = True,
                            final_url: str = "") -> dict:
    """공유 텍스트 한 덩어리 → 수집 초안 1건.

    반환 `{ok, item_id?, url, title, title_ko, item_id_taobao, price, currency, uncollected,
            enrich_state, error?}`.
    """
    from src.collectors.share_text import (canonical_item_url, is_short_link,
                                            parse_share_text)

    share = parse_share_text(raw, final_url=final_url)
    url = share.get("url", "")
    if not url:
        # C-F7: 왜 못 찾았는지 말한다(길이·판정만 — 원문은 안 싣는다).
        from src.collectors.share_text import link_failure_reason
        return {"ok": False, "error": link_failure_reason(raw, final_url)}
    # C-F11: **서버가 단축 링크를 펼 수 있다**(오너 실측 2026-09-12 — `e.tb.cn` → 200 →
    #   본문에 `item.taobao.com/…&id=…&price=…`). F9까지 "못 읽는다"고 적은 건
    #   **리다이렉트 쿼리만 봤기 때문**이다. 쿼리엔 없었고 본문에는 있었다.
    #   여기서 펴는 것은 **상품번호와 공유 시점 가격**뿐이다 — 상세·이미지·옵션은
    #   여전히 로그인 벽 뒤이고(실측 불변) 그건 확장이 한다.
    #   폰이 이미 펴 줬으면(=id가 있으면) **다시 나가지 않는다.**
    resolve_reason = ""
    if not share.get("item_id") and is_short_link(url):
        from src.collectors.link_diag import resolve_short_link
        r = resolve_short_link(url)
        resolve_reason = r.get("reason", "")
        if r.get("ok"):
            share["item_id"] = r["item_id"]
            # 가격은 **비어 있을 때만** 채운다(폰이 준 값이 더 가까운 시점이다).
            if not share.get("price") and r.get("price"):
                share["price"] = r["price"]
                share["currency"] = r.get("currency") or "CNY"
            # 저장 URL = 정규형. 추적 파라미터를 안 남기고, 같은 상품이 한 키로 합쳐진다.
            url = canonical_item_url(r["item_id"]) or url
    share["resolve_reason"] = resolve_reason

    # 제목도 상품번호도 없으면 **이어갈 실마리가 없다** — 빈 행을 만들지 않는다.
    #   단 이 검사는 **해석 뒤**에 온다: 실측(C-F11) 뒤로는 서버가 단축 링크를 펴서
    #   상품번호를 만들어 낼 수 있으므로, 먼저 거절하면 그 실마리를 못 쓴다.
    #   (실측: 맨 URL을 넣었더니 빈 항목이 '수집됨'으로 앉아 편집 화면까지 넘어갔다.)
    if not share.get("title") and not share.get("item_id"):
        return {"ok": False, "url": url, "resolve_reason": resolve_reason,
                "error": ("이 링크에서 상품을 찾지 못했습니다. 앱 공유 글을 통째로 보내 주시거나, "
                          "상품 페이지에서 고가수집기로 수집해 주세요.")}

    item_id_site = share.get("item_id", "")

    title = share.get("title", "")
    title_ko = title
    if translate and title:
        try:
            from src.api.extension_api import _translate_payload
            tr = _translate_payload({"title": title, "description": ""})
            title_ko = tr.get("title_ko") or title
        except Exception as exc:                    # 번역 실패 = 원문 유지(가짜 번역 0)
            logger.warning("공유 수집: 제목 번역 실패 — %s", exc)

    # C-T3(3차): 폰이 링크를 펴 줬으면 **가격과 itemId가 함께 온다** → 미수집 목록이 줄어든다.
    #   가격은 공유 시점 값이다 — 실시간이 아니다. 그 사실을 필드로 남겨 화면이 그대로 말한다.
    price = share.get("price", "")
    currency = share.get("currency", "")
    uncollected = [f for f in UNCOLLECTED_FIELDS if not (f == "price" and price)]
    # 폰이 펴 준 최종 URL이 있으면 그쪽이 더 정확한 소스다. 단 **정규형으로** 저장한다 —
    #   원문엔 `suid`·`un`·`wxsign`이 붙어 오고, 파라미터가 다르면 같은 상품이 여러 행으로 갈린다.
    if share.get("item_id"):
        url = canonical_item_url(share["item_id"]) or share.get("final_url") or url

    from src.seller_console.collect_history_store import append as history_append
    _ret = history_append(
        return_durable=True, source=source, url=url,
        title=title_ko or title or "(제목 없음)",
        image="", price=price, currency=currency,   # ← 없으면 빈칸. 만들지 않는다
        status=("보강 대기" if not price else "ok"), seller_id=str(seller_id or ""),
        extra={
            "title": title, "title_ko": title_ko,
            "images": [], "price": price, "currency": currency,
            # 실시간 시세가 아니다 — 공유한 그 순간의 값이다. 화면이 이걸 그대로 밝힌다.
            "price_source": ("share_link" if price else ""),
            "price_captured_at_share": bool(price),
            # 목록·드로어가 '간이'로 읽는 기존 상태를 그대로 쓴다(새 상태 발명 금지).
            "mode": "share",
            "share_tk": share.get("tk", ""),
            "share_code": share.get("share_code", ""),
            "site_item_id": share.get("item_id") or item_id_site,
            "short_name": share.get("short_name", ""),
            "final_url": share.get("final_url", ""),
            "uncollected": uncollected,
            # C-T3: 보강 전까지 마켓 등록을 막는 근거(가격이 없으면 마진을 못 낸다 — 0 발명 금지).
            "enrich_state": ("done" if price else "pending"),
            "share_raw": share.get("raw", "")[:500],
        },
    )
    item_id, durable = _ret if (isinstance(_ret, tuple) and len(_ret) == 2) else (_ret, True)
    if not item_id or not durable:
        return {"ok": False, "url": url, "error": "저장 영속화 실패(재시도 필요)"}

    logger.info("공유 수집 stage=saved item=%s url=%s item_id=%s 가격=%s%s 미수집=%s 게이트=%s",
                item_id, url, share.get("item_id") or item_id_site or "-",
                price or "-", currency or "", ",".join(uncollected) or "-",
                "done" if price else "pending")
    # C-F9-1: 갈래 판정과 문장은 **원본 `share`에서 한 번만** 만든다.
    #   호출부가 반환 dict로 다시 판정하면 안 된다 — 여기서 `item_id`는 **이력 행 ID**고
    #   `share["item_id"]`는 **상품번호**다. 같은 이름 다른 뜻이라 그대로 재면 늘 오판한다.
    from src.collectors.share_text import gap_message, resolve_gap
    return {"ok": True, "item_id": item_id, "url": url, "title": title,
            "title_ko": title_ko, "item_id_taobao": share.get("item_id") or item_id_site,
            "uncollected": uncollected, "price": price, "currency": currency,
            # 가격이 왔으면 마진을 낼 수 있다 → 등록 가능. 없으면 닫힌 채(0 발명 금지).
            "enrich_state": ("done" if price else "pending"),
            # 서버가 **본 것만** 담는다: 최종 URL이 왔나 · 상품번호가 있었나 · 가격이 있었나.
            "resolve_gap": resolve_gap(share), "message": gap_message(share),
            }


def collect_input(raw: str, *, seller_id: str = "", source: str = "input",
                  final_url: str = "", translate: bool = True) -> dict:
    """**입구 하나짜리 함수.** 단건·일괄·API·텔레그램이 전부 이걸 부른다.

    실측(오너 2026-09-11, 폰): 「여러 URL 한 번에」가 이 판단을 **제 나름대로** 하고 있어
    같은 공유 텍스트가 단건에선 초안이 되고 일괄에선 "실패 2"가 됐다.
    판단이 네 벌이면 네 가지로 갈라진다 — 그래서 한 벌만 둔다.

    판단은 둘뿐이다:
      · 타오바오 계열이고 제목이 있으면 → **공유 초안**(서버 수집 시도 0)
      · 그 외 → 기존 수집 코어(`collect_one_url`)

    반환에 `kind`를 실어 호출부가 화면을 고를 수 있게 한다 —
    `share_draft`(초안 생성) / `collected`(정상 수집) / `failed`.
    """
    from src.collectors.share_text import is_taobao_family, parse_share_text

    share = parse_share_text(raw, final_url=final_url)
    url = share.get("url", "")
    if not url:
        from src.collectors.share_text import link_failure_reason
        return {"ok": False, "kind": "failed", "url": "",
                "error": link_failure_reason(raw, final_url)}

    # C-F7: **같은 상품이 두 키로 쌓이는 것**을 막는다.
    #   단축 링크만 담으면 `tbshare:<토큰>:<tk>`, 나중에 폰이 편 링크로 담으면 `taobao:item:<id>` —
    #   키가 달라 남남이 된다. 다행히 **편 링크가 `short_name`에 그 토큰을 싣고 온다**(실측 원문).
    #   그래서 편 링크로 올 때는 단축 키로도 한 번 더 찾아본다(발명 0 — 실측에 있는 값만 쓴다).
    alt_key_url = ""
    if share.get("short_name") and share.get("item_id"):
        _tk = share.get("tk", "")
        alt_key_url = f"https://e.tb.cn/{share['short_name']}" + (f"?tk={_tk}" if _tk else "")

    # 타오바오는 **서버가 못 읽는다**(실측). 읽어 보고 실패하는 게 아니라 아예 안 간다.
    #   C-F7 실측: 조건에 `and share.get("title")`이 붙어 있어, **제목 없는 맨 타오바오 URL**은
    #   그대로 서버 수집으로 떨어졌다(= F2의 "요청 0"에 구멍). 서버가 못 읽는 건 제목 유무와 무관하다.
    if is_taobao_family(url):
        # C-F11: 「이어갈 실마리가 있나」 판단을 **여기서 또 하지 않는다.**
        #   여기 있던 사본은 `collect_from_share_text`의 해석(단축 링크 펴기)보다 **먼저** 걸려서,
        #   서버가 상품번호를 만들어 낼 수 있는 맨 단축 URL을 미리 거절했다 —
        #   판단이 두 벌이면 늘 앞의 것이 이긴다. 그래서 한 벌만 남긴다(F1의 교훈과 같은 자리).
        r = collect_from_share_text(raw, seller_id=seller_id, source=source,
                                    translate=translate, final_url=final_url)
        r["kind"] = "share_draft" if r.get("ok") else "failed"
        if alt_key_url:
            r["alt_key_url"] = alt_key_url      # 호출부 중복 조회용(같은 상품의 단축 링크 형태)
        return r

    from src.api.extension_api import collect_one_url
    r = collect_one_url(url, seller_id=seller_id, source=source)
    if r.get("ok"):
        r["kind"] = "collected"
        return r
    # 못 읽었지만 공유 글에 제목이 있으면 초안이라도 세운다(빈손으로 돌려보내지 않는다).
    if share.get("title"):
        r2 = collect_from_share_text(raw, seller_id=seller_id, source=source,
                                     translate=translate, final_url=final_url)
        if r2.get("ok"):
            r2["kind"] = "share_draft"
            return r2
    r["kind"] = "failed"
    return r
