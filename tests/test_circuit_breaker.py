"""tests/test_circuit_breaker.py — 서킷 브레이커 테스트.

CLOSED → OPEN → HALF_OPEN → CLOSED 상태 전이와 데코레이터 동작을 검증한다.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.resilience.circuit_breaker import (
    CircuitBreaker, CircuitOpenError, CircuitState, circuit_breaker
)


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def cb():
    """테스트용 서킷 브레이커 — 낮은 임계값, 짧은 타임아웃."""
    return CircuitBreaker(name="test_cb", failure_threshold=3, timeout=1)


# ──────────────────────────────────────────────────────────
# 상태 전이 테스트
# ──────────────────────────────────────────────────────────

class TestCircuitBreakerStateTransitions:
    def test_initial_state_is_closed(self, cb):
        """초기 상태는 CLOSED이다."""
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed is True
        assert cb.is_open is False

    def test_open_after_failure_threshold(self, cb):
        """임계값만큼 실패하면 OPEN 상태로 전환된다."""
        def failing_func():
            raise ValueError("실패")

        for _ in range(3):
            try:
                cb.call(failing_func)
            except ValueError:
                pass

        assert cb.state == CircuitState.OPEN

    def test_open_rejects_calls(self, cb):
        """OPEN 상태에서 호출 시 CircuitOpenError가 발생한다."""
        def failing_func():
            raise ValueError("실패")

        for _ in range(3):
            try:
                cb.call(failing_func)
            except ValueError:
                pass

        with pytest.raises(CircuitOpenError):
            cb.call(lambda: "should not be called")

    def test_half_open_after_timeout(self, cb):
        """타임아웃 후 HALF_OPEN 상태로 전환된다."""
        def failing_func():
            raise ValueError("실패")

        for _ in range(3):
            try:
                cb.call(failing_func)
            except ValueError:
                pass

        assert cb.state == CircuitState.OPEN
        time.sleep(1.1)  # 타임아웃(1초) 경과
        assert cb.state == CircuitState.HALF_OPEN

    def test_closed_after_half_open_success(self, cb):
        """HALF_OPEN에서 성공 시 CLOSED로 복구된다."""
        def failing_func():
            raise ValueError("실패")

        for _ in range(3):
            try:
                cb.call(failing_func)
            except ValueError:
                pass

        time.sleep(1.1)  # HALF_OPEN으로 전환
        result = cb.call(lambda: "success")
        assert result == "success"
        assert cb.state == CircuitState.CLOSED

    def test_open_again_after_half_open_failure(self, cb):
        """HALF_OPEN에서 실패 시 다시 OPEN으로 전환된다."""
        def failing_func():
            raise ValueError("실패")

        for _ in range(3):
            try:
                cb.call(failing_func)
            except ValueError:
                pass

        time.sleep(1.1)  # HALF_OPEN으로 전환
        try:
            cb.call(failing_func)
        except ValueError:
            pass

        assert cb.state == CircuitState.OPEN


# ──────────────────────────────────────────────────────────
# 데코레이터 테스트
# ──────────────────────────────────────────────────────────

class TestCircuitBreakerDecorator:
    def test_decorator_wraps_function(self):
        """데코레이터가 함수를 올바르게 감싼다."""
        @circuit_breaker(failures=3, timeout=1)
        def my_func():
            return "result"

        assert my_func() == "result"
        assert hasattr(my_func, '_circuit_breaker')

    def test_decorator_with_fallback(self):
        """fallback이 설정되면 CircuitOpenError 대신 fallback 값을 반환한다."""
        call_count = {"n": 0}

        @circuit_breaker(failures=2, timeout=60, fallback={"error": "circuit_open"})
        def fragile_func():
            call_count["n"] += 1
            raise ConnectionError("연결 실패")

        for _ in range(2):
            try:
                fragile_func()
            except ConnectionError:
                pass

        # OPEN 상태에서 fallback 반환
        result = fragile_func()
        assert result == {"error": "circuit_open"}

    def test_decorator_circuit_breaker_instance(self):
        """데코레이터 함수에 _circuit_breaker 속성이 있다."""
        @circuit_breaker(failures=5, timeout=30, name="my_service")
        def api_call():
            pass

        assert api_call._circuit_breaker is not None
        assert api_call._circuit_breaker.name == "my_service"


# ──────────────────────────────────────────────────────────
# 알림 콜백 테스트
# ──────────────────────────────────────────────────────────

class TestCircuitBreakerNotification:
    def test_notify_on_state_change(self):
        """상태 변경 시 알림 콜백이 호출된다."""
        notifications = []

        def on_state_change(name, old, new):
            notifications.append((name, old, new))

        cb = CircuitBreaker(name="notify_test", failure_threshold=2, timeout=60, notify_fn=on_state_change)

        def failing():
            raise ValueError("fail")

        for _ in range(2):
            try:
                cb.call(failing)
            except ValueError:
                pass

        assert len(notifications) >= 1
        assert notifications[-1][2] == CircuitState.OPEN


# ──────────────────────────────────────────────────────────
# reset 테스트
# ──────────────────────────────────────────────────────────

class TestCircuitBreakerReset:
    def test_reset_to_closed(self, cb):
        """reset()은 서킷을 CLOSED로 강제 초기화한다."""
        def failing():
            raise ValueError("fail")

        for _ in range(3):
            try:
                cb.call(failing)
            except ValueError:
                pass

        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0
