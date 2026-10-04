"""쿠팡 채널 업로드 브리지.

UploadDispatcher._upload_coupang()가 `from src.channel_sync import coupang_uploader`로
로드하여 `coupang_uploader.upload(product_data)`를 호출한다.
실제 등록 로직은 `src.uploaders.CoupangUploader`(Phase 17-2, Wing API HMAC)를 재사용한다.
"""
from __future__ import annotations

from typing import Any, Dict

from ._channel_bridge import run_upload

REQUIRED_ENVS = ["COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID"]
MARKET_LABEL = "쿠팡"


def make_uploader():
    """이 요청이 쓸 쿠팡 업로더 하나 — 계정이 정해지면 **그 계정의 키**로 만든다(U0).

    실측(U0, 2026-10-02): 예전엔 `CoupangUploader(account=…)`로 만들어 **배송 칸만** 계정 접두를 읽고
    API 키는 무접두를 읽었다 — 우주대행을 고르면 고가네 키에 우주대행 출고지가 섞일 수 있었다.
    키·업체코드도 `_account_creds`(계정 접두 → 무접두 흡수 계정 순)로 같은 계정에서 읽는다.
    """
    from src.uploaders.coupang_uploader import CoupangUploader
    from src.seller_console.market_cred_view import resolve_upload_account
    account = resolve_upload_account()
    if not account:
        return CoupangUploader(), ""
    from src.pipeline.coupang_replicate import _account_creds
    access, secret, vendor = _account_creds(account)
    return CoupangUploader(access_key=access, secret_key=secret, vendor_id=vendor, account=account), account


def upload(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """쿠팡에 상품을 등록하고 {"product_id", "url"}을 반환한다.

    Raises:
        ChannelCredentialsMissing: COUPANG_* 환경변수 미설정
        ChannelUploadError: 원화 판매가 0 또는 Wing API 실패
    """
    # F29: 예전엔 `CoupangUploader()` — **계정 없이** 만들었다. 계정이 없으면 배송·자격을
    #   무접두 이름으로만 읽으므로, 오너가 Render에 `COUPANG_GOGANE_*`로 넣어 둔 값이
    #   이 경로에선 아예 안 보였다(그래서 「미입력 7필드」였다).
    #   **무접두가 있으면 계정은 빈 문자열** — 그게 셀러가 연동 화면에 넣은 자기 키다.
    #   무접두가 없을 때만 계정 접두로 내려간다(순서를 뒤집으면 남의 등록이 오너 자격으로 나간다).
    up, account = make_uploader()
    required = REQUIRED_ENVS if not account else []   # 계정 자격은 무접두로 존재하지 않는다

    return run_upload(
        up,
        prepared_input(product_data),   # F48-c 선택 · F51 SKU별 판매가 — 사전검증과 같은 반영
        required_envs=required,
        market_label=MARKET_LABEL,
    )


def precheck(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """F48-d 사전검증 — **등록과 같은 변환**(to_collected → prepare_product)을 거친 뒤 판정한다.

    같은 상품을 다른 모양으로 넣고 판정하면, 사전검증이 본 것과 등록이 보내는 것이 갈린다.
    """
    from ._channel_bridge import to_collected

    up, _account = make_uploader()
    prepared = up.prepare_product(to_collected(prepared_input(product_data)))
    return up.precheck(prepared)


def with_choices(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """F48-c — 편집 화면에서 오너가 정한 쿠팡 값(`coupang_attributes`·`coupang_option_pick`)을 반영.

    사전검증·등록·옵션 블록이 **같은 함수**를 지난다(한 곳에서만 반영 — 셋이 다르게 보면 거짓말이 된다).
    """
    from src.uploaders.coupang_options import apply_choices
    pd = dict(product_data or {})
    return apply_choices(pd, pd.get("coupang_attributes"), pd.get("coupang_option_pick"))


def with_sku_prices(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """F51 — SKU마다 **그 SKU 원가로** 쿠팡 판매가를 낸다(`sell_price_krw`). 식은 등록과 같은 하나
    (`UploadDispatcher._landed_krw` → `calc_sell_price`). 못 내면 판매가를 비우고 사유(`price_why`)만 남긴다 —
    그 SKU가 하나라도 있으면 다중 등록은 열리지 않는다(F51 규칙 2, `coupang_options.sku_mode`).
    """
    pd = dict(product_data or {})
    skus = pd.get("skus")
    if not isinstance(skus, list) or not skus:
        return pd
    from src.seller_console.upload_dispatcher import UploadDispatcher
    # F51-b 6: 이 판매가들에 쓴 환율(값·출처·갱신 시각)을 같이 싣는다 — 옵션 블록 표가 그대로 보인다.
    try:
        from src.price import sell_fx_rates
        _fx_info = sell_fx_rates()[1]
        _curs = {str(k.get("currency") or pd.get("currency") or "").strip().upper()
                 for k in skus if isinstance(k, dict)}
        pd["fx_info"] = [{"currency": c, **_fx_info[c]} for c in sorted(_curs) if c in _fx_info]
    except Exception:
        pd["fx_info"] = []
    out = []
    for k in skus:
        if not isinstance(k, dict):
            continue
        k = dict(k)
        try:
            cost = float(k.get("price"))
        except (TypeError, ValueError):
            cost = 0.0
        cur = str(k.get("currency") or pd.get("currency") or "").strip().upper()
        if cost > 0 and cur:
            val, why = UploadDispatcher._landed_krw(
                {**pd, "price_original": cost, "price": cost, "currency": cur}, "coupang")
            if val > 0:
                k["sell_price_krw"] = int(round(val))
            else:
                k.pop("sell_price_krw", None)
                k["price_why"] = why
        else:
            k.pop("sell_price_krw", None)
            k["price_why"] = "SKU 원가 또는 통화가 없습니다"
        out.append(k)
    pd["skus"] = out
    return pd


def prepared_input(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """사전검증·등록·옵션 블록이 **같이** 지나는 입력 정리 — F48-c 선택 → F51 SKU별 판매가."""
    # Y8: 분해로 축이 3개를 넘으면 쿠팡 속성 3개 제한에 맞춰 3번째부터 「사양」 한 축으로(못 이으면 그대로 → 계획이 보류)
    from src.collectors.option_split import cap_axes
    return with_sku_prices(with_choices(cap_axes(product_data)))


def option_form(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """F48-c — 「쿠팡 필수 옵션」 블록 재료. 카테고리 예측 → 메타(릴레이 경유·카테고리 캐시) → 계획."""
    from src.uploaders.coupang_options import option_form as _form
    from ._channel_bridge import to_collected

    up, _account = make_uploader()
    _pi = prepared_input(product_data)
    prepared = up.prepare_product(to_collected(_pi))
    prepared["fx_info"] = _pi.get("fx_info") or []      # F51-b 6: SKU별 판매가에 쓴 환율(표에 싣는다)
    cat = up.predict_category(prepared.get("title", "")) or str(prepared.get("category_id") or "")
    if not cat:
        return {"ok": False, "error": "쿠팡 카테고리를 예측하지 못했습니다 — 제목을 확인해 주세요."}
    meta = up.get_category_meta(cat)
    out = _form(meta.get("attributes") or [], prepared, meta_ok=bool(meta),
                choices_from={"options": (product_data or {}).get("options") or []})
    return {"ok": True, "category": cat, **out}
