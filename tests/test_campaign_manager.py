"""tests/test_campaign_manager.py — CampaignManager 테스트."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def manager(mock_env):
    """CampaignManager 인스턴스."""
    from src.marketing.campaign_manager import CampaignManager
    return CampaignManager(sheet_id="fake_id", sheet_name="campaigns")


def _mock_ws(records=None):
    ws = MagicMock()
    ws.get_all_records.return_value = records or []
    ws.get_all_values.return_value = []
    return ws


class TestCreateCampaign:
    def test_create_campaign(self, manager):
        """캠페인 생성 시 campaign_id가 포함된 딕셔너리를 반환해야 한다."""
        with patch('src.marketing.campaign_manager.open_sheet', return_value=_mock_ws()):
            result = manager.create_campaign({
                "name": "테스트 캠페인",
                "type": "email",
                "target_segment": "VIP",
                "budget_krw": 100000,
            })
        assert "campaign_id" in result
        assert result["name"] == "테스트 캠페인"
        assert result["status"] == "draft"

    def test_create_campaign_default_status(self, manager):
        """생성된 캠페인의 상태는 기본적으로 'draft'여야 한다."""
        with patch('src.marketing.campaign_manager.open_sheet', return_value=_mock_ws()):
            result = manager.create_campaign({"name": "기본 캠페인"})
        assert result["status"] == "draft"


class TestPauseCampaign:
    def test_pause_campaign(self, manager):
        """active 캠페인을 pause하면 상태가 'paused'로 변경되어야 한다."""
        campaign = {
            "campaign_id": "c1", "name": "캠페인1", "type": "email",
            "target_segment": "ALL", "start_date": "", "end_date": "",
            "status": "active", "budget_krw": "0", "spent_krw": "0", "created_at": "",
        }
        ws = _mock_ws([campaign])
        with patch('src.marketing.campaign_manager.open_sheet', return_value=ws):
            result = manager.pause_campaign("c1")
        assert result is not None
        assert result["status"] == "paused"

    def test_pause_draft_fails(self, manager):
        """draft 캠페인을 pause하면 None을 반환해야 한다."""
        campaign = {
            "campaign_id": "c2", "name": "캠페인2", "type": "email",
            "target_segment": "ALL", "start_date": "", "end_date": "",
            "status": "draft", "budget_krw": "0", "spent_krw": "0", "created_at": "",
        }
        ws = _mock_ws([campaign])
        with patch('src.marketing.campaign_manager.open_sheet', return_value=ws):
            result = manager.pause_campaign("c2")
        assert result is None


class TestResumeCampaign:
    def test_resume_campaign(self, manager):
        """paused 캠페인을 resume하면 상태가 'active'로 변경되어야 한다."""
        campaign = {
            "campaign_id": "c3", "name": "캠페인3", "type": "email",
            "target_segment": "ALL", "start_date": "", "end_date": "",
            "status": "paused", "budget_krw": "0", "spent_krw": "0", "created_at": "",
        }
        ws = _mock_ws([campaign])
        with patch('src.marketing.campaign_manager.open_sheet', return_value=ws):
            result = manager.resume_campaign("c3")
        assert result is not None
        assert result["status"] == "active"


class TestCompleteCampaign:
    def test_complete_campaign(self, manager):
        """active 캠페인을 complete하면 상태가 'completed'로 변경되어야 한다."""
        campaign = {
            "campaign_id": "c4", "name": "캠페인4", "type": "email",
            "target_segment": "ALL", "start_date": "", "end_date": "",
            "status": "active", "budget_krw": "0", "spent_krw": "0", "created_at": "",
        }
        ws = _mock_ws([campaign])
        with patch('src.marketing.campaign_manager.open_sheet', return_value=ws):
            result = manager.complete_campaign("c4")
        assert result is not None
        assert result["status"] == "completed"


class TestGetCampaigns:
    def test_get_campaigns_returns_list(self, manager):
        """get_campaigns는 리스트를 반환해야 한다."""
        campaigns = [
            {"campaign_id": "c5", "name": "A", "type": "email",
             "target_segment": "ALL", "start_date": "", "end_date": "",
             "status": "active", "budget_krw": "0", "spent_krw": "0", "created_at": ""},
            {"campaign_id": "c6", "name": "B", "type": "telegram",
             "target_segment": "VIP", "start_date": "", "end_date": "",
             "status": "draft", "budget_krw": "0", "spent_krw": "0", "created_at": ""},
        ]
        ws = _mock_ws(campaigns)
        with patch('src.marketing.campaign_manager.open_sheet', return_value=ws):
            result = manager.get_campaigns()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_get_campaigns_with_status_filter(self, manager):
        """status 필터를 사용하면 해당 상태의 캠페인만 반환해야 한다."""
        campaigns = [
            {"campaign_id": "c7", "status": "active", "name": "", "type": "",
             "target_segment": "", "start_date": "", "end_date": "",
             "budget_krw": "0", "spent_krw": "0", "created_at": ""},
            {"campaign_id": "c8", "status": "draft", "name": "", "type": "",
             "target_segment": "", "start_date": "", "end_date": "",
             "budget_krw": "0", "spent_krw": "0", "created_at": ""},
        ]
        ws = _mock_ws(campaigns)
        with patch('src.marketing.campaign_manager.open_sheet', return_value=ws):
            result = manager.get_campaigns(status="active")
        assert all(c["status"] == "active" for c in result)
