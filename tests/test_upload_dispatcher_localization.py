from __future__ import annotations


def test_upload_dispatcher_uses_market_locale_localized_payload():
    from src.seller_console.upload_dispatcher import UploadDispatcher

    payload, localized = UploadDispatcher._payload_for_market(
        {
            "title": "원문 제목",
            "localized": {
                "en-US": {"title": "Localized Title", "description": "Localized Description", "keywords": [], "options": []}
            },
        },
        "amazon",
    )

    assert localized is True
    assert payload["title"] == "Localized Title"
    assert payload["description"] == "Localized Description"


def test_upload_dispatcher_falls_back_to_original_when_localized_missing():
    from src.seller_console.upload_dispatcher import UploadDispatcher

    payload, localized = UploadDispatcher._payload_for_market({"title": "원문 제목", "localized": {}}, "amazon")

    assert localized is False
    assert payload["title"] == "원문 제목"
