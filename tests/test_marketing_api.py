"""tests/test_marketing_api.py — 마케팅 API 엔드포인트 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def api_client(mock_env, monkeypatch):
    """marketing_bp가 등록된 Flask 테스트 클라이언트."""
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    with wh.app.test_client() as c:
        yield c


SAMPLE_CAMPAIGNS = [
    {
        "campaign_id": "c1", "name": "테스트 캠페인", "type": "email",
        "target_segment": "VIP", "start_date": "2026-01-01", "end_date": "2026-01-31",
        "status": "active", "budget_krw": "100000", "spent_krw": "30000",
        "created_at": "2026-01-01T00:00:00",
    },
]

SAMPLE_CAMPAIGN = SAMPLE_CAMPAIGNS[0]


class TestGetCampaigns:
    def test_get_campaigns_returns_200(self, api_client):
        """GET /api/marketing/campaigns는 200을 반환해야 한다."""
        with patch('src.marketing.campaign_manager.CampaignManager.get_campaigns',
                   return_value=SAMPLE_CAMPAIGNS):
            resp = api_client.get('/api/marketing/campaigns')
        assert resp.status_code == 200
        data = resp.get_json()
        assert "campaigns" in data


class TestCreateCampaign:
    def test_create_campaign_returns_201(self, api_client):
        """POST /api/marketing/campaigns는 201을 반환해야 한다."""
        with patch('src.marketing.campaign_manager.CampaignManager.create_campaign',
                   return_value=SAMPLE_CAMPAIGN):
            resp = api_client.post('/api/marketing/campaigns', json={
                "name": "신규 캠페인",
                "type": "email",
            })
        assert resp.status_code == 201
        data = resp.get_json()
        assert "campaign" in data


class TestPatchCampaignStatus:
    def test_patch_campaign_pause(self, api_client):
        """PATCH /api/marketing/campaigns/<id>로 상태를 변경할 수 있어야 한다."""
        paused = {**SAMPLE_CAMPAIGN, "status": "paused"}
        with patch('src.marketing.campaign_manager.CampaignManager.pause_campaign',
                   return_value=paused):
            resp = api_client.patch('/api/marketing/campaigns/c1', json={"action": "pause"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["campaign"]["status"] == "paused"

    def test_patch_campaign_not_found(self, api_client):
        """존재하지 않는 캠페인은 404를 반환해야 한다."""
        with patch('src.marketing.campaign_manager.CampaignManager.pause_campaign',
                   return_value=None):
            resp = api_client.patch('/api/marketing/campaigns/nonexistent', json={"action": "pause"})
        assert resp.status_code == 404


class TestGetAbTests:
    def test_get_ab_tests_returns_200(self, api_client):
        """GET /api/marketing/ab-tests는 200을 반환해야 한다."""
        with patch('src.marketing.ab_testing.ABTestManager.get_results', return_value={}):
            resp = api_client.get('/api/marketing/ab-tests?experiment=test_exp')
        assert resp.status_code == 200


class TestPostAbTest:
    def test_post_ab_test_get_variant(self, api_client):
        """POST /api/marketing/ab-tests로 변형을 조회할 수 있어야 한다."""
        with patch('src.marketing.ab_testing.ABTestManager.get_variant', return_value='A'):
            resp = api_client.post('/api/marketing/ab-tests', json={
                "experiment_name": "exp1",
                "customer_email": "user@example.com",
                "action": "variant",
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "variant" in data

    def test_post_ab_test_invalid_action(self, api_client):
        """알 수 없는 action은 400을 반환해야 한다."""
        resp = api_client.post('/api/marketing/ab-tests', json={
            "experiment_name": "exp1",
            "customer_email": "user@example.com",
            "action": "invalid_action",
        })
        assert resp.status_code == 400
