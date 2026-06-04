from __future__ import annotations


def test_compute_onboarding_state_zero_step():
    from src.seller_console.onboarding import compute_onboarding_state

    state = compute_onboarding_state(connected_markets=0, source_count=0, product_count=0)
    assert state["completed_steps"] == 0
    assert state["progress_percent"] == 0
    assert state["visible"] is True
    assert state["steps"][0]["is_next"] is True


def test_compute_onboarding_state_one_step():
    from src.seller_console.onboarding import compute_onboarding_state

    state = compute_onboarding_state(connected_markets=1, source_count=0, product_count=0)
    assert state["completed_steps"] == 1
    assert state["progress_percent"] == 33
    assert state["steps"][1]["is_next"] is True


def test_compute_onboarding_state_two_step():
    from src.seller_console.onboarding import compute_onboarding_state

    state = compute_onboarding_state(connected_markets=1, source_count=2, product_count=0)
    assert state["completed_steps"] == 2
    assert state["progress_percent"] == 66
    assert state["steps"][2]["is_next"] is True


def test_compute_onboarding_state_three_step_complete_hidden():
    from src.seller_console.onboarding import compute_onboarding_state

    state = compute_onboarding_state(connected_markets=1, source_count=1, product_count=1)
    assert state["completed_steps"] == 3
    assert state["is_completed"] is True
    assert state["visible"] is False
    assert state["show_completion_notice"] is True


def test_compute_onboarding_state_dismissed_hidden():
    from src.seller_console.onboarding import compute_onboarding_state

    state = compute_onboarding_state(connected_markets=0, source_count=0, product_count=0, dismissed=True)
    assert state["dismissed"] is True
    assert state["visible"] is False
    assert state["show_completion_notice"] is False
