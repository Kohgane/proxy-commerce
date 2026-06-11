"""11번가(11st) 채널 업로드 브리지.

UploadDispatcher._upload_elevenst()가 `from src.channel_sync import elevenst_uploader`로
로드하여 `elevenst_uploader.upload(product_data)`를 호출한다.
실제 등록 로직은 `src.uploaders.ElevenStUploader`(11번가 OpenAPI)를 재사용한다.
"""
from __future__ import annotations

from typing import Any, Dict

from ._channel_bridge import run_upload

REQUIRED_ENVS = ["ELEVENST_API_KEY"]
MARKET_LABEL = "11번가"


def upload(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """11번가에 상품을 등록하고 {"product_id", "url"}을 반환한다.

    Raises:
        ChannelCredentialsMissing: ELEVENST_API_KEY 미설정
        ChannelUploadError: 원화 판매가 0 또는 OpenAPI 실패
    """
    from src.uploaders.elevenst_uploader import ElevenStUploader

    return run_upload(
        ElevenStUploader(),
        product_data,
        required_envs=REQUIRED_ENVS,
        market_label=MARKET_LABEL,
    )
