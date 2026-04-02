"""tests/test_customer_service.py — Customer Service System tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from flask import Flask

from src.customer_service.auto_responder import AutoResponder
from src.customer_service.escalation import EscalationRule
from src.customer_service.models import TicketPriority, TicketStatus
from src.customer_service.ticket_manager import TicketManager


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def manager():
    return TicketManager()


@pytest.fixture
def sample_ticket(manager):
    return manager.create('cust_1', '배송 문의', '주문 후 3일이 지났는데 아직 배송이 안 됩니다.')


@pytest.fixture
def flask_client():
    from src.api.cs_api import cs_api, _manager
    # Reset manager state for each test
    _manager._tickets.clear()

    app = Flask(__name__)
    app.register_blueprint(cs_api)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


# ──────────────────────────────────────────────────────────
# TicketManager tests
# ──────────────────────────────────────────────────────────

def test_ticket_create(manager):
    ticket = manager.create('cust_1', '환불 요청', '상품이 불량입니다.', priority='high')
    assert ticket.id
    assert ticket.customer_id == 'cust_1'
    assert ticket.subject == '환불 요청'
    assert ticket.status == TicketStatus.open
    assert ticket.priority == TicketPriority.high
    assert ticket.assigned_to is None
    assert ticket.messages == []


def test_ticket_get(manager, sample_ticket):
    found = manager.get(sample_ticket.id)
    assert found is not None
    assert found.id == sample_ticket.id


def test_ticket_get_missing(manager):
    assert manager.get('nonexistent') is None


def test_ticket_list(manager):
    manager.create('cust_1', 'A', '', priority='normal')
    manager.create('cust_2', 'B', '', priority='high')
    tickets = manager.list_tickets()
    assert len(tickets) == 2


def test_ticket_list_filter_status(manager):
    t = manager.create('cust_1', 'A', '')
    manager.update_status(t.id, 'resolved')
    manager.create('cust_2', 'B', '')

    open_tickets = manager.list_tickets(status='open')
    resolved_tickets = manager.list_tickets(status='resolved')
    assert len(open_tickets) == 1
    assert len(resolved_tickets) == 1


def test_ticket_update_status(manager, sample_ticket):
    updated = manager.update_status(sample_ticket.id, 'in_progress')
    assert updated is not None
    assert updated.status == TicketStatus.in_progress


def test_ticket_assign(manager, sample_ticket):
    result = manager.assign(sample_ticket.id, 'agent_007')
    assert result is not None
    assert result.assigned_to == 'agent_007'


def test_ticket_add_message(manager, sample_ticket):
    msg = manager.add_message(sample_ticket.id, sender='agent', content='확인 중입니다.')
    assert msg is not None
    assert msg.ticket_id == sample_ticket.id
    assert msg.content == '확인 중입니다.'
    assert msg.is_auto is False
    assert len(manager.get(sample_ticket.id).messages) == 1


def test_ticket_close(manager, sample_ticket):
    closed = manager.close(sample_ticket.id)
    assert closed is not None
    assert closed.status == TicketStatus.closed


# ──────────────────────────────────────────────────────────
# AutoResponder tests
# ──────────────────────────────────────────────────────────

def test_auto_responder_match():
    ar = AutoResponder()
    result = ar.suggest('배송이 언제 되나요?')
    assert result is not None
    assert '배송' in result or '출고' in result


def test_auto_responder_no_match():
    ar = AutoResponder()
    result = ar.suggest('xyzzy unknown query')
    assert result is None


def test_auto_responder_add_faq():
    ar = AutoResponder()
    ar.add_faq('테스트키워드', '테스트 응답입니다.')
    result = ar.suggest('테스트키워드 관련 문의')
    assert result == '테스트 응답입니다.'


# ──────────────────────────────────────────────────────────
# EscalationRule tests
# ──────────────────────────────────────────────────────────

def test_escalation_sla_ok(manager):
    ticket = manager.create('cust_1', '문의', '')
    rule = EscalationRule()
    assert rule.check_sla(ticket) is None


def test_escalation_sla_alert(manager):
    ticket = manager.create('cust_1', '문의', '')
    ticket.updated_at = datetime.utcnow() - timedelta(hours=25)
    rule = EscalationRule()
    assert rule.check_sla(ticket) == 'alert'


def test_escalation_sla_escalate(manager):
    ticket = manager.create('cust_1', '문의', '')
    ticket.updated_at = datetime.utcnow() - timedelta(hours=49)
    rule = EscalationRule()
    assert rule.check_sla(ticket) == 'escalate'


def test_escalation_get_overdue_tickets(manager):
    t1 = manager.create('cust_1', 'A', '')  # ok
    t2 = manager.create('cust_2', 'B', '')
    t2.updated_at = datetime.utcnow() - timedelta(hours=30)  # alert
    t3 = manager.create('cust_3', 'C', '')
    t3.updated_at = datetime.utcnow() - timedelta(hours=55)  # escalate

    rule = EscalationRule()
    overdue = rule.get_overdue_tickets([t1, t2, t3])
    assert len(overdue) == 2
    statuses = {o['sla_status'] for o in overdue}
    assert 'alert' in statuses
    assert 'escalate' in statuses


# ──────────────────────────────────────────────────────────
# CS API tests
# ──────────────────────────────────────────────────────────

def test_cs_api_status(flask_client):
    resp = flask_client.get('/api/v1/cs/status')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'


def test_cs_api_create_ticket(flask_client):
    resp = flask_client.post('/api/v1/cs/tickets', json={
        'customer_id': 'cust_1',
        'subject': '배송 문의',
        'description': '배송이 늦습니다.',
        'priority': 'high',
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['subject'] == '배송 문의'
    assert data['priority'] == 'high'
    assert data['status'] == 'open'


def test_cs_api_create_ticket_missing_fields(flask_client):
    resp = flask_client.post('/api/v1/cs/tickets', json={'customer_id': 'cust_1'})
    assert resp.status_code == 400


def test_cs_api_list_tickets(flask_client):
    flask_client.post('/api/v1/cs/tickets', json={
        'customer_id': 'cust_1', 'subject': 'A', 'description': ''
    })
    flask_client.post('/api/v1/cs/tickets', json={
        'customer_id': 'cust_2', 'subject': 'B', 'description': ''
    })
    resp = flask_client.get('/api/v1/cs/tickets')
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2


def test_cs_api_get_ticket(flask_client):
    create_resp = flask_client.post('/api/v1/cs/tickets', json={
        'customer_id': 'cust_1', 'subject': 'Test', 'description': 'desc'
    })
    ticket_id = create_resp.get_json()['id']

    resp = flask_client.get(f'/api/v1/cs/tickets/{ticket_id}')
    assert resp.status_code == 200
    assert resp.get_json()['id'] == ticket_id


def test_cs_api_get_ticket_not_found(flask_client):
    resp = flask_client.get('/api/v1/cs/tickets/nonexistent')
    assert resp.status_code == 404
