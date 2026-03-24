"""src/automation/workflow_templates.py — 사전 정의 워크플로 템플릿.

비즈니스 규칙 기반 워크플로를 rule_engine 규칙 세트로 정의.
"""

# ─────────────────────────────────────────────────────────────
# 재고 부족 워크플로
# 트리거: low_stock_event
# 액션: 텔레그램 알림 + 재발주 큐 생성
# ─────────────────────────────────────────────────────────────
low_stock_alert_workflow = [
    {
        'rule_id': 'low_stock_telegram',
        'name': '재고 부족 텔레그램 알림',
        'trigger': 'low_stock_event',
        'conditions': [
            {'field': 'stock', 'op': 'lte', 'value': 3},
        ],
        'actions': [
            {
                'action_type': 'send_telegram',
                'params': {
                    'message': '⚠️ 재고 부족: {{sku}} 재고 {{stock}}개 남음',
                },
            },
        ],
        'enabled': True,
        'priority': 10,
    },
    {
        'rule_id': 'low_stock_reorder',
        'name': '재고 부족 자동 재발주',
        'trigger': 'low_stock_event',
        'conditions': [
            {'field': 'stock', 'op': 'lte', 'value': 1},
        ],
        'actions': [
            {
                'action_type': 'create_reorder',
                'params': {'qty': 10},
            },
            {
                'action_type': 'log_audit',
                'params': {},
            },
        ],
        'enabled': True,
        'priority': 20,
    },
]

# ─────────────────────────────────────────────────────────────
# 경쟁사 가격 변동 워크플로
# 트리거: price_change_event
# 액션: 가격 재계산 알림 + 텔레그램 알림
# ─────────────────────────────────────────────────────────────
price_change_workflow = [
    {
        'rule_id': 'price_change_alert',
        'name': '경쟁사 가격 변동 알림',
        'trigger': 'price_change_event',
        'conditions': [
            {'field': 'change_pct', 'op': 'gte', 'value': 5},
        ],
        'actions': [
            {
                'action_type': 'send_telegram',
                'params': {
                    'message': '📈 경쟁사 가격 변동: {{sku}} {{change_pct}}% 변동',
                },
            },
            {
                'action_type': 'log_audit',
                'params': {},
            },
        ],
        'enabled': True,
        'priority': 10,
    },
    {
        'rule_id': 'price_drop_alert',
        'name': '경쟁사 가격 급락 알림',
        'trigger': 'price_change_event',
        'conditions': [
            {'field': 'change_pct', 'op': 'lte', 'value': -10},
        ],
        'actions': [
            {
                'action_type': 'send_telegram',
                'params': {
                    'message': '📉 경쟁사 가격 급락: {{sku}} 가격 재검토 필요',
                },
            },
        ],
        'enabled': True,
        'priority': 5,
    },
]

# ─────────────────────────────────────────────────────────────
# 신규 주문 워크플로
# 트리거: new_order_event
# 액션: 검증 → 라우팅 → 알림 → 감사 로그
# ─────────────────────────────────────────────────────────────
new_order_workflow = [
    {
        'rule_id': 'new_order_notify',
        'name': '신규 주문 텔레그램 알림',
        'trigger': 'new_order_event',
        'conditions': [
            {'field': 'order_total_krw', 'op': 'gt', 'value': 0},
        ],
        'actions': [
            {
                'action_type': 'send_telegram',
                'params': {
                    'message': '🛒 신규 주문 접수: #{{order_id}} {{order_total_krw}}원',
                },
            },
            {
                'action_type': 'log_audit',
                'params': {},
            },
        ],
        'enabled': True,
        'priority': 10,
    },
    {
        'rule_id': 'new_order_high_value',
        'name': '고액 신규 주문 알림',
        'trigger': 'new_order_event',
        'conditions': [
            {'field': 'order_total_krw', 'op': 'gte', 'value': 500000},
        ],
        'actions': [
            {
                'action_type': 'send_telegram',
                'params': {
                    'message': '💎 고액 주문 접수: #{{order_id}} {{order_total_krw}}원 — 우선 처리 요망',
                },
            },
        ],
        'enabled': True,
        'priority': 1,
    },
]

# ─────────────────────────────────────────────────────────────
# 고객 윈백 워크플로
# 트리거: customer_churn_risk_event
# 액션: 이탈 위험 고객 → 할인 코드 → 이메일 발송
# ─────────────────────────────────────────────────────────────
customer_win_back_workflow = [
    {
        'rule_id': 'win_back_at_risk',
        'name': '이탈 위험 고객 윈백',
        'trigger': 'customer_churn_risk_event',
        'conditions': [
            {'field': 'segment', 'op': 'eq', 'value': 'AT_RISK'},
        ],
        'actions': [
            {
                'action_type': 'send_email',
                'params': {
                    'template': 'win_back',
                    'discount_pct': 10,
                },
            },
            {
                'action_type': 'log_audit',
                'params': {},
            },
        ],
        'enabled': True,
        'priority': 10,
    },
    {
        'rule_id': 'win_back_dormant',
        'name': '휴면 고객 재활성화',
        'trigger': 'customer_churn_risk_event',
        'conditions': [
            {'field': 'segment', 'op': 'eq', 'value': 'DORMANT'},
        ],
        'actions': [
            {
                'action_type': 'send_email',
                'params': {
                    'template': 'reactivation',
                    'discount_pct': 15,
                },
            },
        ],
        'enabled': True,
        'priority': 20,
    },
]

# 모든 워크플로 모음
ALL_WORKFLOWS = {
    'low_stock_alert': low_stock_alert_workflow,
    'price_change': price_change_workflow,
    'new_order': new_order_workflow,
    'customer_win_back': customer_win_back_workflow,
}
