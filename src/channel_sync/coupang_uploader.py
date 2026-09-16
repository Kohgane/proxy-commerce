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


def upload(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """쿠팡에 상품을 등록하고 {"product_id", "url"}을 반환한다.

    Raises:
        ChannelCredentialsMissing: COUPANG_* 환경변수 미설정
        ChannelUploadError: 원화 판매가 0 또는 Wing API 실패
    """
    from src.uploaders.coupang_uploader import CoupangUploader

    # F29: 예전엔 `CoupangUploader()` — **계정 없이** 만들었다. 계정이 없으면 배송·자격을
    #   무접두 이름으로만 읽으므로, 오너가 Render에 `COUPANG_GOGANE_*`로 넣어 둔 값이
    #   이 경로에선 아예 안 보였다(그래서 「미입력 7필드」였다).
    #   **무접두가 있으면 계정은 빈 문자열** — 그게 셀러가 연동 화면에 넣은 자기 키다.
    #   무접두가 없을 때만 계정 접두로 내려간다(순서를 뒤집으면 남의 등록이 오너 자격으로 나간다).
    from src.seller_console.market_cred_view import resolve_upload_account
    account = resolve_upload_account()
    required = REQUIRED_ENVS if not account else []   # 계정 자격은 무접두로 존재하지 않는다

    return run_upload(
        CoupangUploader(account=account) if account else CoupangUploader(),
        product_data,
        required_envs=required,
        market_label=MARKET_LABEL,
    )
