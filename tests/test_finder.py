"""Tests for oss-contribution-finder."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from oss_contribution_finder import (
    _repo_info,
    build_parser,
    check_contributor_friendly,
    dedupe_by_repo,
    enrich_opportunities,
    format_json,
    format_markdown,
    format_table,
    get_token,
    rate_limit,
    search_issues,
)


def test_build_parser_defaults():
    args = build_parser().parse_args([])
    assert args.language is None
    assert args.topic is None
    assert args.min_stars is None
    assert args.created_after is None
    assert args.updated_after is None
    assert args.sort == "updated"
    assert args.limit == 20
    assert args.format == "table"
    assert args.output_file is None
    assert args.no_enrich is False
    assert args.require_contributing is False
    assert args.check_rate_limit is False
    assert args.retry == 3
    assert args.no_cache is False
    assert args.page == 1
    assert args.per_page is None
    # --label defaults to None rather than ["good first issue"]; the fallback
    # lives in main() so that --label REPLACES the default instead of being
    # ANDed onto it (#60). Asserted as None on purpose: pinning a
    # non-None default here would reintroduce #60.
    assert args.label is None


def test_build_parser_short_and_long_flags():
    args = build_parser().parse_args(
        ["-l", "python", "-t", "rust", "-n", "5", "-f", "json", "-o", "out.json"]
    )
    assert args.language == "python"
    assert args.topic == "rust"
    assert args.limit == 5
    assert args.format == "json"
    assert args.output_file == "out.json"


def test_build_parser_label_replaces_default():
    # #60: --label must REPLACE the default, not accumulate onto it.
    # The parser itself stays out of it (default=None); main() substitutes.
    assert build_parser().parse_args(["--label", "help wanted"]).label == ["help wanted"]
    assert build_parser().parse_args(
        ["--label", "help wanted", "--label", "docs"]
    ).label == ["help wanted", "docs"]


def test_build_parser_rejects_unknown_format():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--format", "yaml"])


def test_build_parser_rejects_non_integer_limit():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--limit", "many"])


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


def test_api_request_cache_ttl_hit_and_expiration():
    import time
    from oss_contribution_finder import api_request, _API_CACHE
    _API_CACHE.clear()
    test_url = "https://api.github.com/ttl-endpoint"

    # Cached 10 seconds ago with TTL 60 -> hit
    now = time.time()
    _API_CACHE[test_url] = ({"ttl": "fresh"}, now - 10)
    res = api_request(test_url, use_cache=True, cache_ttl=60)
    assert res == {"ttl": "fresh"}

    # Cached 100 seconds ago with TTL 60 -> expired, evicted, triggers request
    _API_CACHE[test_url] = ({"ttl": "stale"}, now - 100)
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = b'{"ttl": "renewed"}'
    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = api_request(test_url, use_cache=True, cache_ttl=60)
        assert res == {"ttl": "renewed"}
        # Cache is refreshed with timestamp
        assert test_url in _API_CACHE
        data, ts = _API_CACHE[test_url]
        assert data == {"ttl": "renewed"}
        assert ts >= now - 1
    _API_CACHE.clear()


def test_build_parser_pagination_flags():
    parser = build_parser()
    args = parser.parse_args(["--page", "3", "--per-page", "50"])
    assert args.page == 3
    assert args.per_page == 50


@patch("oss_contribution_finder.api_request")
def test_search_issues_pagination_params(mock_api):
    mock_api.return_value = {"total_count": 0, "items": []}
    search_issues(per_page=25, page=4)
    call_args = mock_api.call_args
    url = call_args[0][0]
    assert "per_page=25" in url
    assert "page=4" in url


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


def test_contributor_signals_from_github_contents():
    entries = [
        {"name": "PULL_REQUEST_TEMPLATE.md", "type": "file"},
        {"name": "ISSUE_TEMPLATE", "type": "dir"},
    ]
    with patch("oss_contribution_finder.api_request", side_effect=[{"type": "file"}, entries]) as api:
        result = check_contributor_friendly("owner/repo")
    assert result == {"has_contributing": True, "has_pr_template": True,
                      "has_issue_template": True}
    assert api.call_count == 2
    assert api.call_args_list[0].args[0].endswith("/repos/owner/repo/contents/CONTRIBUTING.md")
    assert api.call_args_list[1].args[0].endswith("/repos/owner/repo/contents/.github")


def test_pr_template_directory_counts_without_single_file():
    with patch("oss_contribution_finder.api_request", side_effect=[
        {"error": 404}, [{"name": "PULL_REQUEST_TEMPLATE", "type": "dir"}]
    ]):
        assert check_contributor_friendly("owner/repo") == {
            "has_contributing": False, "has_pr_template": True, "has_issue_template": False,
        }


def test_missing_github_directory_has_no_signals():
    with patch("oss_contribution_finder.api_request", side_effect=[
        {"error": 404}, {"error": 404}
    ]):
        assert check_contributor_friendly("owner/repo") == {
            "has_contributing": False, "has_pr_template": False, "has_issue_template": False,
        }


def test_contents_error_is_not_treated_as_missing():
    with patch("oss_contribution_finder.api_request", side_effect=[
        {"error": 403, "rate_limited": True}, {"error": 404}
    ]):
        assert check_contributor_friendly("owner/repo")["has_contributing"] is None


def test_wrong_contents_types_do_not_count_as_templates():
    with patch("oss_contribution_finder.api_request", side_effect=[
        {"type": "dir"}, [
            {"name": "PULL_REQUEST_TEMPLATE.md", "type": "dir"},
            {"name": "ISSUE_TEMPLATE", "type": "file"},
        ]
    ]):
        assert check_contributor_friendly("owner/repo") == {
            "has_contributing": False, "has_pr_template": False, "has_issue_template": False,
        }


def test_contributor_check_passes_token_and_cache_choice():
    with patch("oss_contribution_finder.api_request", side_effect=[
        {"error": 404}, {"error": 404}
    ]) as api:
        check_contributor_friendly("owner/repo", token="secret", use_cache=False)
    assert all(call.kwargs == {"token": "secret", "use_cache": False}
               for call in api.call_args_list)


def test_cli_detects_signals_and_reuses_checks_for_same_repo(capsys):
    items = [{"title": "One", "repository_url": "https://api.github.com/repos/a/b"},
             {"title": "Two", "repository_url": "https://api.github.com/repos/a/b"}]
    with patch("sys.argv", ["finder", "--no-enrich", "--format", "json"]), \
         patch("oss_contribution_finder.get_token", return_value=None), \
         patch("oss_contribution_finder.search_issues", return_value={"items": items}), \
         patch("oss_contribution_finder.api_request", side_effect=[
             {"error": 404}, [{"name": "ISSUE_TEMPLATE", "type": "dir"}]
         ]) as api:
        from oss_contribution_finder import main
        main()
    assert [item["contributor_friendly"] for item in json.loads(capsys.readouterr().out)] == [True, True]
    assert api.call_count == 2


def test_cli_require_contributing_filters_even_with_no_enrich(capsys):
    items = [{"title": "Keep", "repository_url": "https://api.github.com/repos/a/yes"},
             {"title": "Drop", "repository_url": "https://api.github.com/repos/a/no"},
             {"title": "Invalid", "repository_url": "broken"}]
    with patch("sys.argv", ["finder", "--no-enrich", "--require-contributing", "--format", "json"]), \
         patch("oss_contribution_finder.get_token", return_value=None), \
         patch("oss_contribution_finder.search_issues", return_value={"items": items}), \
         patch("oss_contribution_finder.api_request", side_effect=[
             {"type": "file"}, {"error": 404}, {"error": 404}, {"error": 404}
         ]) as api:
        from oss_contribution_finder import main
        main()
    output = json.loads(capsys.readouterr().out)
    assert [item["title"] for item in output] == ["Keep"]
    assert output[0]["contributor_friendly"] is True
    assert api.call_count == 4


def test_cli_without_filter_keeps_missing_repos(capsys):
    item = {"title": "Still here", "repository_url": "https://api.github.com/repos/a/b"}
    with patch("sys.argv", ["finder", "--no-enrich", "--format", "json"]), \
         patch("oss_contribution_finder.get_token", return_value=None), \
         patch("oss_contribution_finder.search_issues", return_value={"items": [item]}), \
         patch("oss_contribution_finder.api_request", side_effect=[{"error": 404}, {"error": 404}]):
        from oss_contribution_finder import main
        main()
    assert json.loads(capsys.readouterr().out)[0]["contributor_friendly"] is False


def test_cli_api_error_warns_and_does_not_pass_filter(capsys):
    item = {"title": "Unverified", "repository_url": "https://api.github.com/repos/a/b"}
    with patch("sys.argv", ["finder", "--no-enrich", "--require-contributing", "--format", "json"]), \
         patch("oss_contribution_finder.get_token", return_value=None), \
         patch("oss_contribution_finder.search_issues", return_value={"items": [item]}), \
         patch("oss_contribution_finder.api_request", side_effect=[
             {"error": 403}, {"error": 404}
         ]):
        from oss_contribution_finder import main
        main()
    output = capsys.readouterr()
    assert json.loads(output.out) == []
    assert "could not be fully checked" in output.err


def test_formatters_show_detected_signal():
    item = {"title": "Fix", "html_url": "https://github.com/a/b/issues/1",
            "repository_url": "https://api.github.com/repos/a/b", "contributor_friendly": True}
    assert "Yes" in format_table([item])
    assert "Contributor-friendly**: Yes" in format_markdown([item])
