"""Tests for oss-contribution-finder."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from oss_contribution_finder import (
    _repo_info,
    dedupe_by_repo,
    enrich_opportunities,
    format_json,
    format_markdown,
    format_table,
    get_token,
    rate_limit,
    search_issues,
)


def test_get_token_from_env():
    with patch.dict(os.environ, {"GH_TOKEN": "test_token_123"}):
        assert get_token() == "test_token_123"


def test_get_token_from_github_env():
    with patch.dict(os.environ, {"GITHUB_TOKEN": "test_token_456"}):
        assert get_token() == "test_token_456"


def test_get_token_missing():
    with patch.dict(os.environ, {}, clear=True):
        assert get_token() is None


def test_format_table_empty():
    result = format_table([])
    assert "No opportunities found" in result


def test_format_table_with_data():
    opportunities = [
        {
            "repo": {"full_name": "test/repo", "stargazers_count": 42},
            "title": "Fix bug in parser",
            "html_url": "https://github.com/test/repo/issues/1",
        }
    ]
    result = format_table(opportunities)
    assert "test/repo" in result
    assert "Fix bug in parser" in result
    assert "42" in result


def test_format_markdown_empty():
    result = format_markdown([])
    assert "No opportunities found" in result


def test_format_markdown_with_data():
    opportunities = [
        {
            "repo": {
                "full_name": "test/repo",
                "html_url": "https://github.com/test/repo",
                "description": "A test repo",
                "stargazers_count": 100,
                "language": "Python",
            },
            "title": "Fix bug",
            "html_url": "https://github.com/test/repo/issues/1",
            "labels": ["good first issue", "bug"],
            "updated_at": "2026-09-01T12:00:00Z",
        }
    ]
    result = format_markdown(opportunities)
    assert "test/repo" in result
    assert "Fix bug" in result
    assert "good first issue" in result
    assert "Python" in result


def test_format_json_empty():
    result = format_json([])
    assert result == "[]"


def test_format_json_with_data():
    opportunities = [{"title": "Test", "repo": {"full_name": "test/repo"}}]
    result = format_json(opportunities)
    parsed = json.loads(result)
    assert len(parsed) == 1
    assert parsed[0]["title"] == "Test"


def test_dedupe_by_repo_no_dedup():
    opportunities = [
        {"repo": {"full_name": "repo/a"}},
        {"repo": {"full_name": "repo/b"}},
    ]
    result = dedupe_by_repo(opportunities, max_per_repo=3)
    assert len(result) == 2


def test_dedupe_by_repo_limits_per_repo():
    opportunities = [
        {"repo": {"full_name": "repo/a"}},
        {"repo": {"full_name": "repo/a"}},
        {"repo": {"full_name": "repo/a"}},
        {"repo": {"full_name": "repo/a"}},
    ]
    result = dedupe_by_repo(opportunities, max_per_repo=2)
    assert len(result) == 2


def test_dedupe_by_repo_mixed():
    opportunities = [
        {"repo": {"full_name": "repo/a"}},
        {"repo": {"full_name": "repo/a"}},
        {"repo": {"full_name": "repo/b"}},
        {"repo": {"full_name": "repo/a"}},
    ]
    result = dedupe_by_repo(opportunities, max_per_repo=2)
    assert len(result) == 3  # 2 from repo/a + 1 from repo/b


@patch("oss_contribution_finder.api_request")
def test_search_issues_basic(mock_api):
    mock_api.return_value = {
        "total_count": 1,
        "items": [
            {
                "title": "Fix bug",
                "html_url": "https://github.com/test/repo/issues/1",
                "repository_url": "https://api.github.com/repos/test/repo",
                "labels": [{"name": "good first issue"}],
                "updated_at": "2026-09-01T12:00:00Z",
            }
        ],
    }
    result = search_issues(labels=["good first issue"], language="python")
    assert result["total_count"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "Fix bug"


@patch("oss_contribution_finder.api_request")
def test_search_issues_with_filters(mock_api):
    mock_api.return_value = {"total_count": 0, "items": []}
    search_issues(
        labels=["good first issue", "help wanted"],
        language="rust",
        topic="cli",
        min_stars=100,
        created_after="2026-01-01",
        updated_after="2026-08-01",
    )
    # Verify the API was called with correct parameters
    call_args = mock_api.call_args
    url = call_args[0][0]
    assert "label%3A%22good%20first%20issue%22" in url
    assert "label%3A%22help%20wanted%22" in url
    assert "language%3Arust" in url
    assert "topic%3Acli" in url
    assert "stars%3A%3E%3D100" in url


@patch("oss_contribution_finder.api_request")
def test_rate_limit(mock_api):
    mock_api.return_value = {
        "resources": {
            "core": {"limit": 5000, "remaining": 4999},
            "search": {"limit": 30, "remaining": 29},
        }
    }
    result = rate_limit()
    assert result["resources"]["core"]["limit"] == 5000


def test_output_file_flag(tmp_path):
    """Test writing output directly to a file using --output."""
    import argparse
    from unittest.mock import patch

    out_file = tmp_path / "output.md"
    sample_items = [
        {
            "html_url": "https://github.com/foo/bar/issues/1",
            "title": "Fix issue",
            "labels": [{"name": "bug"}],
            "repository_url": "https://api.github.com/repos/foo/bar",
            "_stars": 42,
            "_lang": "Python",
        }
    ]

    test_args = ["oss_finder", "--format", "markdown", "-o", str(out_file)]
    with patch("sys.argv", test_args):
        with patch("oss_contribution_finder.get_token", return_value=None):
            with patch("oss_contribution_finder.search_issues", return_value={"items": sample_items}):
                import oss_contribution_finder
                oss_contribution_finder.main()

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Fix issue" in content
    assert "foo/bar" in content


def test_api_request_caching():
    from oss_contribution_finder import api_request, _API_CACHE
    _API_CACHE.clear()
    test_url = "https://api.github.com/test-endpoint"
    _API_CACHE[test_url] = {"cached": True}
    res = api_request(test_url, use_cache=True)
    assert res == {"cached": True}
    _API_CACHE.clear()


@patch("urllib.request.urlopen")
def test_api_request_retry_on_rate_limit(mock_urlopen):
    import urllib.error
    from oss_contribution_finder import api_request, _API_CACHE
    _API_CACHE.clear()

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = b'{"success": true}'

    fp = MagicMock()
    fp.read.return_value = b'rate limit exceeded'
    err = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, fp)

    mock_urlopen.side_effect = [err, mock_resp]

    with patch("time.sleep") as mock_sleep:
        res = api_request("https://api.github.com/rate-limited-endpoint", retries=2, use_cache=False)
        assert res == {"success": True}
        assert mock_sleep.called


def test_repo_info_with_existing_repo_dict():
    opp = {"repo": {"full_name": "custom/repo", "stargazers_count": 99}}
    info = _repo_info(opp)
    assert info["full_name"] == "custom/repo"
    assert info["stargazers_count"] == 99


def test_repo_info_standard_api_url():
    opp = {"repository_url": "https://api.github.com/repos/owner/my-repo"}
    info = _repo_info(opp)
    assert info["full_name"] == "owner/my-repo"
    assert info["html_url"] == "https://github.com/owner/my-repo"


def test_repo_info_trailing_slash():
    opp = {"repository_url": "https://api.github.com/repos/owner/my-repo/"}
    info = _repo_info(opp)
    assert info["full_name"] == "owner/my-repo"
    assert info["html_url"] == "https://github.com/owner/my-repo"


def test_repo_info_query_params_and_fragments():
    opp = {"repository_url": "https://api.github.com/repos/owner/my-repo?ref=main&page=1#heading"}
    info = _repo_info(opp)
    assert info["full_name"] == "owner/my-repo"
    assert info["html_url"] == "https://github.com/owner/my-repo"


def test_repo_info_git_suffix():
    opp = {"repository_url": "https://github.com/owner/my-repo.git"}
    info = _repo_info(opp)
    assert info["full_name"] == "owner/my-repo"
    assert info["html_url"] == "https://github.com/owner/my-repo"


def test_repo_info_git_suffix_with_trailing_slash():
    opp = {"repository_url": "https://github.com/owner/my-repo.git/"}
    info = _repo_info(opp)
    assert info["full_name"] == "owner/my-repo"


def test_repo_info_ssh_format():
    opp = {"repository_url": "git@github.com:owner/my-repo.git"}
    info = _repo_info(opp)
    assert info["full_name"] == "owner/my-repo"
    assert info["html_url"] == "https://github.com/owner/my-repo"


def test_repo_info_empty_or_missing_or_none():
    assert _repo_info({})["full_name"] == "unknown/unknown"
    assert _repo_info({"repository_url": None})["full_name"] == "unknown/unknown"
    assert _repo_info({"repository_url": ""})["full_name"] == "unknown/unknown"
    assert _repo_info({"repository_url": "   "})["full_name"] == "unknown/unknown"


def test_repo_info_short_paths():
    assert _repo_info({"repository_url": "https://github.com/"})["full_name"] == "unknown/unknown"
    assert _repo_info({"repository_url": "https://github.com/owner"})["full_name"] == "unknown/unknown"


@patch("oss_contribution_finder.get_repo_info")
def test_enrich_opportunities_with_trailing_slashes_and_params(mock_get_repo):
    mock_get_repo.return_value = {"full_name": "owner/repo", "stargazers_count": 10}
    opportunities = [
        {"repository_url": "https://api.github.com/repos/owner/repo/?param=1"},
        {"repository_url": "https://github.com/owner/repo.git"},
        {"repository_url": "invalid-url"},
    ]
    enriched = enrich_opportunities(opportunities)
    assert len(enriched) == 1
    assert enriched[0]["repo"]["full_name"] == "owner/repo"
    mock_get_repo.assert_called_once_with("owner/repo", token=None)
