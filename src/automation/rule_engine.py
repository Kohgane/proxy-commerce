"""src/automation/rule_engine.py — 조건-액션 기반 규칙 엔진.

Google Sheets에서 규칙 정의를 로드하고 조건 평가 및 액션 실행.

환경변수:
  AUTOMATION_ENABLED    — 활성화 여부 (기본 "0")
  AUTOMATION_SHEET_NAME — 규칙 정의 워크시트 이름 (기본 "automation_rules")
  GOOGLE_SHEET_ID       — Google Sheets ID
"""

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_ENABLED = os.getenv('AUTOMATION_ENABLED', '0') == '1'
_SHEET_NAME = os.getenv('AUTOMATION_SHEET_NAME', 'automation_rules')

# 지원 조건 연산자
OPERATORS = {'eq', 'ne', 'gt', 'lt', 'gte', 'lte', 'contains', 'in', 'not_in'}

# 지원 액션 타입
ACTION_TYPES = {
    'send_telegram', 'send_email', 'update_price', 'update_stock',
    'create_reorder', 'log_audit', 'pause_campaign',
}

RULE_HEADERS = [
    'rule_id', 'name', 'trigger', 'conditions', 'actions',
    'enabled', 'priority',
]


def _eval_condition(condition: dict, event_data: dict) -> bool:
    """단일 조건을 평가한다.

    Args:
        condition: {'field': str, 'op': str, 'value': any}
        event_data: 이벤트 데이터 dict

    Returns:
        조건 만족 여부
    """
    field = condition.get('field', '')
    op = condition.get('op', 'eq')
    expected = condition.get('value')

    # 중첩 필드 지원 (예: "order.total_krw")
    actual = event_data
    for part in field.split('.'):
        if isinstance(actual, dict):
            actual = actual.get(part)
        else:
            actual = None
            break

    try:
        if op == 'eq':
            return actual == expected
        elif op == 'ne':
            return actual != expected
        elif op == 'gt':
            return float(actual) > float(expected)
        elif op == 'lt':
            return float(actual) < float(expected)
        elif op == 'gte':
            return float(actual) >= float(expected)
        elif op == 'lte':
            return float(actual) <= float(expected)
        elif op == 'contains':
            return expected in str(actual)
        elif op == 'in':
            items = expected if isinstance(expected, list) else [expected]
            return actual in items
        elif op == 'not_in':
            items = expected if isinstance(expected, list) else [expected]
            return actual not in items
        else:
            logger.warning("알 수 없는 연산자: %s", op)
            return False
    except (TypeError, ValueError) as exc:
        logger.debug("조건 평가 실패 (%s %s %s): %s", field, op, expected, exc)
        return False


def evaluate_rule(rule: dict, event_data: dict) -> bool:
    """규칙의 모든 조건을 평가한다 (AND 로직).

    Args:
        rule: 규칙 dict
        event_data: 이벤트 데이터

    Returns:
        모든 조건 만족 여부
    """
    if not rule.get('enabled', True):
        return False

    trigger = rule.get('trigger', '')
    event_type = event_data.get('event_type', '')
    if trigger and trigger != event_type:
        return False

    conditions = rule.get('conditions', [])
    if isinstance(conditions, str):
        try:
            conditions = json.loads(conditions)
        except Exception:
            conditions = []

    return all(_eval_condition(c, event_data) for c in conditions)


def execute_actions(rule: dict, event_data: dict) -> list:
    """규칙의 액션을 실행한다.

    Args:
        rule: 규칙 dict
        event_data: 이벤트 데이터

    Returns:
        실행 결과 리스트 [{action_type, status, detail}]
    """
    actions = rule.get('actions', [])
    if isinstance(actions, str):
        try:
            actions = json.loads(actions)
        except Exception:
            actions = []

    results = []
    for action in actions:
        action_type = action.get('action_type', '')
        params = action.get('params', {})
        result = _dispatch_action(action_type, params, event_data, rule)
        results.append({
            'action_type': action_type,
            'status': result.get('status', 'ok'),
            'detail': result.get('detail', ''),
        })

    return results


def _dispatch_action(action_type: str, params: dict,
                     event_data: dict, rule: dict) -> dict:
    """액션 타입에 따라 실제 실행."""
    try:
        if action_type == 'send_telegram':
            msg = params.get('message', str(event_data))
            from ..utils.telegram import send_tele
            send_tele(f"[{rule.get('name', 'rule')}] {msg}")
            return {'status': 'ok', 'detail': 'telegram sent'}

        elif action_type == 'send_email':
            return {'status': 'skipped', 'detail': 'email dispatch not implemented'}

        elif action_type == 'update_price':
            return {'status': 'skipped', 'detail': 'price update requires catalog access'}

        elif action_type == 'update_stock':
            return {'status': 'skipped', 'detail': 'stock update requires inventory access'}

        elif action_type == 'create_reorder':
            sku = params.get('sku') or event_data.get('sku', '')
            if sku:
                from ..reorder.reorder_queue import ReorderQueue
                queue = ReorderQueue()
                queue.add({'sku': sku, 'qty': params.get('qty', 1),
                           'source': 'automation', 'rule_id': rule.get('rule_id', '')})
                return {'status': 'ok', 'detail': f'reorder queued for {sku}'}
            return {'status': 'skipped', 'detail': 'no sku provided'}

        elif action_type == 'log_audit':
            from ..audit.audit_log import AuditLog
            log = AuditLog()
            log.record(
                action=f"automation:{rule.get('rule_id', 'unknown')}",
                details=str(event_data)[:500],
            )
            return {'status': 'ok', 'detail': 'audit logged'}

        elif action_type == 'pause_campaign':
            campaign_id = params.get('campaign_id') or event_data.get('campaign_id', '')
            if campaign_id:
                from ..marketing.campaign_manager import CampaignManager
                mgr = CampaignManager()
                mgr.pause_campaign(campaign_id)
                return {'status': 'ok', 'detail': f'campaign {campaign_id} paused'}
            return {'status': 'skipped', 'detail': 'no campaign_id provided'}

        else:
            return {'status': 'unknown', 'detail': f'unknown action: {action_type}'}

    except Exception as exc:
        logger.error("액션 실행 실패 (%s): %s", action_type, exc)
        return {'status': 'error', 'detail': str(exc)}


class RuleEngine:
    """규칙 엔진 — Google Sheets에서 규칙 로드 및 실행."""

    def __init__(self):
        self._sheet = None

    def _get_sheet(self):
        if self._sheet is None:
            from ..utils.sheets import open_sheet
            sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
            self._sheet = open_sheet(sheet_id, _SHEET_NAME)
            self._ensure_headers()
        return self._sheet

    def _ensure_headers(self):
        ws = self._sheet
        rows = ws.get_all_values()
        if not rows or rows[0] != RULE_HEADERS:
            ws.clear()
            ws.append_row(RULE_HEADERS)

    def get_rules(self, trigger: str = None, enabled_only: bool = True) -> list:
        """규칙 목록을 반환한다."""
        if not _ENABLED:
            return []
        try:
            ws = self._get_sheet()
            records = ws.get_all_records()
        except Exception as exc:
            logger.warning("규칙 조회 실패: %s", exc)
            return []

        rules = []
        for row in records:
            if enabled_only and str(row.get('enabled', '1')) not in ('1', 'true', 'True'):
                continue
            if trigger and str(row.get('trigger', '')) != trigger:
                continue

            rule = dict(row)
            # JSON 필드 파싱
            for field in ('conditions', 'actions'):
                val = rule.get(field, '[]')
                if isinstance(val, str):
                    try:
                        rule[field] = json.loads(val)
                    except Exception:
                        rule[field] = []
            rules.append(rule)

        return sorted(rules, key=lambda r: int(r.get('priority', 0) or 0))

    def add_rule(self, rule: dict) -> bool:
        """새 규칙을 추가한다."""
        try:
            ws = self._get_sheet()
            rule_id = rule.get('rule_id') or f"rule_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            conditions = rule.get('conditions', [])
            actions = rule.get('actions', [])
            ws.append_row([
                rule_id,
                rule.get('name', ''),
                rule.get('trigger', ''),
                json.dumps(conditions, ensure_ascii=False),
                json.dumps(actions, ensure_ascii=False),
                '1' if rule.get('enabled', True) else '0',
                str(rule.get('priority', 0)),
            ])
            return True
        except Exception as exc:
            logger.error("규칙 추가 실패: %s", exc)
            return False

    def update_rule(self, rule_id: str, updates: dict) -> bool:
        """규칙을 업데이트한다."""
        try:
            ws = self._get_sheet()
            records = ws.get_all_records()
            for i, row in enumerate(records):
                if str(row.get('rule_id')) == str(rule_id):
                    row.update(updates)
                    row_num = i + 2
                    for field in ('conditions', 'actions'):
                        if field in row and isinstance(row[field], (list, dict)):
                            row[field] = json.dumps(row[field], ensure_ascii=False)
                    ws.update(f'A{row_num}:G{row_num}', [[
                        row.get('rule_id', ''),
                        row.get('name', ''),
                        row.get('trigger', ''),
                        row.get('conditions', '[]'),
                        row.get('actions', '[]'),
                        row.get('enabled', '1'),
                        row.get('priority', '0'),
                    ]])
                    return True
            return False
        except Exception as exc:
            logger.error("규칙 업데이트 실패: %s", exc)
            return False

    def process_event(self, event_data: dict) -> list:
        """이벤트를 처리하고 해당하는 규칙을 실행한다."""
        if not _ENABLED:
            return []

        event_type = event_data.get('event_type', '')
        rules = self.get_rules(trigger=event_type)
        all_results = []

        for rule in rules:
            if evaluate_rule(rule, event_data):
                action_results = execute_actions(rule, event_data)
                all_results.append({
                    'rule_id': rule.get('rule_id'),
                    'rule_name': rule.get('name'),
                    'actions': action_results,
                })

        return all_results
