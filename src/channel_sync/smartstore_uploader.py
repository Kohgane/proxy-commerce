"""스마트스토어(네이버 커머스) 채널 업로드 브리지.

UploadDispatcher._upload_smartstore()가 `from src.channel_sync import smartstore_uploader`로
로드하여 `smartstore_uploader.upload(product_data)`를 호출한다.
실제 등록 로직은 `src.uploaders.NaverSmartStoreUploader`(Phase 17-2, OAuth2)를 재사용한다.
"""
from __future__ import annotations

from typing import Any, Dict

from ._channel_bridge import run_upload

REQUIRED_ENVS = ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"]
MARKET_LABEL = "스마트스토어"


def upload(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """스마트스토어에 상품을 등록하고 {"product_id", "url"}을 반환한다.

    Raises:
        ChannelCredentialsMissing: NAVER_* 환경변수 미설정
        ChannelUploadError: 원화 판매가 0 또는 커머스 API 실패
    """
    from src.uploaders.naver_uploader import NaverSmartStoreUploader

    return run_upload(
        NaverSmartStoreUploader(),
        product_data,
        required_envs=REQUIRED_ENVS,
        market_label=MARKET_LABEL,
    )
