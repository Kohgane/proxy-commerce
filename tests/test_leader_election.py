from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_leader_election_acquire_and_is_leader(tmp_path):
    from src.scheduler.leader_election import acquire_leadership, is_leader

    lock = tmp_path / "leader.lock"
    assert acquire_leadership(lock, ttl_seconds=2) is True
    assert is_leader(lock) is True


def test_leader_election_ttl_takeover(tmp_path):
    from src.scheduler.leader_election import acquire_leadership

    lock = tmp_path / "leader.lock"
    assert acquire_leadership(lock, ttl_seconds=1) is True
    time.sleep(1.1)
    assert acquire_leadership(lock, ttl_seconds=1) is True
