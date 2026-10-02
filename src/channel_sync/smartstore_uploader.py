"""스마트스토어(네이버 커머스) 채널 업로드 브리지.

UploadDispatcher._upload_smartstore()가 `from src.channel_sync import smartstore_uploader`로
로드하여 `smartstore_uploader.upload(product_data)`를 호출한다.
실제 등록 로직은 `src.uploaders.NaverSmartStoreUploader`(Phase 17-2, OAuth2)를 재사용한다.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from ._channel_bridge import ChannelCredentialsMissing, run_upload

MARKET_LABEL = "스마트스토어"


def upload(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """스마트스토어에 상품을 등록하고 {"product_id", "url"}을 반환한다.

    네이버 커머스 자격증명은 NAVER_CLIENT_ID/SECRET 또는 NAVER_COMMERCE_CLIENT_ID/SECRET
    어느 쪽이든 허용한다(코드 경로별 명명 혼용 흡수).

    Raises:
        ChannelCredentialsMissing: 네이버 자격증명 미설정
        ChannelUploadError: 원화 판매가 0 또는 커머스 API 실패
    """
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    from src.seller_console.market_cred_view import current_naver_account

    # U0b(오너 2026-10-02 정정): 스토어를 고르면(`smartstore:chezgoga`·`smartstore:gocosmos`) 그 스토어 키로 —
    #   `NAVER_<STORE>_CLIENT_ID/SECRET`(없으면 공용 키 폴백 + 경고 — 업로더 `_acct_env`).
    account = current_naver_account()
    up = NaverSmartStoreUploader(account=account) if account else NaverSmartStoreUploader()
    client_id = getattr(up, "client_id", "") or (os.getenv("NAVER_CLIENT_ID") or os.getenv("NAVER_COMMERCE_CLIENT_ID"))
    client_secret = (getattr(up, "client_secret", "")
                     or (os.getenv("NAVER_CLIENT_SECRET") or os.getenv("NAVER_COMMERCE_CLIENT_SECRET")))
    if not client_id or not client_secret:
        raise ChannelCredentialsMissing(
            "스마트스토어 자격증명 미설정: "
            "NAVER_CLIENT_ID(또는 NAVER_COMMERCE_CLIENT_ID) / "
            "NAVER_CLIENT_SECRET(또는 NAVER_COMMERCE_CLIENT_SECRET)"
            + (f" · 스토어 전용 NAVER_{account.upper()}_CLIENT_ID/SECRET" if account else "")
        )

    return run_upload(
        up,
        product_data,
        required_envs=[],
        market_label=MARKET_LABEL,
    )
