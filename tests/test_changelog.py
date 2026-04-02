"""Tests for scripts/generate_changelog.py."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from generate_changelog import categorize_commits, generate_markdown


class TestCategorizeCommits:
    def test_categorize_commits_features(self):
        commits = ["feat: add new endpoint", "feature: support OAuth"]
        features, fixes, other = categorize_commits(commits)
        assert features == commits
        assert fixes == []
        assert other == []

    def test_categorize_commits_fixes(self):
        commits = ["fix: correct null check", "bugfix: handle empty list"]
        features, fixes, other = categorize_commits(commits)
        assert features == []
        assert fixes == commits
        assert other == []

    def test_categorize_commits_other(self):
        commits = ["chore: update deps", "docs: improve README", "refactor: clean up"]
        features, fixes, other = categorize_commits(commits)
        assert features == []
        assert fixes == []
        assert other == commits


class TestGenerateMarkdown:
    def test_generate_markdown_structure(self):
        features = ["feat: shiny new thing"]
        fixes = ["fix: broken widget"]
        other = ["chore: tidy up"]
        md = generate_markdown(features, fixes, other)
        assert "## Features" in md
        assert "## Bug Fixes" in md
        assert "## Other" in md
        assert "feat: shiny new thing" in md
        assert "fix: broken widget" in md
        assert "chore: tidy up" in md

    def test_generate_markdown_empty(self):
        md = generate_markdown([], [], [])
        assert "No changes" in md
        # Should still have a title line
        assert md.startswith("#")

    def test_generate_markdown_with_tag(self):
        md = generate_markdown(["feat: something"], [], [], tag_name="v1.2.3")
        assert "v1.2.3" in md

    def test_generate_markdown_no_tag(self):
        md = generate_markdown([], ["fix: oops"], [])
        assert "Changelog" in md
        assert "## Bug Fixes" in md
