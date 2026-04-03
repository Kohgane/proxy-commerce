"""src/rate_limiting/rate_limit_middleware.py — Flask 미들웨어."""
from __future__ import annotations

from .sliding_window_limiter import SlidingWindowLimiter
from .rate_limit_policy import RateLimitPolicy


class RateLimitMiddleware:
    """Flask before_request 훅으로 레이트 리미팅 적용."""

    def __init__(self) -> None:
        self._limiter = SlidingWindowLimiter()
        self._policy = RateLimitPolicy()

    def init_app(self, app) -> None:
        """Flask app에 미들웨어 등록."""
        @app.before_request
        def _before():
            from flask import request, jsonify
            endpoint = request.path
            policy = self._policy.get_policy(endpoint)
            if policy:
                key = f"{endpoint}:{request.remote_addr}"
                allowed = self._limiter.check(key, policy["limit"], policy["window"])
                if not allowed:
                    return jsonify({"error": "Too Many Requests"}), 429

    def get_limiter(self) -> SlidingWindowLimiter:
        return self._limiter

    def get_policy(self) -> RateLimitPolicy:
        return self._policy
