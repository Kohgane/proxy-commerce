"""tests/test_live_chat.py — Phase 107: 실시간 채팅 고객 지원 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── ChatSessionStatus ────────────────────────────────────────────────────────

class TestChatSessionStatus:
    def test_values(self):
        from src.live_chat.engine import ChatSessionStatus
        assert ChatSessionStatus.waiting == 'waiting'
        assert ChatSessionStatus.assigned == 'assigned'
        assert ChatSessionStatus.active == 'active'
        assert ChatSessionStatus.on_hold == 'on_hold'
        assert ChatSessionStatus.resolved == 'resolved'
        assert ChatSessionStatus.closed == 'closed'

    def test_is_str(self):
        from src.live_chat.engine import ChatSessionStatus
        assert isinstance(ChatSessionStatus.waiting, str)


# ─── MessageType ──────────────────────────────────────────────────────────────

class TestMessageType:
    def test_values(self):
        from src.live_chat.engine import MessageType
        assert MessageType.text == 'text'
        assert MessageType.image == 'image'
        assert MessageType.file == 'file'
        assert MessageType.system == 'system'
        assert MessageType.auto_reply == 'auto_reply'
        assert MessageType.quick_reply == 'quick_reply'


# ─── SenderType ───────────────────────────────────────────────────────────────

class TestSenderType:
    def test_values(self):
        from src.live_chat.engine import SenderType
        assert SenderType.customer == 'customer'
        assert SenderType.agent == 'agent'
        assert SenderType.bot == 'bot'
        assert SenderType.system == 'system'


# ─── ChatMessage ──────────────────────────────────────────────────────────────

class TestChatMessage:
    def _make(self):
        from src.live_chat.engine import ChatMessage, SenderType, MessageType
        return ChatMessage(
            message_id='msg-001',
            session_id='sess-001',
            sender_type=SenderType.customer,
            sender_id='cust-001',
            content='안녕하세요',
        )

    def test_create(self):
        msg = self._make()
        assert msg.message_id == 'msg-001'
        assert msg.session_id == 'sess-001'
        assert msg.content == '안녕하세요'

    def test_timestamp_auto_set(self):
        msg = self._make()
        assert msg.timestamp != ''
        assert 'T' in msg.timestamp

    def test_to_dict_keys(self):
        msg = self._make()
        d = msg.to_dict()
        assert 'message_id' in d
        assert 'session_id' in d
        assert 'sender_type' in d
        assert 'sender_id' in d
        assert 'content' in d
        assert 'message_type' in d
        assert 'timestamp' in d
        assert 'metadata' in d

    def test_to_dict_values(self):
        msg = self._make()
        d = msg.to_dict()
        assert d['sender_type'] == 'customer'
        assert d['message_type'] == 'text'
        assert d['content'] == '안녕하세요'


# ─── ChatSession ──────────────────────────────────────────────────────────────

class TestChatSession:
    def _make(self):
        from src.live_chat.engine import ChatSession
        return ChatSession(
            session_id='sess-001',
            customer_id='cust-001',
        )

    def test_create(self):
        s = self._make()
        assert s.session_id == 'sess-001'
        assert s.customer_id == 'cust-001'

    def test_default_status(self):
        from src.live_chat.engine import ChatSessionStatus
        s = self._make()
        assert s.status == ChatSessionStatus.waiting

    def test_started_at_auto_set(self):
        s = self._make()
        assert s.started_at != ''

    def test_to_dict_keys(self):
        s = self._make()
        d = s.to_dict()
        for key in ['session_id', 'customer_id', 'agent_id', 'status',
                    'channel', 'started_at', 'ended_at', 'message_count',
                    'rating', 'tags']:
            assert key in d

    def test_to_dict_status_string(self):
        s = self._make()
        d = s.to_dict()
        assert d['status'] == 'waiting'


# ─── ChatEngine ───────────────────────────────────────────────────────────────

class TestChatEngine:
    def _engine(self):
        from src.live_chat.engine import ChatEngine
        return ChatEngine()

    def test_create_session(self):
        from src.live_chat.engine import ChatSessionStatus
        engine = self._engine()
        session = engine.create_session('cust-001')
        assert session.customer_id == 'cust-001'
        assert session.status == ChatSessionStatus.waiting
        assert len(session.messages) == 1  # system message

    def test_create_session_with_channel(self):
        engine = self._engine()
        session = engine.create_session('cust-001', channel='mobile')
        assert session.channel == 'mobile'

    def test_create_session_with_tags(self):
        engine = self._engine()
        session = engine.create_session('cust-001', tags=['배송조회'])
        assert '배송조회' in session.tags

    def test_get_session(self):
        engine = self._engine()
        s = engine.create_session('cust-001')
        found = engine.get_session(s.session_id)
        assert found is not None
        assert found.session_id == s.session_id

    def test_get_session_not_found(self):
        engine = self._engine()
        assert engine.get_session('nonexistent') is None

    def test_list_sessions(self):
        engine = self._engine()
        engine.create_session('cust-001')
        engine.create_session('cust-002')
        sessions = engine.list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_by_status(self):
        from src.live_chat.engine import ChatSessionStatus
        engine = self._engine()
        s1 = engine.create_session('cust-001')
        s2 = engine.create_session('cust-002')
        engine.assign_agent(s2.session_id, 'agent-001')
        waiting = engine.list_sessions(status=ChatSessionStatus.waiting)
        assert len(waiting) == 1
        assert waiting[0].session_id == s1.session_id

    def test_list_sessions_by_customer(self):
        engine = self._engine()
        engine.create_session('cust-001')
        engine.create_session('cust-001')
        engine.create_session('cust-002')
        mine = engine.list_sessions(customer_id='cust-001')
        assert len(mine) == 2

    def test_assign_agent(self):
        from src.live_chat.engine import ChatSessionStatus
        engine = self._engine()
        s = engine.create_session('cust-001')
        updated = engine.assign_agent(s.session_id, 'agent-001')
        assert updated.agent_id == 'agent-001'
        assert updated.status == ChatSessionStatus.assigned

    def test_assign_agent_not_found(self):
        engine = self._engine()
        result = engine.assign_agent('nonexistent', 'agent-001')
        assert result is None

    def test_hold_session(self):
        from src.live_chat.engine import ChatSessionStatus
        engine = self._engine()
        s = engine.create_session('cust-001')
        updated = engine.hold_session(s.session_id)
        assert updated.status == ChatSessionStatus.on_hold

    def test_close_session(self):
        from src.live_chat.engine import ChatSessionStatus
        engine = self._engine()
        s = engine.create_session('cust-001')
        closed = engine.close_session(s.session_id)
        assert closed.status == ChatSessionStatus.closed
        assert closed.ended_at is not None

    def test_close_session_with_resolution(self):
        engine = self._engine()
        s = engine.create_session('cust-001')
        closed = engine.close_session(s.session_id, resolution='문의 해결')
        assert closed.status.value == 'closed'

    def test_resolve_session(self):
        from src.live_chat.engine import ChatSessionStatus
        engine = self._engine()
        s = engine.create_session('cust-001')
        resolved = engine.resolve_session(s.session_id)
        assert resolved.status == ChatSessionStatus.resolved

    def test_rate_session(self):
        engine = self._engine()
        s = engine.create_session('cust-001')
        rated = engine.rate_session(s.session_id, 5)
        assert rated.rating == 5

    def test_rate_session_invalid(self):
        engine = self._engine()
        s = engine.create_session('cust-001')
        with pytest.raises(ValueError):
            engine.rate_session(s.session_id, 6)

    def test_send_message(self):
        from src.live_chat.engine import SenderType
        engine = self._engine()
        s = engine.create_session('cust-001')
        engine.assign_agent(s.session_id, 'agent-001')
        msg = engine.send_message(
            session_id=s.session_id,
            sender_type=SenderType.customer,
            sender_id='cust-001',
            content='배송 문의드립니다',
        )
        assert msg is not None
        assert msg.content == '배송 문의드립니다'

    def test_send_message_to_closed_session(self):
        from src.live_chat.engine import SenderType
        engine = self._engine()
        s = engine.create_session('cust-001')
        engine.close_session(s.session_id)
        msg = engine.send_message(
            session_id=s.session_id,
            sender_type=SenderType.customer,
            sender_id='cust-001',
            content='test',
        )
        assert msg is None

    def test_send_message_not_found(self):
        from src.live_chat.engine import SenderType
        engine = self._engine()
        msg = engine.send_message(
            session_id='nonexistent',
            sender_type=SenderType.customer,
            sender_id='cust-001',
            content='test',
        )
        assert msg is None

    def test_get_messages(self):
        from src.live_chat.engine import SenderType
        engine = self._engine()
        s = engine.create_session('cust-001')
        engine.assign_agent(s.session_id, 'agent-001')
        engine.send_message(s.session_id, SenderType.customer, 'cust-001', '문의')
        messages = engine.get_messages(s.session_id)
        assert len(messages) >= 2  # system + customer

    def test_transfer_session(self):
        from src.live_chat.engine import ChatSessionStatus
        engine = self._engine()
        s = engine.create_session('cust-001')
        engine.assign_agent(s.session_id, 'agent-001')
        transferred = engine.transfer_session(s.session_id, 'agent-002')
        assert transferred.agent_id == 'agent-002'
        assert transferred.status == ChatSessionStatus.assigned

    def test_activate_session(self):
        from src.live_chat.engine import ChatSessionStatus
        engine = self._engine()
        s = engine.create_session('cust-001')
        engine.assign_agent(s.session_id, 'agent-001')
        activated = engine.activate_session(s.session_id)
        assert activated.status == ChatSessionStatus.active

    def test_get_stats(self):
        engine = self._engine()
        engine.create_session('cust-001')
        engine.create_session('cust-002')
        stats = engine.get_stats()
        assert stats['total_sessions'] == 2
        assert 'by_status' in stats
        assert 'average_rating' in stats

    def test_get_stats_with_ratings(self):
        engine = self._engine()
        s1 = engine.create_session('cust-001')
        s2 = engine.create_session('cust-002')
        engine.rate_session(s1.session_id, 4)
        engine.rate_session(s2.session_id, 5)
        stats = engine.get_stats()
        assert stats['average_rating'] == 4.5
        assert stats['rated_sessions'] == 2

    def test_message_activates_assigned_session(self):
        from src.live_chat.engine import SenderType, ChatSessionStatus
        engine = self._engine()
        s = engine.create_session('cust-001')
        engine.assign_agent(s.session_id, 'agent-001')
        assert s.status == ChatSessionStatus.assigned
        engine.send_message(s.session_id, SenderType.customer, 'cust-001', 'hello')
        assert s.status == ChatSessionStatus.active


# ─── WebSocketManager ─────────────────────────────────────────────────────────

class TestWebSocketManager:
    def _ws(self):
        from src.live_chat.websocket_manager import WebSocketManager
        return WebSocketManager()

    def test_connect(self):
        ws = self._ws()
        conn = ws.connect('user-001', 'customer')
        assert conn.user_id == 'user-001'
        assert conn.user_type == 'customer'
        assert conn.connection_id != ''

    def test_connect_sets_timestamps(self):
        ws = self._ws()
        conn = ws.connect('user-001', 'customer')
        assert conn.connected_at != ''
        assert conn.last_ping != ''

    def test_disconnect(self):
        ws = self._ws()
        conn = ws.connect('user-001', 'customer')
        result = ws.disconnect(conn.connection_id)
        assert result is True
        assert ws.get_connection(conn.connection_id) is None

    def test_disconnect_not_found(self):
        ws = self._ws()
        result = ws.disconnect('nonexistent')
        assert result is False

    def test_reconnect(self):
        ws = self._ws()
        ws.connect('user-001', 'customer')
        ws.connect('user-001', 'customer')
        new_conn = ws.reconnect('user-001', 'customer')
        # 이전 연결 해제 후 새 연결
        user_conns = ws.get_user_connections('user-001')
        assert len(user_conns) == 1
        assert user_conns[0].connection_id == new_conn.connection_id

    def test_get_connection(self):
        ws = self._ws()
        conn = ws.connect('user-001', 'customer')
        found = ws.get_connection(conn.connection_id)
        assert found is not None
        assert found.user_id == 'user-001'

    def test_get_user_connections(self):
        ws = self._ws()
        ws.connect('user-001', 'customer')
        ws.connect('user-001', 'customer')
        conns = ws.get_user_connections('user-001')
        assert len(conns) == 2

    def test_ping(self):
        ws = self._ws()
        conn = ws.connect('user-001', 'customer')
        old_ping = conn.last_ping
        import time
        time.sleep(0.01)
        result = ws.ping(conn.connection_id)
        assert result is True

    def test_ping_not_found(self):
        ws = self._ws()
        result = ws.ping('nonexistent')
        assert result is False

    def test_broadcast(self):
        ws = self._ws()
        ws.connect('user-001', 'customer')
        ws.connect('user-002', 'customer')
        ws.connect('agent-001', 'agent')
        count = ws.broadcast('test_event', {'msg': 'hello'})
        assert count == 3

    def test_broadcast_by_type(self):
        ws = self._ws()
        ws.connect('user-001', 'customer')
        ws.connect('user-002', 'customer')
        ws.connect('agent-001', 'agent')
        count = ws.broadcast('test_event', {'msg': 'hello'}, user_type='customer')
        assert count == 2

    def test_unicast(self):
        ws = self._ws()
        ws.connect('user-001', 'customer')
        result = ws.unicast('user-001', 'msg', {'text': 'hi'})
        assert result is True

    def test_unicast_not_connected(self):
        ws = self._ws()
        result = ws.unicast('ghost', 'msg', {'text': 'hi'})
        assert result is False

    def test_get_status(self):
        ws = self._ws()
        ws.connect('user-001', 'customer')
        ws.connect('agent-001', 'agent')
        status = ws.get_status()
        assert status['total_connections'] == 2
        assert status['online_customers'] == 1
        assert status['online_agents'] == 1

    def test_heartbeat_check(self):
        ws = self._ws()
        ws.connect('user-001', 'customer')
        timed_out = ws.check_heartbeat(timeout_seconds=60)
        assert isinstance(timed_out, list)

    def test_get_message_log(self):
        ws = self._ws()
        ws.connect('user-001', 'customer')
        ws.broadcast('event', {'data': 1})
        log = ws.get_message_log()
        assert len(log) >= 1


# ─── Connection ───────────────────────────────────────────────────────────────

class TestConnection:
    def test_create(self):
        from src.live_chat.websocket_manager import Connection
        conn = Connection(
            connection_id='conn-001',
            user_id='user-001',
            user_type='customer',
        )
        assert conn.connection_id == 'conn-001'
        assert conn.connected_at != ''

    def test_to_dict(self):
        from src.live_chat.websocket_manager import Connection
        conn = Connection(
            connection_id='conn-001',
            user_id='user-001',
            user_type='customer',
        )
        d = conn.to_dict()
        assert 'connection_id' in d
        assert 'user_id' in d
        assert 'user_type' in d
        assert 'connected_at' in d
        assert 'last_ping' in d


# ─── AgentStatus ─────────────────────────────────────────────────────────────

class TestAgentStatus:
    def test_values(self):
        from src.live_chat.agent_assignment import AgentStatus
        assert AgentStatus.online == 'online'
        assert AgentStatus.busy == 'busy'
        assert AgentStatus.away == 'away'
        assert AgentStatus.offline == 'offline'


# ─── AgentProfile ─────────────────────────────────────────────────────────────

class TestAgentProfile:
    def _make(self, status='online', current=0, max_s=5):
        from src.live_chat.agent_assignment import AgentProfile, AgentStatus
        return AgentProfile(
            agent_id='agent-001',
            name='김상담',
            status=AgentStatus(status),
            skills=['배송조회', '환불문의'],
            current_sessions=current,
            max_sessions=max_s,
            languages=['ko'],
            rating=4.8,
        )

    def test_is_available_online(self):
        agent = self._make('online', 0, 5)
        assert agent.is_available is True

    def test_is_available_full(self):
        agent = self._make('online', 5, 5)
        assert agent.is_available is False

    def test_is_available_offline(self):
        agent = self._make('offline')
        assert agent.is_available is False

    def test_load_ratio(self):
        agent = self._make('online', 2, 5)
        assert agent.load_ratio == pytest.approx(0.4)

    def test_to_dict(self):
        agent = self._make()
        d = agent.to_dict()
        assert d['agent_id'] == 'agent-001'
        assert d['name'] == '김상담'
        assert 'is_available' in d
        assert 'load_ratio' in d


# ─── AssignmentStrategy ──────────────────────────────────────────────────────

class TestRoundRobinStrategy:
    def _agents(self):
        from src.live_chat.agent_assignment import AgentProfile, AgentStatus
        return [
            AgentProfile('a1', 'Agent1', AgentStatus.online),
            AgentProfile('a2', 'Agent2', AgentStatus.online),
        ]

    def test_assign(self):
        from src.live_chat.agent_assignment import RoundRobinStrategy
        strategy = RoundRobinStrategy()
        agents = self._agents()
        a1 = strategy.assign(agents, 'cust-001')
        a2 = strategy.assign(agents, 'cust-002')
        assert a1 is not None
        assert a2 is not None
        assert a1.agent_id != a2.agent_id

    def test_no_available(self):
        from src.live_chat.agent_assignment import RoundRobinStrategy, AgentProfile, AgentStatus
        strategy = RoundRobinStrategy()
        agents = [AgentProfile('a1', 'A1', AgentStatus.offline)]
        result = strategy.assign(agents, 'cust-001')
        assert result is None


class TestLeastLoadStrategy:
    def test_assign_least_loaded(self):
        from src.live_chat.agent_assignment import LeastLoadStrategy, AgentProfile, AgentStatus
        strategy = LeastLoadStrategy()
        a1 = AgentProfile('a1', 'Agent1', AgentStatus.online, current_sessions=3, max_sessions=5)
        a2 = AgentProfile('a2', 'Agent2', AgentStatus.online, current_sessions=1, max_sessions=5)
        result = strategy.assign([a1, a2], 'cust-001')
        assert result.agent_id == 'a2'

    def test_no_available(self):
        from src.live_chat.agent_assignment import LeastLoadStrategy, AgentProfile, AgentStatus
        strategy = LeastLoadStrategy()
        agents = [AgentProfile('a1', 'A1', AgentStatus.offline)]
        result = strategy.assign(agents, 'cust-001')
        assert result is None


class TestSkillBasedStrategy:
    def test_assign_by_skill(self):
        from src.live_chat.agent_assignment import SkillBasedStrategy, AgentProfile, AgentStatus
        strategy = SkillBasedStrategy()
        a1 = AgentProfile('a1', 'A1', AgentStatus.online, skills=['환불문의'])
        a2 = AgentProfile('a2', 'A2', AgentStatus.online, skills=['배송조회'])
        result = strategy.assign([a1, a2], 'cust-001', tags=['배송조회'])
        assert result.agent_id == 'a2'

    def test_assign_no_tags(self):
        from src.live_chat.agent_assignment import SkillBasedStrategy, AgentProfile, AgentStatus
        strategy = SkillBasedStrategy()
        agents = [
            AgentProfile('a1', 'A1', AgentStatus.online, current_sessions=2, max_sessions=5),
            AgentProfile('a2', 'A2', AgentStatus.online, current_sessions=0, max_sessions=5),
        ]
        result = strategy.assign(agents, 'cust-001', tags=None)
        assert result.agent_id == 'a2'


class TestPriorityStrategy:
    def test_assign_vip(self):
        from src.live_chat.agent_assignment import PriorityStrategy, AgentProfile, AgentStatus
        strategy = PriorityStrategy()
        a1 = AgentProfile('a1', 'A1', AgentStatus.online, rating=3.0)
        a2 = AgentProfile('a2', 'A2', AgentStatus.online, rating=5.0)
        result = strategy.assign([a1, a2], 'cust-001', is_vip=True)
        assert result.agent_id == 'a2'

    def test_assign_normal(self):
        from src.live_chat.agent_assignment import PriorityStrategy, AgentProfile, AgentStatus
        strategy = PriorityStrategy()
        a1 = AgentProfile('a1', 'A1', AgentStatus.online, current_sessions=3, max_sessions=5)
        a2 = AgentProfile('a2', 'A2', AgentStatus.online, current_sessions=1, max_sessions=5)
        result = strategy.assign([a1, a2], 'cust-001', is_vip=False)
        assert result.agent_id == 'a2'


# ─── AgentAssignmentService ───────────────────────────────────────────────────

class TestAgentAssignmentService:
    def _service(self):
        from src.live_chat.agent_assignment import AgentAssignmentService
        return AgentAssignmentService()

    def _agent(self, agent_id='agent-001', name='Agent1', status='online'):
        from src.live_chat.agent_assignment import AgentProfile, AgentStatus
        return AgentProfile(
            agent_id=agent_id,
            name=name,
            status=AgentStatus(status),
        )

    def test_register_agent(self):
        service = self._service()
        agent = self._agent()
        result = service.register_agent(agent)
        assert result.agent_id == 'agent-001'
        assert service.get_agent('agent-001') is not None

    def test_get_agent_not_found(self):
        service = self._service()
        assert service.get_agent('nonexistent') is None

    def test_list_agents(self):
        service = self._service()
        service.register_agent(self._agent('a1'))
        service.register_agent(self._agent('a2'))
        agents = service.list_agents()
        assert len(agents) == 2

    def test_list_agents_by_status(self):
        from src.live_chat.agent_assignment import AgentStatus
        service = self._service()
        service.register_agent(self._agent('a1', status='online'))
        service.register_agent(self._agent('a2', status='offline'))
        online = service.list_agents(status=AgentStatus.online)
        assert len(online) == 1

    def test_update_agent_status(self):
        from src.live_chat.agent_assignment import AgentStatus
        service = self._service()
        service.register_agent(self._agent())
        updated = service.update_agent_status('agent-001', AgentStatus.busy)
        assert updated.status == AgentStatus.busy

    def test_update_agent_status_not_found(self):
        from src.live_chat.agent_assignment import AgentStatus
        service = self._service()
        result = service.update_agent_status('nonexistent', AgentStatus.busy)
        assert result is None

    def test_assign_success(self):
        service = self._service()
        service.register_agent(self._agent())
        agent = service.assign('sess-001', 'cust-001')
        assert agent is not None
        assert agent.current_sessions == 1

    def test_assign_no_agents(self):
        service = self._service()
        agent = service.assign('sess-001', 'cust-001')
        assert agent is None
        # 대기열에 추가됨
        queue = service.get_queue()
        assert len(queue) == 1

    def test_assign_queues_when_full(self):
        service = self._service()
        agent = self._agent()
        agent.max_sessions = 1
        agent.current_sessions = 1
        service.register_agent(agent)
        result = service.assign('sess-001', 'cust-001')
        assert result is None
        assert len(service.get_queue()) == 1

    def test_release(self):
        service = self._service()
        service.register_agent(self._agent())
        service.assign('sess-001', 'cust-001')
        agent = service.release('agent-001')
        assert agent.current_sessions == 0

    def test_release_not_found(self):
        service = self._service()
        result = service.release('nonexistent')
        assert result is None

    def test_get_wait_position(self):
        service = self._service()
        service.assign('sess-001', 'cust-001')  # no agents → queue
        pos = service.get_wait_position('sess-001')
        assert pos == 1

    def test_get_wait_position_not_in_queue(self):
        service = self._service()
        assert service.get_wait_position('not-in-queue') == 0

    def test_dequeue_next(self):
        service = self._service()
        service.assign('sess-001', 'cust-001')
        service.assign('sess-002', 'cust-002')
        entry = service.dequeue_next()
        assert entry is not None
        assert len(service.get_queue()) == 1

    def test_dequeue_empty(self):
        service = self._service()
        assert service.dequeue_next() is None

    def test_get_stats(self):
        service = self._service()
        service.register_agent(self._agent('a1'))
        service.register_agent(self._agent('a2', status='offline'))
        stats = service.get_stats()
        assert stats['total_agents'] == 2
        assert stats['available'] == 1
        assert stats['offline'] == 1

    def test_get_agent_stats(self):
        service = self._service()
        service.register_agent(self._agent())
        stats = service.get_agent_stats('agent-001')
        assert stats is not None
        assert stats['agent_id'] == 'agent-001'
        assert 'load_ratio' in stats

    def test_vip_priority_in_queue(self):
        service = self._service()
        # 일반 고객 먼저 대기열에 추가
        service.assign('sess-001', 'cust-001', is_vip=False)
        # VIP 고객 추가 → 우선순위 높아서 앞에 위치
        service.assign('sess-002', 'cust-002', is_vip=True)
        queue = service.get_queue()
        assert queue[0].session_id == 'sess-002'


# ─── QueueEntry ──────────────────────────────────────────────────────────────

class TestQueueEntry:
    def test_create(self):
        from src.live_chat.agent_assignment import QueueEntry
        entry = QueueEntry(session_id='sess-001', customer_id='cust-001')
        assert entry.session_id == 'sess-001'
        assert entry.enqueued_at != ''

    def test_to_dict(self):
        from src.live_chat.agent_assignment import QueueEntry
        entry = QueueEntry(session_id='sess-001', customer_id='cust-001', is_vip=True)
        d = entry.to_dict()
        assert d['session_id'] == 'sess-001'
        assert d['is_vip'] is True
        assert 'enqueued_at' in d


# ─── FAQEntry ─────────────────────────────────────────────────────────────────

class TestFAQEntry:
    def test_create(self):
        from src.live_chat.auto_reply import FAQEntry
        faq = FAQEntry(
            faq_id='faq-001',
            keywords=['배송', '언제'],
            question='배송은 얼마나?',
            answer='2-3일',
            category='배송조회',
        )
        assert faq.faq_id == 'faq-001'
        assert faq.hit_count == 0

    def test_to_dict(self):
        from src.live_chat.auto_reply import FAQEntry
        faq = FAQEntry('f1', ['kw'], 'Q', 'A', '기타')
        d = faq.to_dict()
        assert 'faq_id' in d
        assert 'keywords' in d
        assert 'answer' in d
        assert 'hit_count' in d


# ─── QuickReply ───────────────────────────────────────────────────────────────

class TestQuickReply:
    def test_create(self):
        from src.live_chat.auto_reply import QuickReply
        qr = QuickReply('배송 확인', 'check_delivery')
        assert qr.label == '배송 확인'
        assert qr.value == 'check_delivery'

    def test_to_dict(self):
        from src.live_chat.auto_reply import QuickReply
        qr = QuickReply('test', 'val')
        d = qr.to_dict()
        assert d['label'] == 'test'
        assert d['value'] == 'val'


# ─── AutoReplyService ─────────────────────────────────────────────────────────

class TestAutoReplyService:
    def _service(self):
        from src.live_chat.auto_reply import AutoReplyService
        # Use 24-hour business hours to avoid time-of-day failures in tests
        return AutoReplyService(business_hours={'start': 0, 'end': 24})

    def test_list_faqs(self):
        service = self._service()
        faqs = service.list_faqs()
        assert len(faqs) >= 5  # default FAQs

    def test_list_faqs_by_category(self):
        service = self._service()
        faqs = service.list_faqs(category='배송조회')
        assert all(f.category == '배송조회' for f in faqs)

    def test_add_faq(self):
        from src.live_chat.auto_reply import FAQEntry
        service = self._service()
        faq = FAQEntry('faq-new', ['테스트'], '테스트 질문', '테스트 답변')
        result = service.add_faq(faq)
        assert service.get_faq('faq-new') is not None

    def test_get_faq(self):
        service = self._service()
        faq = service.get_faq('faq-001')
        assert faq is not None
        assert faq.category == '배송조회'

    def test_get_faq_not_found(self):
        service = self._service()
        assert service.get_faq('nonexistent') is None

    def test_get_reply_matched(self):
        service = self._service()
        faq, quick_replies, needs_agent = service.get_reply('배송이 언제 오나요?')
        assert faq is not None
        assert faq.category == '배송조회'
        assert needs_agent is False
        assert len(quick_replies) > 0

    def test_get_reply_hit_count_increment(self):
        service = self._service()
        faq_before = service.get_faq('faq-001')
        old_count = faq_before.hit_count
        service.get_reply('배송 문의드립니다')
        assert faq_before.hit_count > old_count

    def test_get_reply_no_match(self):
        service = self._service()
        faq, quick_replies, needs_agent = service.get_reply('qwerty12345nomatch9999')
        # 매칭 실패 → 상담원 연결
        assert needs_agent is True

    def test_get_reply_refund(self):
        service = self._service()
        faq, _, needs_agent = service.get_reply('환불 어떻게 하나요')
        assert faq is not None
        assert faq.category == '환불문의'
        assert needs_agent is False

    def test_get_reply_off_hours(self):
        from datetime import datetime, timezone
        from src.live_chat.auto_reply import AutoReplyService
        service = AutoReplyService(business_hours={'start': 9, 'end': 10})
        # is_business_hours at night should return False
        night = datetime(2025, 1, 1, 22, 0, 0, tzinfo=timezone.utc)
        assert service.is_business_hours(night) is False

    def test_is_business_hours_during(self):
        from datetime import datetime, timezone
        from src.live_chat.auto_reply import AutoReplyService
        service = AutoReplyService(business_hours={'start': 9, 'end': 18})
        midday = datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        assert service.is_business_hours(midday) is True

    def test_is_business_hours_night(self):
        from datetime import datetime, timezone
        from src.live_chat.auto_reply import AutoReplyService
        service = AutoReplyService(business_hours={'start': 9, 'end': 18})
        night = datetime(2025, 1, 1, 23, 0, 0, tzinfo=timezone.utc)
        assert service.is_business_hours(night) is False

    def test_get_categories(self):
        service = self._service()
        categories = service.get_categories()
        assert '배송조회' in categories
        assert '환불문의' in categories

    def test_get_stats(self):
        service = self._service()
        stats = service.get_stats()
        assert 'total_faqs' in stats
        assert 'total_hits' in stats
        assert 'by_category' in stats


# ─── ChatHistoryManager ───────────────────────────────────────────────────────

class TestChatHistoryManager:
    def _make_session(self, session_id='sess-001', customer_id='cust-001'):
        return {
            'session_id': session_id,
            'customer_id': customer_id,
            'status': 'closed',
            'started_at': '2025-01-01T10:00:00+00:00',
            'ended_at': '2025-01-01T10:30:00+00:00',
            'rating': 5,
            'tags': [],
        }

    def _make_messages(self):
        return [
            {'message_id': 'm1', 'sender_type': 'customer', 'content': '배송 문의', 'timestamp': '2025-01-01T10:01:00+00:00'},
            {'message_id': 'm2', 'sender_type': 'agent', 'content': '확인하겠습니다', 'timestamp': '2025-01-01T10:02:00+00:00'},
        ]

    def test_save_and_get(self):
        from src.live_chat.history import ChatHistoryManager
        mgr = ChatHistoryManager()
        session = self._make_session()
        mgr.save_session(session, self._make_messages())
        record = mgr.get_session_history('sess-001')
        assert record is not None
        assert record['session']['session_id'] == 'sess-001'

    def test_get_not_found(self):
        from src.live_chat.history import ChatHistoryManager
        mgr = ChatHistoryManager()
        assert mgr.get_session_history('nonexistent') is None

    def test_get_customer_history(self):
        from src.live_chat.history import ChatHistoryManager
        mgr = ChatHistoryManager()
        mgr.save_session(self._make_session('s1', 'cust-001'), [])
        mgr.save_session(self._make_session('s2', 'cust-001'), [])
        mgr.save_session(self._make_session('s3', 'cust-002'), [])
        history = mgr.get_customer_history('cust-001')
        assert len(history) == 2

    def test_search(self):
        from src.live_chat.history import ChatHistoryManager
        mgr = ChatHistoryManager()
        mgr.save_session(self._make_session(), self._make_messages())
        results = mgr.search('배송')
        assert len(results) >= 1
        assert '배송' in results[0]['message']['content']

    def test_search_no_match(self):
        from src.live_chat.history import ChatHistoryManager
        mgr = ChatHistoryManager()
        mgr.save_session(self._make_session(), self._make_messages())
        results = mgr.search('xyz999')
        assert len(results) == 0

    def test_get_stats(self):
        from src.live_chat.history import ChatHistoryManager
        mgr = ChatHistoryManager()
        mgr.save_session(self._make_session('s1'), self._make_messages())
        mgr.save_session(self._make_session('s2'), [])
        stats = mgr.get_stats()
        assert stats['total_sessions'] == 2
        assert 'average_rating' in stats

    def test_get_daily_count(self):
        from src.live_chat.history import ChatHistoryManager
        mgr = ChatHistoryManager()
        mgr.save_session(self._make_session('s1'), [])
        mgr.save_session(self._make_session('s2'), [])
        count = mgr.get_daily_count('2025-01-01')
        assert count == 2


# ─── ChatNotificationService ─────────────────────────────────────────────────

class TestChatNotificationService:
    def _service(self):
        from src.live_chat.notification import ChatNotificationService
        return ChatNotificationService()

    def test_notify_wait_time(self):
        service = self._service()
        note = service.notify_wait_time('cust-001', 300)
        assert note['event'] == 'wait_time'
        assert note['recipient_id'] == 'cust-001'

    def test_notify_agent_assigned(self):
        service = self._service()
        note = service.notify_agent_assigned('cust-001', '김상담', 'sess-001')
        assert note['event'] == 'agent_assigned'
        assert '김상담' in note['message']

    def test_notify_new_session(self):
        service = self._service()
        note = service.notify_new_session('agent-001', 'sess-001', 'cust-001')
        assert note['event'] == 'new_session'
        assert note['recipient_id'] == 'agent-001'

    def test_notify_no_response(self):
        service = self._service()
        note = service.notify_no_response('cust-001', 'sess-001', minutes=10)
        assert note['event'] == 'no_response_reminder'
        assert '10분' in note['message']

    def test_request_rating(self):
        service = self._service()
        note = service.request_rating('cust-001', 'sess-001')
        assert note['event'] == 'rating_request'

    def test_notify_off_hours(self):
        service = self._service()
        note = service.notify_off_hours('cust-001', 'sess-001')
        assert note['event'] == 'off_hours'

    def test_get_notifications_all(self):
        service = self._service()
        service.notify_wait_time('cust-001', 120)
        service.notify_wait_time('cust-002', 240)
        notes = service.get_notifications()
        assert len(notes) == 2

    def test_get_notifications_filtered(self):
        service = self._service()
        service.notify_wait_time('cust-001', 120)
        service.notify_agent_assigned('cust-001', '김상담', 'sess-001')
        notes = service.get_notifications(recipient_id='cust-001')
        assert len(notes) == 2
        notes_wait = service.get_notifications(event='wait_time')
        assert len(notes_wait) == 1

    def test_get_stats(self):
        service = self._service()
        service.notify_wait_time('cust-001', 120)
        service.notify_agent_assigned('cust-001', '김상담', 'sess-001')
        stats = service.get_stats()
        assert stats['total_sent'] == 2
        assert 'by_event' in stats


# ─── ChatAnalytics ────────────────────────────────────────────────────────────

class TestChatAnalytics:
    def _analytics(self):
        from src.live_chat.analytics import ChatAnalytics
        return ChatAnalytics()

    def _session_dict(self, session_id='s1', agent_id='a1', rating=None, tags=None):
        return {
            'session_id': session_id,
            'customer_id': 'cust-001',
            'agent_id': agent_id,
            'status': 'closed',
            'started_at': '2025-01-01T10:00:00+00:00',
            'rating': rating,
            'tags': tags or [],
        }

    def test_record_session(self):
        a = self._analytics()
        a.record_session(self._session_dict())
        assert len(a._sessions) == 1

    def test_record_message(self):
        a = self._analytics()
        a.record_message({'message_id': 'm1', 'content': 'hi'})
        assert len(a._messages) == 1

    def test_get_realtime_metrics(self):
        a = self._analytics()
        metrics = a.get_realtime_metrics(active_sessions=5, waiting_customers=2, online_agents=3)
        assert metrics['active_sessions'] == 5
        assert metrics['waiting_customers'] == 2
        assert metrics['online_agents'] == 3

    def test_get_performance_metrics_empty(self):
        a = self._analytics()
        perf = a.get_performance_metrics()
        assert perf['total_sessions'] == 0
        assert perf['average_rating'] == 0.0

    def test_get_performance_metrics_with_sessions(self):
        a = self._analytics()
        a.record_session(self._session_dict('s1', rating=5))
        a.record_session(self._session_dict('s2', rating=3))
        perf = a.get_performance_metrics()
        assert perf['total_sessions'] == 2
        assert perf['average_rating'] == 4.0

    def test_get_agent_performance(self):
        a = self._analytics()
        a.record_session(self._session_dict('s1', agent_id='a1', rating=5))
        a.record_session(self._session_dict('s2', agent_id='a1', rating=3))
        a.record_session(self._session_dict('s3', agent_id='a2', rating=4))
        perf = a.get_agent_performance()
        assert len(perf) == 2
        a1_perf = next((p for p in perf if p['agent_id'] == 'a1'), None)
        assert a1_perf is not None
        assert a1_perf['total_sessions'] == 2

    def test_get_category_analysis(self):
        a = self._analytics()
        a.record_session(self._session_dict('s1', tags=['배송조회', '주문상태']))
        a.record_session(self._session_dict('s2', tags=['배송조회']))
        analysis = a.get_category_analysis()
        assert analysis['by_category']['배송조회'] == 2
        assert analysis['by_category']['주문상태'] == 1

    def test_get_peak_hours(self):
        a = self._analytics()
        a.record_session(self._session_dict('s1'))
        a.record_session(self._session_dict('s2'))
        peak = a.get_peak_hours()
        assert 'peak_hour' in peak
        assert 'hourly_distribution' in peak

    def test_get_peak_hours_empty(self):
        a = self._analytics()
        peak = a.get_peak_hours()
        assert peak['peak_hour'] is None

    def test_get_dashboard(self):
        a = self._analytics()
        a.record_session(self._session_dict())
        dashboard = a.get_dashboard(active_sessions=1, waiting_customers=0, online_agents=2)
        assert 'realtime' in dashboard
        assert 'performance' in dashboard
        assert 'agent_performance' in dashboard
        assert 'category_analysis' in dashboard
        assert 'peak_hours' in dashboard


# ─── API Blueprint ────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    from flask import Flask
    flask_app = Flask(__name__)
    from src.api.live_chat_api import live_chat_bp
    flask_app.register_blueprint(live_chat_bp)
    flask_app.config['TESTING'] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestLiveChatAPI:
    def test_create_session(self, client):
        resp = client.post('/api/v1/live-chat/sessions', json={
            'customer_id': 'cust-001',
            'channel': 'web',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['customer_id'] == 'cust-001'
        assert 'session_id' in data

    def test_list_sessions(self, client):
        client.post('/api/v1/live-chat/sessions', json={'customer_id': 'cust-001'})
        resp = client.get('/api/v1/live-chat/sessions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_get_session(self, client):
        create_resp = client.post('/api/v1/live-chat/sessions', json={'customer_id': 'cust-001'})
        session_id = create_resp.get_json()['session_id']
        resp = client.get(f'/api/v1/live-chat/sessions/{session_id}')
        assert resp.status_code == 200
        assert resp.get_json()['session_id'] == session_id

    def test_get_session_not_found(self, client):
        resp = client.get('/api/v1/live-chat/sessions/nonexistent')
        assert resp.status_code == 404

    def test_send_message(self, client):
        create_resp = client.post('/api/v1/live-chat/sessions', json={'customer_id': 'cust-001'})
        session_id = create_resp.get_json()['session_id']
        resp = client.post(f'/api/v1/live-chat/sessions/{session_id}/messages', json={
            'sender_type': 'customer',
            'sender_id': 'cust-001',
            'content': '안녕하세요',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['content'] == '안녕하세요'

    def test_send_message_no_content(self, client):
        create_resp = client.post('/api/v1/live-chat/sessions', json={'customer_id': 'cust-001'})
        session_id = create_resp.get_json()['session_id']
        resp = client.post(f'/api/v1/live-chat/sessions/{session_id}/messages', json={
            'sender_type': 'customer',
            'sender_id': 'cust-001',
        })
        assert resp.status_code == 400

    def test_send_message_invalid_session(self, client):
        resp = client.post('/api/v1/live-chat/sessions/nonexistent/messages', json={
            'sender_type': 'customer',
            'sender_id': 'c',
            'content': 'test',
        })
        assert resp.status_code == 404

    def test_get_messages(self, client):
        create_resp = client.post('/api/v1/live-chat/sessions', json={'customer_id': 'cust-001'})
        session_id = create_resp.get_json()['session_id']
        client.post(f'/api/v1/live-chat/sessions/{session_id}/messages', json={
            'sender_type': 'customer',
            'sender_id': 'cust-001',
            'content': '문의',
        })
        resp = client.get(f'/api/v1/live-chat/sessions/{session_id}/messages')
        assert resp.status_code == 200
        msgs = resp.get_json()
        assert isinstance(msgs, list)
        assert len(msgs) >= 1

    def test_close_session(self, client):
        create_resp = client.post('/api/v1/live-chat/sessions', json={'customer_id': 'cust-001'})
        session_id = create_resp.get_json()['session_id']
        resp = client.post(f'/api/v1/live-chat/sessions/{session_id}/close', json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'closed'

    def test_close_session_not_found(self, client):
        resp = client.post('/api/v1/live-chat/sessions/nonexistent/close', json={})
        assert resp.status_code == 404

    def test_rate_session(self, client):
        create_resp = client.post('/api/v1/live-chat/sessions', json={'customer_id': 'cust-001'})
        session_id = create_resp.get_json()['session_id']
        resp = client.post(f'/api/v1/live-chat/sessions/{session_id}/rate', json={'rating': 5})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['rating'] == 5

    def test_rate_session_invalid(self, client):
        create_resp = client.post('/api/v1/live-chat/sessions', json={'customer_id': 'cust-001'})
        session_id = create_resp.get_json()['session_id']
        resp = client.post(f'/api/v1/live-chat/sessions/{session_id}/rate', json={'rating': 10})
        assert resp.status_code == 400

    def test_rate_session_no_rating(self, client):
        create_resp = client.post('/api/v1/live-chat/sessions', json={'customer_id': 'cust-001'})
        session_id = create_resp.get_json()['session_id']
        resp = client.post(f'/api/v1/live-chat/sessions/{session_id}/rate', json={})
        assert resp.status_code == 400

    def test_list_agents(self, client):
        resp = client.get('/api/v1/live-chat/agents')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_list_agents_invalid_status(self, client):
        resp = client.get('/api/v1/live-chat/agents?status=invalid')
        assert resp.status_code == 400

    def test_list_sessions_invalid_status(self, client):
        resp = client.get('/api/v1/live-chat/sessions?status=invalid')
        assert resp.status_code == 400

    def test_get_queue(self, client):
        resp = client.get('/api/v1/live-chat/queue')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'queue' in data
        assert 'queue_length' in data

    def test_list_faq(self, client):
        resp = client.get('/api/v1/live-chat/faq')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 5

    def test_add_faq(self, client):
        resp = client.post('/api/v1/live-chat/faq', json={
            'faq_id': 'faq-test-001',
            'keywords': ['테스트'],
            'question': '테스트 질문',
            'answer': '테스트 답변',
            'category': '기타',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['faq_id'] == 'faq-test-001'

    def test_add_faq_missing_field(self, client):
        resp = client.post('/api/v1/live-chat/faq', json={
            'faq_id': 'faq-x',
            'keywords': ['k'],
        })
        assert resp.status_code == 400

    def test_get_analytics(self, client):
        resp = client.get('/api/v1/live-chat/analytics')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'session_stats' in data
        assert 'performance' in data
        assert 'faq_stats' in data

    def test_get_dashboard(self, client):
        resp = client.get('/api/v1/live-chat/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'realtime' in data
        assert 'performance' in data


# ─── 봇 커맨드 ────────────────────────────────────────────────────────────────

class TestChatBotCommands:
    def test_cmd_chat_status(self):
        from src.bot.commands import cmd_chat_status
        result = cmd_chat_status()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_chat_queue(self):
        from src.bot.commands import cmd_chat_queue
        result = cmd_chat_queue()
        assert isinstance(result, str)

    def test_cmd_agent_status(self):
        from src.bot.commands import cmd_agent_status
        result = cmd_agent_status()
        assert isinstance(result, str)

    def test_cmd_chat_stats(self):
        from src.bot.commands import cmd_chat_stats
        result = cmd_chat_stats()
        assert isinstance(result, str)

    def test_cmd_chat_dashboard(self):
        from src.bot.commands import cmd_chat_dashboard
        result = cmd_chat_dashboard()
        assert isinstance(result, str)


# ─── 포맷터 ────────────────────────────────────────────────────────────────────

class TestChatFormatters:
    def test_format_chat_session(self):
        from src.bot.formatters import format_message
        data = {
            'session_id': 'sess-001',
            'status': 'active',
            'customer_id': 'cust-001',
            'agent_id': 'agent-001',
            'message_count': 5,
            'rating': 4,
        }
        result = format_message('chat_session', data)
        assert '채팅 세션' in result
        assert 'active' in result

    def test_format_chat_stats(self):
        from src.bot.formatters import format_message
        data = {
            'total_sessions': 10,
            'average_rating': 4.5,
            'rated_sessions': 8,
            'by_status': {'active': 3, 'closed': 7},
        }
        result = format_message('chat_stats', data)
        assert '채팅 통계' in result
        assert '10' in result

    def test_format_chat_queue(self):
        from src.bot.formatters import format_message
        data = {
            'queue': [
                {'customer_id': 'cust-001', 'is_vip': False},
                {'customer_id': 'cust-002', 'is_vip': True},
            ],
            'agent_stats': {'available': 2},
        }
        result = format_message('chat_queue', data)
        assert '대기열' in result

    def test_format_agent_profile(self):
        from src.bot.formatters import format_message
        data = {
            'agent_id': 'agent-001',
            'name': '김상담',
            'status': 'online',
            'is_available': True,
            'current_sessions': 2,
            'max_sessions': 5,
            'skills': ['배송조회'],
            'rating': 4.8,
            'shift': '09:00-18:00',
        }
        result = format_message('agent_profile', data)
        assert '김상담' in result
        assert '상담원 프로필' in result

    def test_format_chat_dashboard(self):
        from src.bot.formatters import format_message
        data = {
            'realtime': {
                'active_sessions': 5,
                'waiting_customers': 2,
                'online_agents': 3,
            },
            'performance': {
                'avg_first_response_seconds': 120,
                'avg_resolution_seconds': 600,
                'average_rating': 4.5,
                'total_sessions': 20,
            },
        }
        result = format_message('chat_dashboard', data)
        assert '대시보드' in result
        assert '5' in result

    def test_format_message_unknown_type(self):
        from src.bot.formatters import format_message
        result = format_message('chat_session', {
            'session_id': 'x',
            'status': 'waiting',
            'customer_id': 'c',
            'agent_id': None,
            'message_count': 0,
            'rating': None,
        })
        assert isinstance(result, str)
