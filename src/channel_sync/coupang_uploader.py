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

    return run_upload(
        CoupangUploader(),
        product_data,
        required_envs=REQUIRED_ENVS,
        market_label=MARKET_LABEL,
    )
