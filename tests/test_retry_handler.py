"""tests/test_retry_handler.py — 재시도 핸들러 테스트.

지수 백오프 재시도 로직과 @retry 데코레이터를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.resilience.retry_handler import RetryHandler, retry  # noqa: E402


# ──────────────────────────────────────────────────────────
# RetryHandler 테스트
# ──────────────────────────────────────────────────────────

class TestRetryHandler:
    def test_success_on_first_try(self):
        """첫 시도에 성공하면 결과를 반환한다."""
        handler = RetryHandler(max_retries=3, initial_delay=0)
        result = handler.execute(lambda: "ok")
        assert result == "ok"

    def test_success_after_retries(self):
        """몇 번 실패 후 성공하면 결과를 반환한다."""
        call_count = {"n": 0}

        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ConnectionError("일시적 실패")
            return "recovered"

        handler = RetryHandler(max_retries=3, initial_delay=0, jitter=False)
        result = handler.execute(flaky)
        assert result == "recovered"
        assert call_count["n"] == 3

    def test_raises_after_max_retries(self):
        """최대 재시도 횟수 초과 시 예외를 발생시킨다."""
        call_count = {"n": 0}

        def always_fails():
            call_count["n"] += 1
            raise ValueError("계속 실패")

        handler = RetryHandler(max_retries=2, initial_delay=0, jitter=False)
        with pytest.raises(ValueError, match="계속 실패"):
            handler.execute(always_fails)

        assert call_count["n"] == 3  # 최초 1 + 재시도 2

    def test_only_retries_specified_exceptions(self):
        """지정된 예외 타입만 재시도한다."""
        call_count = {"n": 0}

        def raises_type_error():
            call_count["n"] += 1
            raise TypeError("재시도 안 함")

        # TypeError는 재시도 대상이 아님
        handler = RetryHandler(
            max_retries=3, initial_delay=0, exceptions=(ConnectionError,)
        )
        with pytest.raises(TypeError):
            handler.execute(raises_type_error)

        assert call_count["n"] == 1  # 재시도 없음

    def test_delay_calculation(self):
        """백오프 계산이 올바르다 (지터 비활성화 시)."""
        handler = RetryHandler(
            max_retries=3,
            backoff=2.0,
            initial_delay=1.0,
            max_delay=60.0,
            jitter=False,
        )
        assert handler._calc_delay(1) == 1.0   # 1.0 * 2^0
        assert handler._calc_delay(2) == 2.0   # 1.0 * 2^1
        assert handler._calc_delay(3) == 4.0   # 1.0 * 2^2

    def test_max_delay_capped(self):
        """max_delay를 초과하지 않는다."""
        handler = RetryHandler(
            max_retries=10,
            backoff=2.0,
            initial_delay=1.0,
            max_delay=5.0,
            jitter=False,
        )
        delay = handler._calc_delay(10)
        assert delay <= 5.0

    def test_jitter_adds_randomness(self):
        """지터 활성화 시 동일 attempt에서 값이 다를 수 있다."""
        handler = RetryHandler(initial_delay=1.0, jitter=True)
        delays = {handler._calc_delay(1) for _ in range(10)}
        # 지터가 있으면 일부 값이 달라야 함
        assert len(delays) > 1


# ──────────────────────────────────────────────────────────
# @retry 데코레이터 테스트
# ──────────────────────────────────────────────────────────

class TestRetryDecorator:
    def test_decorator_wraps_function(self):
        """데코레이터가 함수 이름/docstring을 보존한다."""
        @retry(max_retries=3)
        def my_api_call():
            """API 호출."""
            return 42

        assert my_api_call.__name__ == "my_api_call"
        assert "API" in my_api_call.__doc__
        assert my_api_call() == 42

    def test_decorator_retries_on_exception(self):
        """데코레이터가 지정된 예외에 대해 재시도한다."""
        attempts = {"n": 0}

        @retry(max_retries=2, initial_delay=0, exceptions=(IOError,))
        def unstable():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise IOError("일시적 IO 오류")
            return "done"

        result = unstable()
        assert result == "done"
        assert attempts["n"] == 2

    def test_decorator_exposes_handler(self):
        """데코레이터 함수에 _retry_handler 속성이 있다."""
        @retry(max_retries=5)
        def func():
            pass

        assert hasattr(func, '_retry_handler')
        assert func._retry_handler.max_retries == 5
