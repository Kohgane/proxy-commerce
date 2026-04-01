"""tests/test_rule_engine.py — 규칙 엔진 테스트."""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestEvalCondition:
    def test_eq_true(self):
        from src.automation.rule_engine import _eval_condition
        assert _eval_condition({'field': 'status', 'op': 'eq', 'value': 'new'}, {'status': 'new'})

    def test_eq_false(self):
        from src.automation.rule_engine import _eval_condition
        assert not _eval_condition({'field': 'status', 'op': 'eq', 'value': 'new'}, {'status': 'old'})

    def test_ne(self):
        from src.automation.rule_engine import _eval_condition
        assert _eval_condition({'field': 'status', 'op': 'ne', 'value': 'old'}, {'status': 'new'})

    def test_gt(self):
        from src.automation.rule_engine import _eval_condition
        assert _eval_condition({'field': 'stock', 'op': 'gt', 'value': 3}, {'stock': 5})
        assert not _eval_condition({'field': 'stock', 'op': 'gt', 'value': 3}, {'stock': 3})

    def test_lt(self):
        from src.automation.rule_engine import _eval_condition
        assert _eval_condition({'field': 'stock', 'op': 'lt', 'value': 5}, {'stock': 3})

    def test_gte(self):
        from src.automation.rule_engine import _eval_condition
        assert _eval_condition({'field': 'stock', 'op': 'gte', 'value': 3}, {'stock': 3})

    def test_lte(self):
        from src.automation.rule_engine import _eval_condition
        assert _eval_condition({'field': 'stock', 'op': 'lte', 'value': 3}, {'stock': 3})
        assert not _eval_condition({'field': 'stock', 'op': 'lte', 'value': 3}, {'stock': 4})

    def test_contains(self):
        from src.automation.rule_engine import _eval_condition
        assert _eval_condition({'field': 'name', 'op': 'contains', 'value': 'bag'},
                               {'name': 'leather bag'})

    def test_in(self):
        from src.automation.rule_engine import _eval_condition
        assert _eval_condition({'field': 'status', 'op': 'in', 'value': ['a', 'b']},
                               {'status': 'a'})
        assert not _eval_condition({'field': 'status', 'op': 'in', 'value': ['a', 'b']},
                                   {'status': 'c'})

    def test_not_in(self):
        from src.automation.rule_engine import _eval_condition
        assert _eval_condition({'field': 'status', 'op': 'not_in', 'value': ['a', 'b']},
                               {'status': 'c'})

    def test_nested_field(self):
        """중첩 필드 접근 지원."""
        from src.automation.rule_engine import _eval_condition
        assert _eval_condition({'field': 'order.total_krw', 'op': 'gt', 'value': 100},
                               {'order': {'total_krw': 200}})

    def test_unknown_op_returns_false(self):
        from src.automation.rule_engine import _eval_condition
        assert not _eval_condition({'field': 'x', 'op': 'unknown', 'value': 1}, {'x': 1})


class TestEvaluateRule:
    def test_all_conditions_met(self):
        from src.automation.rule_engine import evaluate_rule
        rule = {
            'enabled': True,
            'trigger': 'test_event',
            'conditions': [
                {'field': 'stock', 'op': 'lte', 'value': 3},
                {'field': 'active', 'op': 'eq', 'value': True},
            ],
        }
        event = {'event_type': 'test_event', 'stock': 2, 'active': True}
        assert evaluate_rule(rule, event)

    def test_one_condition_fails(self):
        from src.automation.rule_engine import evaluate_rule
        rule = {
            'enabled': True,
            'trigger': 'test_event',
            'conditions': [
                {'field': 'stock', 'op': 'lte', 'value': 3},
            ],
        }
        event = {'event_type': 'test_event', 'stock': 10}
        assert not evaluate_rule(rule, event)

    def test_disabled_rule_returns_false(self):
        from src.automation.rule_engine import evaluate_rule
        rule = {'enabled': False, 'trigger': 'test_event', 'conditions': []}
        event = {'event_type': 'test_event'}
        assert not evaluate_rule(rule, event)

    def test_wrong_trigger_returns_false(self):
        from src.automation.rule_engine import evaluate_rule
        rule = {'enabled': True, 'trigger': 'other_event', 'conditions': []}
        event = {'event_type': 'test_event'}
        assert not evaluate_rule(rule, event)

    def test_json_string_conditions(self):
        """conditions가 JSON 문자열로 저장된 경우 파싱되어야 한다."""
        import json
        from src.automation.rule_engine import evaluate_rule
        conditions = [{'field': 'stock', 'op': 'lt', 'value': 5}]
        rule = {
            'enabled': True,
            'trigger': 'test_event',
            'conditions': json.dumps(conditions),
        }
        event = {'event_type': 'test_event', 'stock': 2}
        assert evaluate_rule(rule, event)


class TestExecuteActions:
    def test_send_telegram_action(self):
        from src.automation.rule_engine import execute_actions
        rule = {
            'rule_id': 'r1',
            'name': 'test rule',
            'actions': [{'action_type': 'send_telegram', 'params': {'message': 'hello'}}],
        }
        with patch('src.utils.telegram.send_tele') as mock_tele:
            results = execute_actions(rule, {'event_type': 'test'})
        assert len(results) == 1
        assert results[0]['action_type'] == 'send_telegram'
        mock_tele.assert_called_once()

    def test_unknown_action_returns_unknown_status(self):
        from src.automation.rule_engine import execute_actions
        rule = {
            'rule_id': 'r1',
            'name': 'test',
            'actions': [{'action_type': 'nonexistent_action', 'params': {}}],
        }
        results = execute_actions(rule, {})
        assert results[0]['status'] == 'unknown'

    def test_json_string_actions(self):
        """actions가 JSON 문자열로 저장된 경우 파싱되어야 한다."""
        import json
        from src.automation.rule_engine import execute_actions
        actions = [{'action_type': 'send_telegram', 'params': {'message': 'test'}}]
        rule = {
            'rule_id': 'r1',
            'name': 'test',
            'actions': json.dumps(actions),
        }
        with patch('src.utils.telegram.send_tele'):
            results = execute_actions(rule, {})
        assert len(results) == 1
