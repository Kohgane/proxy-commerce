from __future__ import annotations

from src.seo.robots_generator import RobotsGenerator


def test_robots_allows_privacy_and_terms():
    content = RobotsGenerator(base_url="https://example.com").generate()
    assert "Allow: /privacy" in content
    assert "Allow: /terms" in content
