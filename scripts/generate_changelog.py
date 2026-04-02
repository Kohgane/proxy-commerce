#!/usr/bin/env python3
"""Generate changelog from git commit messages."""
import subprocess
import sys
from datetime import date


def get_previous_tag():
    """Return the previous git tag, or None if there isn't one."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0", "HEAD^"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_commits_since(tag):
    """Return a list of oneline commit messages since *tag*.

    If *tag* is None, returns all commits in the repo.
    """
    if tag:
        rev_range = f"{tag}..HEAD"
    else:
        rev_range = "HEAD"

    result = subprocess.run(
        ["git", "log", rev_range, "--oneline", "--no-merges"],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.strip().splitlines()
    # Strip the leading commit hash from each line.
    commits = []
    for line in lines:
        if line:
            parts = line.split(" ", 1)
            commits.append(parts[1] if len(parts) > 1 else line)
    return commits


def categorize_commits(commits):
    """Split commits into (features, fixes, other) lists."""
    features = []
    fixes = []
    other = []

    for commit in commits:
        lower = commit.lower()
        if lower.startswith(("feat:", "feature:")):
            features.append(commit)
        elif lower.startswith(("fix:", "bugfix:")):
            fixes.append(commit)
        else:
            other.append(commit)

    return features, fixes, other


def generate_markdown(features, fixes, other, tag_name=None):
    """Render a Markdown changelog string."""
    today = date.today().isoformat()
    title = f"Release {tag_name}" if tag_name else "Changelog"
    lines = [f"# {title}", "", f"*{today}*", ""]

    if features:
        lines.append("## Features")
        lines.append("")
        for commit in features:
            lines.append(f"- {commit}")
        lines.append("")

    if fixes:
        lines.append("## Bug Fixes")
        lines.append("")
        for commit in fixes:
            lines.append(f"- {commit}")
        lines.append("")

    if other:
        lines.append("## Other")
        lines.append("")
        for commit in other:
            lines.append(f"- {commit}")
        lines.append("")

    if not features and not fixes and not other:
        lines.append("*No changes.*")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    tag_name = None
    # Allow an explicit tag name to be passed as an argument (e.g. from the
    # release workflow where ${{ github.ref_name }} is known).
    if len(sys.argv) > 1:
        tag_name = sys.argv[1]

    prev_tag = get_previous_tag()
    commits = get_commits_since(prev_tag)
    features, fixes, other = categorize_commits(commits)
    print(generate_markdown(features, fixes, other, tag_name=tag_name))
