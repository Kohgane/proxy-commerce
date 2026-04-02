"""src/api/cs_api.py — Customer Service REST API blueprint."""

from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, jsonify, request

from ..customer_service.ticket_manager import TicketManager

cs_api = Blueprint('cs_api', __name__, url_prefix='/api/v1/cs')

_manager = TicketManager()


def _ticket_dict(ticket) -> dict:
    d = asdict(ticket)
    d['status'] = ticket.status.value
    d['priority'] = ticket.priority.value
    return d


@cs_api.get('/status')
def cs_status():
    return jsonify({'module': 'customer_service', 'status': 'ok'})


@cs_api.post('/tickets')
def create_ticket():
    body = request.get_json(silent=True) or {}
    customer_id = body.get('customer_id', '')
    subject = body.get('subject', '')
    description = body.get('description', '')
    priority = body.get('priority', 'normal')

    if not customer_id or not subject:
        return jsonify({'error': 'customer_id and subject are required'}), 400

    ticket = _manager.create(customer_id, subject, description, priority)
    return jsonify(_ticket_dict(ticket)), 201


@cs_api.get('/tickets')
def list_tickets():
    status_filter = request.args.get('status')
    tickets = _manager.list_tickets(status=status_filter)
    return jsonify([_ticket_dict(t) for t in tickets])


@cs_api.get('/tickets/<ticket_id>')
def get_ticket(ticket_id: str):
    ticket = _manager.get(ticket_id)
    if ticket is None:
        return jsonify({'error': 'Ticket not found'}), 404
    return jsonify(_ticket_dict(ticket))


@cs_api.post('/tickets/<ticket_id>/reply')
def add_reply(ticket_id: str):
    body = request.get_json(silent=True) or {}
    sender = body.get('sender', '')
    content = body.get('content', '')

    if not sender or not content:
        return jsonify({'error': 'sender and content are required'}), 400

    msg = _manager.add_message(ticket_id, sender, content)
    if msg is None:
        return jsonify({'error': 'Ticket not found'}), 404
    return jsonify(asdict(msg)), 201


@cs_api.put('/tickets/<ticket_id>/status')
def update_status(ticket_id: str):
    body = request.get_json(silent=True) or {}
    status = body.get('status', '')
    if not status:
        return jsonify({'error': 'status is required'}), 400

    ticket = _manager.update_status(ticket_id, status)
    if ticket is None:
        return jsonify({'error': 'Ticket not found'}), 404
    return jsonify(_ticket_dict(ticket))
