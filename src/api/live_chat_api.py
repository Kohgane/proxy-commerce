"""src/api/live_chat_api.py — 실시간 채팅 고객 지원 API Blueprint (Phase 107).

Blueprint: /api/v1/live-chat

엔드포인트:
  POST /sessions                       — 채팅 세션 생성
  GET  /sessions                       — 세션 목록
  GET  /sessions/<session_id>          — 세션 상세
  POST /sessions/<session_id>/messages — 메시지 전송
  GET  /sessions/<session_id>/messages — 메시지 이력
  POST /sessions/<session_id>/close    — 세션 종료
  POST /sessions/<session_id>/rate     — 만족도 평가
  POST /sessions/<session_id>/transfer — 상담원 이관
  GET  /agents                         — 상담원 목록
  POST /agents/<agent_id>/status       — 상담원 상태 변경
  GET  /agents/<agent_id>/stats        — 상담원 통계
  GET  /queue                          — 대기열 현황
  GET  /faq                            — FAQ 목록
  POST /faq                            — FAQ 추가
  GET  /analytics                      — 분석 데이터
  GET  /dashboard                      — 실시간 대시보드
"""
from __future__ import annotations

import logging
import uuid

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

live_chat_bp = Blueprint(
    'live_chat',
    __name__,
    url_prefix='/api/v1/live-chat',
)

# ── 지연 초기화 ───────────────────────────────────────────────────────────────
_engine = None
_ws_manager = None
_assignment_service = None
_auto_reply = None
_history_manager = None
_notification_service = None
_analytics = None


def _get_engine():
    global _engine
    if _engine is None:
        from ..live_chat.engine import ChatEngine
        _engine = ChatEngine()
    return _engine


def _get_ws_manager():
    global _ws_manager
    if _ws_manager is None:
        from ..live_chat.websocket_manager import WebSocketManager
        _ws_manager = WebSocketManager()
    return _ws_manager


def _get_assignment():
    global _assignment_service
    if _assignment_service is None:
        from ..live_chat.agent_assignment import AgentAssignmentService
        _assignment_service = AgentAssignmentService()
    return _assignment_service


def _get_auto_reply():
    global _auto_reply
    if _auto_reply is None:
        from ..live_chat.auto_reply import AutoReplyService
        _auto_reply = AutoReplyService()
    return _auto_reply


def _get_history():
    global _history_manager
    if _history_manager is None:
        from ..live_chat.history import ChatHistoryManager
        _history_manager = ChatHistoryManager()
    return _history_manager


def _get_notification():
    global _notification_service
    if _notification_service is None:
        from ..live_chat.notification import ChatNotificationService
        _notification_service = ChatNotificationService()
    return _notification_service


def _get_analytics():
    global _analytics
    if _analytics is None:
        from ..live_chat.analytics import ChatAnalytics
        _analytics = ChatAnalytics()
    return _analytics


# ── 세션 엔드포인트 ────────────────────────────────────────────────────────────

@live_chat_bp.post('/sessions')
def create_session():
    """채팅 세션 생성."""
    data = request.get_json(silent=True) or {}
    customer_id = data.get('customer_id', str(uuid.uuid4()))
    channel = data.get('channel', 'web')
    tags = data.get('tags', [])
    is_vip = bool(data.get('is_vip', False))

    engine = _get_engine()
    session = engine.create_session(customer_id=customer_id, channel=channel, tags=tags)

    # 자동 상담원 배정 시도
    assignment = _get_assignment()
    agent = assignment.assign(
        session_id=session.session_id,
        customer_id=customer_id,
        tags=tags,
        is_vip=is_vip,
    )
    if agent:
        engine.assign_agent(session.session_id, agent.agent_id)
        notif = _get_notification()
        notif.notify_agent_assigned(customer_id, agent.name, session.session_id)
        notif.notify_new_session(agent.agent_id, session.session_id, customer_id)
    else:
        notif = _get_notification()
        queue = assignment.get_queue()
        wait_pos = assignment.get_wait_position(session.session_id)
        notif.notify_wait_time(customer_id, wait_pos * 120)

    # 자동 응답 체크
    auto_reply = _get_auto_reply()
    if not auto_reply.is_business_hours():
        notif = _get_notification()
        notif.notify_off_hours(customer_id, session.session_id)

    return jsonify(session.to_dict()), 201


@live_chat_bp.get('/sessions')
def list_sessions():
    """세션 목록 조회."""
    from ..live_chat.engine import ChatSessionStatus
    status_str = request.args.get('status')
    customer_id = request.args.get('customer_id')
    status = None
    if status_str:
        try:
            status = ChatSessionStatus(status_str)
        except ValueError:
            return jsonify({'error': f'invalid status: {status_str}'}), 400

    sessions = _get_engine().list_sessions(status=status, customer_id=customer_id)
    return jsonify([s.to_dict() for s in sessions])


@live_chat_bp.get('/sessions/<session_id>')
def get_session(session_id):
    """세션 상세 조회."""
    session = _get_engine().get_session(session_id)
    if not session:
        return jsonify({'error': 'session not found'}), 404
    return jsonify(session.to_dict())


@live_chat_bp.post('/sessions/<session_id>/messages')
def send_message(session_id):
    """메시지 전송."""
    from ..live_chat.engine import SenderType, MessageType
    session = _get_engine().get_session(session_id)
    if not session:
        return jsonify({'error': 'session not found'}), 404

    data = request.get_json(silent=True) or {}
    sender_type_str = data.get('sender_type', 'customer')
    sender_id = data.get('sender_id', 'unknown')
    content = data.get('content', '')
    message_type_str = data.get('message_type', 'text')

    if not content:
        return jsonify({'error': 'content is required'}), 400

    try:
        sender_type = SenderType(sender_type_str)
        message_type = MessageType(message_type_str)
    except ValueError:
        return jsonify({'error': 'invalid sender_type or message_type'}), 400

    engine = _get_engine()
    msg = engine.send_message(
        session_id=session_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=content,
        message_type=message_type,
        metadata=data.get('metadata', {}),
    )
    if not msg:
        return jsonify({'error': 'cannot send message to closed/resolved session'}), 409

    # 고객 메시지일 경우 자동 응답 시도
    if sender_type == SenderType.customer and not session.agent_id:
        auto_reply = _get_auto_reply()
        faq, quick_replies, needs_agent = auto_reply.get_reply(content)
        if faq:
            engine.send_message(
                session_id=session_id,
                sender_type=SenderType.bot,
                sender_id='bot',
                content=faq.answer,
                message_type=MessageType.auto_reply,
                metadata={'faq_id': faq.faq_id, 'category': faq.category},
            )

    # WebSocket 유니캐스트 (mock)
    ws = _get_ws_manager()
    ws.unicast(sender_id, 'message', msg.to_dict())

    return jsonify(msg.to_dict()), 201


@live_chat_bp.get('/sessions/<session_id>/messages')
def get_messages(session_id):
    """메시지 이력 조회."""
    session = _get_engine().get_session(session_id)
    if not session:
        return jsonify({'error': 'session not found'}), 404
    messages = _get_engine().get_messages(session_id)
    return jsonify([m.to_dict() for m in messages])


@live_chat_bp.post('/sessions/<session_id>/close')
def close_session(session_id):
    """세션 종료."""
    data = request.get_json(silent=True) or {}
    resolution = data.get('resolution', '')
    engine = _get_engine()
    session = engine.close_session(session_id, resolution=resolution)
    if not session:
        return jsonify({'error': 'session not found'}), 404

    # 상담원 세션 해제
    if session.agent_id:
        _get_assignment().release(session.agent_id)

    # 만족도 조사 요청
    _get_notification().request_rating(session.customer_id, session_id)

    # 이력 저장
    history = _get_history()
    history.save_session(
        session.to_dict(),
        [m.to_dict() for m in session.messages],
    )

    # 분석 기록
    analytics = _get_analytics()
    analytics.record_session(session.to_dict())

    return jsonify(session.to_dict())


@live_chat_bp.post('/sessions/<session_id>/rate')
def rate_session(session_id):
    """만족도 평가."""
    data = request.get_json(silent=True) or {}
    rating = data.get('rating')
    if rating is None:
        return jsonify({'error': 'rating is required'}), 400
    try:
        session = _get_engine().rate_session(session_id, int(rating))
    except (ValueError, TypeError):
        return jsonify({'error': 'rating must be an integer between 1 and 5'}), 400
    if not session:
        return jsonify({'error': 'session not found'}), 404
    return jsonify(session.to_dict())


@live_chat_bp.post('/sessions/<session_id>/transfer')
def transfer_session(session_id):
    """상담원 이관."""
    data = request.get_json(silent=True) or {}
    new_agent_id = data.get('agent_id')
    if not new_agent_id:
        return jsonify({'error': 'agent_id is required'}), 400

    engine = _get_engine()
    session = engine.get_session(session_id)
    if not session:
        return jsonify({'error': 'session not found'}), 404

    old_agent_id = session.agent_id
    if old_agent_id:
        _get_assignment().release(old_agent_id)

    new_agent = _get_assignment().get_agent(new_agent_id)
    if not new_agent:
        return jsonify({'error': 'agent not found'}), 404

    session = engine.transfer_session(session_id, new_agent_id)
    new_agent.current_sessions += 1
    return jsonify(session.to_dict())


# ── 상담원 엔드포인트 ──────────────────────────────────────────────────────────

@live_chat_bp.get('/agents')
def list_agents():
    """상담원 목록."""
    from ..live_chat.agent_assignment import AgentStatus
    status_str = request.args.get('status')
    status = None
    if status_str:
        try:
            status = AgentStatus(status_str)
        except ValueError:
            return jsonify({'error': f'invalid status: {status_str}'}), 400
    agents = _get_assignment().list_agents(status=status)
    return jsonify([a.to_dict() for a in agents])


@live_chat_bp.post('/agents/<agent_id>/status')
def update_agent_status(agent_id):
    """상담원 상태 변경."""
    from ..live_chat.agent_assignment import AgentStatus
    data = request.get_json(silent=True) or {}
    status_str = data.get('status')
    if not status_str:
        return jsonify({'error': 'status is required'}), 400
    try:
        status = AgentStatus(status_str)
    except ValueError:
        return jsonify({'error': f'invalid status: {status_str}'}), 400
    agent = _get_assignment().update_agent_status(agent_id, status)
    if not agent:
        return jsonify({'error': 'agent not found'}), 404
    return jsonify(agent.to_dict())


@live_chat_bp.get('/agents/<agent_id>/stats')
def get_agent_stats(agent_id):
    """상담원 통계."""
    stats = _get_assignment().get_agent_stats(agent_id)
    if not stats:
        return jsonify({'error': 'agent not found'}), 404
    return jsonify(stats)


# ── 대기열 엔드포인트 ──────────────────────────────────────────────────────────

@live_chat_bp.get('/queue')
def get_queue():
    """대기열 현황."""
    assignment = _get_assignment()
    queue = assignment.get_queue()
    stats = assignment.get_stats()
    return jsonify({
        'queue': [e.to_dict() for e in queue],
        'queue_length': len(queue),
        'agent_stats': stats,
    })


# ── FAQ 엔드포인트 ─────────────────────────────────────────────────────────────

@live_chat_bp.get('/faq')
def list_faq():
    """FAQ 목록."""
    category = request.args.get('category')
    faqs = _get_auto_reply().list_faqs(category=category)
    return jsonify([f.to_dict() for f in faqs])


@live_chat_bp.post('/faq')
def add_faq():
    """FAQ 추가."""
    from ..live_chat.auto_reply import FAQEntry
    data = request.get_json(silent=True) or {}
    required = ['faq_id', 'keywords', 'question', 'answer']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    faq = FAQEntry(
        faq_id=data['faq_id'],
        keywords=data['keywords'],
        question=data['question'],
        answer=data['answer'],
        category=data.get('category', '기타'),
    )
    result = _get_auto_reply().add_faq(faq)
    return jsonify(result.to_dict()), 201


# ── 분석 엔드포인트 ────────────────────────────────────────────────────────────

@live_chat_bp.get('/analytics')
def get_analytics():
    """분석 데이터."""
    analytics = _get_analytics()
    engine = _get_engine()
    assignment = _get_assignment()
    stats = engine.get_stats()
    agent_stats = assignment.get_stats()
    return jsonify({
        'session_stats': stats,
        'performance': analytics.get_performance_metrics(),
        'agent_performance': analytics.get_agent_performance(),
        'category_analysis': analytics.get_category_analysis(),
        'peak_hours': analytics.get_peak_hours(),
        'agent_stats': agent_stats,
        'faq_stats': _get_auto_reply().get_stats(),
        'notification_stats': _get_notification().get_stats(),
        'ws_status': _get_ws_manager().get_status(),
        'history_stats': _get_history().get_stats(),
    })


@live_chat_bp.get('/dashboard')
def get_dashboard():
    """실시간 대시보드."""
    engine = _get_engine()
    assignment = _get_assignment()
    analytics = _get_analytics()
    ws = _get_ws_manager()

    active_sessions = len(engine.list_sessions())
    queue = assignment.get_queue()
    ws_status = ws.get_status()
    online_agents = ws_status.get('online_agents', 0)

    return jsonify(
        analytics.get_dashboard(
            active_sessions=active_sessions,
            waiting_customers=len(queue),
            online_agents=online_agents,
        )
    )
