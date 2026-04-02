"""src/audit/decorators.py — Phase 41: @audit_log 데코레이터."""
import functools
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def audit_log(
    event_type: str,
    actor: str = 'system',
    resource_fn=None,
    store=None,
):
    """함수 실행 전/후를 자동으로 감사 로그에 기록하는 데코레이터.

    Args:
        event_type: 이벤트 타입 문자열
        actor: 행위자 식별자
        resource_fn: 인자에서 리소스 문자열을 추출하는 함수 (optional)
        store: AuditStore 인스턴스 (없으면 로깅만)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            started_at = datetime.now(timezone.utc).isoformat()
            resource = ''
            if resource_fn:
                try:
                    resource = resource_fn(*args, **kwargs)
                except Exception:
                    pass

            before = None  # reserved for future before/after state capture
            result = None
            error = None
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as exc:
                error = str(exc)
                raise
            finally:
                ended_at = datetime.now(timezone.utc).isoformat()
                entry = {
                    'timestamp': started_at,
                    'event_type': event_type,
                    'actor': actor,
                    'resource': resource or func.__name__,
                    'details': {
                        'function': func.__name__,
                        'started_at': started_at,
                        'ended_at': ended_at,
                        'success': error is None,
                        'error': error,
                    },
                    'ip_address': '',
                }
                logger.info("AUDIT[decorator] | %s | %s | %s", event_type, actor, resource or func.__name__)
                if store is not None:
                    try:
                        store.append(entry)
                    except Exception as exc2:
                        logger.warning("감사 로그 저장 실패: %s", exc2)
        return wrapper
    return decorator
