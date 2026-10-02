"""Regression tests for the --label default contract (#60).

The documented behaviour (README) is: ``--label`` is repeatable and defaults to
``good first issue``. Before #60 the parser used ``action="append"`` with
``default=["good first issue"]``, so argparse seeded the list with the default
and then appended the user's labels to it. Every ``--label`` was therefore ANDed
with ``good first issue`` and could never replace it.

These tests drive the real ``main()`` so they cover both halves of the fix: the
parser must leave ``args.label`` as ``None`` when the flag is absent, and
``main()`` must apply the default afterwards.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import oss_contribution_finder as ocf


def _labels_for(argv):
    """Run main() with argv and return the labels handed to search_issues()."""
    captured = {}

    def fake_search_issues(**kwargs):
        captured.update(kwargs)
        return {"total_count": 0, "items": []}

    with patch.object(sys, "argv", ["oss-contribution-finder", "--no-cache"] + argv), \
            patch.object(ocf, "search_issues", fake_search_issues), \
            patch.object(ocf, "get_token", lambda: "test_token"):
        ocf.main()
    return captured["labels"]


def test_default_label_applied_when_flag_absent():
    """No --label must search 'good first issue'."""
    assert _labels_for([]) == ["good first issue"]


def test_single_label_replaces_default():
    """A user-supplied --label must REPLACE the default, not AND with it."""
    assert _labels_for(["--label", "bug"]) == ["bug"]


def test_repeated_labels_accumulate_without_default():
    """Repeating --label accumulates the user's labels, still without the default."""
    assert _labels_for(["--label", "a", "--label", "b"]) == ["a", "b"]


def test_default_is_not_leaked_into_explicit_labels():
    """Regression guard: 'good first issue' must never appear when it was not asked for."""
    labels = _labels_for(["--label", "documentation"])
    assert "good first issue" not in labels