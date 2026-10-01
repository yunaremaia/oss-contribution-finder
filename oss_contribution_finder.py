#!/usr/bin/env python3
"""OSS Contribution Finder — discover good-first-issue opportunities.

Searches GitHub for open-source projects with "good first issue" labels,
filtered by language, activity, and topic. Outputs a ranked list of
opportunities ready for contribution.

Usage:
    oss-contribution-finder --language python --limit 10
    oss-contribution-finder --topic rust --min-stars 100 --format json
    oss-contribution-finder --language go --format markdown >> opportunities.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Any

# Simple in-memory response cache to reduce duplicate API calls
_API_CACHE: dict[str, Any] = {}


GITHUB_API = "https://api.github.com"
SEARCH_ENDPOINT = f"{GITHUB_API}/search/issues"


def get_token() -> str | None:
    """Get GitHub token from environment."""
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def api_request(
    url: str,
    token: str | None = None,
    retries: int = 3,
    use_cache: bool = True,
) -> dict | list:
    """Make an authenticated API request with rate limit handling, retry, and caching."""
    if use_cache and url in _API_CACHE:
        return _API_CACHE[url]

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(max(1, retries)):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                if use_cache:
                    _API_CACHE[url] = data
                return data
        except urllib.error.HTTPError as e:
            raw_body = e.read().decode(errors="ignore") if e.fp else ""
            # Check for primary or secondary rate limit (403 or 429)
            is_rate_limit = (
                e.code == 429
                or (e.code == 403 and any(k in raw_body.lower() for k in ["rate limit", "rate-limit", "secondary rate"]))
            )

            if is_rate_limit:
                reset_header = e.headers.get("X-RateLimit-Reset") if hasattr(e, "headers") and e.headers else None
                if reset_header and str(reset_header).isdigit():
                    wait_seconds = max(1.0, float(reset_header) - time.time())
                else:
                    wait_seconds = float(2 ** attempt)

                sleep_time = min(wait_seconds, 60.0)

                if attempt < retries - 1:
                    time.sleep(sleep_time)
                    continue

                return {
                    "error": e.code,
                    "rate_limited": True,
                    "message": f"GitHub API rate limit exceeded (HTTP {e.code}). Reset in {int(wait_seconds)}s. Use a GitHub token with GH_TOKEN to increase limits.",
                }

            return {"error": e.code, "message": raw_body}
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(float(2 ** attempt))
                continue
            return {"error": str(e)}

    return {"error": "Max retries exceeded"}


def search_issues(
    *,
    labels: list[str] | None = None,
    language: str | None = None,
    topic: str | None = None,
    min_stars: int | None = None,
    created_after: str | None = None,
    updated_after: str | None = None,
    sort: str = "updated",
    order: str = "desc",
    per_page: int = 30,
    page: int = 1,
    token: str | None = None,
    retries: int = 3,
    use_cache: bool = True,
) -> dict:
    """Search GitHub issues with filters."""
    query_parts = ["state:open", "is:issue"]

    if labels:
        for label in labels:
            query_parts.append(f'label:"{label}"')
    if language:
        query_parts.append(f"language:{language}")
    if topic:
        query_parts.append(f"topic:{topic}")
    if min_stars:
        query_parts.append(f"stars:>={min_stars}")
    if created_after:
        query_parts.append(f"created:>={created_after}")
    if updated_after:
        query_parts.append(f"updated:>={updated_after}")

    query = " ".join(query_parts)
    params = (
        f"q={urllib.parse.quote(query)}"
        f"&sort={sort}&order={order}"
        f"&per_page={per_page}&page={page}"
    )
    url = f"{SEARCH_ENDPOINT}?{params}"
    return api_request(url, token=token, retries=retries, use_cache=use_cache)


def get_repo_info(full_name: str, token: str | None = None) -> dict:
    """Get repository metadata."""
    url = f"{GITHUB_API}/repos/{full_name}"
    return api_request(url, token=token)


def check_contributor_friendly(
    full_name: str, token: str | None = None, use_cache: bool = True,
) -> dict[str, bool | None]:
    """Detect root CONTRIBUTING.md and templates; None means an API error."""
    base = f"{GITHUB_API}/repos/{full_name}/contents"
    contributing = api_request(f"{base}/CONTRIBUTING.md", token=token, use_cache=use_cache)
    github = api_request(f"{base}/.github", token=token, use_cache=use_cache)

    def present(response: dict | list, kind: str) -> bool | None:
        if isinstance(response, dict) and "error" in response:
            return False if response["error"] == 404 else None
        return isinstance(response, dict) and response.get("type") == kind

    has_contributing = present(contributing, "file")
    if isinstance(github, list):
        has_pr_template = any(
            isinstance(entry, dict)
            and (
                (entry.get("name") == "PULL_REQUEST_TEMPLATE.md" and entry.get("type") == "file")
                or (entry.get("name") == "PULL_REQUEST_TEMPLATE" and entry.get("type") == "dir")
            )
            for entry in github
        )
        has_issue_template = any(
            isinstance(entry, dict)
            and entry.get("name") == "ISSUE_TEMPLATE"
            and entry.get("type") == "dir"
            for entry in github
        )
    else:
        error = github.get("error") if isinstance(github, dict) else None
        has_pr_template = has_issue_template = False if error == 404 else None

    return {
        "has_contributing": has_contributing,
        "has_pr_template": has_pr_template,
        "has_issue_template": has_issue_template,
    }


def rate_limit(token: str | None = None) -> dict:
    """Check current rate limit status."""
    url = f"{GITHUB_API}/rate_limit"
    return api_request(url, token=token)


def _repo_info(opp: dict[str, Any]) -> dict[str, Any]:
    """Return repo metadata, falling back to repository_url when enrich was skipped."""
    repo = opp.get("repo")
    if isinstance(repo, dict) and repo.get("full_name"):
        return repo
    repo_url = opp.get("repository_url") or ""
    if not isinstance(repo_url, str):
        repo_url = ""
    parsed = urllib.parse.urlparse(repo_url.strip())
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4].rstrip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        owner = parts[-2]
        if ":" in owner:
            owner = owner.split(":")[-1]
        repo_name = parts[-1]
        full_name = f"{owner}/{repo_name}"
    else:
        full_name = "unknown/unknown"
    return {
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "stargazers_count": 0,
        "language": "Unknown",
        "description": None,
    }


def format_markdown(opportunities: list[dict]) -> str:
    """Format opportunities as markdown."""
    if not opportunities:
        return "# No opportunities found\n"

    lines = ["# OSS Contribution Opportunities\n"]
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")

    for i, opp in enumerate(opportunities, 1):
        repo = _repo_info(opp)
        lines.append(f"## {i}. [{repo['full_name']}]({repo['html_url']})")
        if repo.get("description"):
            lines.append(f"_{repo['description']}_")
        lines.append(f"- **Issue**: [{opp['title']}]({opp['html_url']})")
        labels = opp.get("labels", [])
        if labels and isinstance(labels[0], dict):
            labels = [l.get("name", "") for l in labels]
        lines.append(f"- **Labels**: {', '.join(labels)}")
        lines.append(f"- **Stars**: ⭐ {repo.get('stargazers_count', '?')}")
        lines.append(f"- **Language**: {repo.get('language', 'Unknown')}")
        if "contributor_friendly" in opp:
            lines.append(f"- **Contributor-friendly**: {'Yes' if opp['contributor_friendly'] else 'No'}")
        lines.append(f"- **Updated**: {opp.get('updated_at', '?')[:10]}")
        lines.append("")

    return "\n".join(lines)


def format_json(opportunities: list[dict]) -> str:
    """Format opportunities as JSON."""
    return json.dumps(opportunities, indent=2)


def format_table(opportunities: list[dict]) -> str:
    """Format opportunities as a readable table."""
    if not opportunities:
        return "No opportunities found."

    lines = []
    lines.append(f"{'#':>3} {'Repository':<40} {'Stars':>6} {'Title':<50} {'Friendly':<8}")
    lines.append("-" * 114)

    for i, opp in enumerate(opportunities, 1):
        repo = _repo_info(opp)
        repo_name = repo["full_name"]
        stars = repo.get("stargazers_count", 0)
        title = opp["title"][:47] + "..." if len(opp["title"]) > 50 else opp["title"]
        friendly = "?"
        if "contributor_friendly" in opp:
            friendly = "Yes" if opp["contributor_friendly"] else "No"
        lines.append(f"{i:>3} {repo_name:<40} {stars:>6} {title:<50} {friendly:<8}")

    return "\n".join(lines)


def dedupe_by_repo(opportunities: list[dict], max_per_repo: int = 3) -> list[dict]:
    """Limit opportunities per repository."""
    counts: dict[str, int] = {}
    result = []
    for opp in opportunities:
        repo = _repo_info(opp)["full_name"]
        count = counts.get(repo, 0)
        if count < max_per_repo:
            result.append(opp)
            counts[repo] = count + 1
    return result


def enrich_opportunities(
    opportunities: list[dict],
    token: str | None = None,
    max_repos: int = 10,
) -> list[dict]:
    """Fetch repo metadata for opportunities (rate-limit aware)."""
    seen = set()
    enriched = []
    for opp in opportunities:
        full_name = _repo_info(opp)["full_name"]
        if full_name == "unknown/unknown" or full_name in seen:
            continue
        seen.add(full_name)
        if len(seen) > max_repos:
            break
        info = get_repo_info(full_name, token=token)
        if "error" not in info:
            opp["repo"] = info
            enriched.append(opp)
    return enriched


def main():
    parser = argparse.ArgumentParser(
        description="Find OSS contribution opportunities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  oss-contribution-finder --language python --limit 10
  oss-contribution-finder --topic rust --min-stars 100 --format json
  oss-contribution-finder --language go --format markdown >> opportunities.md
        """,
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    parser.add_argument(
        "--label",
        action="append",
        default=["good first issue"],
        help="Labels to filter (default: 'good first issue')",
    )
    parser.add_argument("--language", "-l", help="Programming language filter")
    parser.add_argument("--topic", "-t", help="GitHub topic filter")
    parser.add_argument("--min-stars", type=int, help="Minimum star count")
    parser.add_argument(
        "--created-after",
        help="Only issues created after date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--updated-after",
        help="Only issues updated after date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--sort",
        choices=["comments", "reactions", "updated"],
        default="updated",
        help="Sort field (default: updated)",
    )
    parser.add_argument("--limit", "-n", type=int, default=20, help="Max results")
    parser.add_argument(
        "--format",
        "-f",
        choices=["table", "markdown", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output_file",
        help="Write output to a file instead of stdout",
    )

    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip fetching repo metadata (faster, less info)",
    )
    parser.add_argument(
        "--require-contributing",
        action="store_true",
        help="Only show repositories with a root CONTRIBUTING.md",
    )
    parser.add_argument(
        "--check-rate-limit",
        action="store_true",
        help="Check rate limit and exit",
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=3,
        help="Maximum retry attempts on rate limit or network error (default: 3)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable response caching for API requests",
    )

    args = parser.parse_args()
    token = get_token()

    if args.check_rate_limit:
        rl = rate_limit(token=token)
        core = rl.get("resources", {}).get("core", {})
        search = rl.get("resources", {}).get("search", {})
        print(f"Core: {core.get('remaining', '?')}/{core.get('limit', '?')} (resets at {core.get('reset', '?')})")
        print(f"Search: {search.get('remaining', '?')}/{search.get('limit', '?')} (resets at {search.get('reset', '?')})")
        return

    # Default: only recent issues (last 30 days)
    if not args.updated_after:
        args.updated_after = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    per_page = min(args.limit, 100)
    result = search_issues(
        labels=args.label,
        language=args.language,
        topic=args.topic,
        min_stars=args.min_stars,
        created_after=args.created_after,
        updated_after=args.updated_after,
        sort=args.sort,
        per_page=per_page,
        token=token,
        retries=args.retry,
        use_cache=not args.no_cache,
    )

    if "error" in result:
        msg = result.get("message") or str(result)
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)

    items = result.get("items", [])

    # Enrich with repo metadata
    if not args.no_enrich and token:
        items = enrich_opportunities(items, token=token, max_repos=args.limit)

    # Search can return several issues per repo; check its files only once.
    signals_by_repo: dict[str, dict[str, bool | None]] = {}
    filtered = []
    for item in items:
        full_name = _repo_info(item)["full_name"]
        parts = full_name.split("/") if isinstance(full_name, str) else []
        if len(parts) != 2 or not all(parts) or full_name == "unknown/unknown":
            signals = {
                "has_contributing": None,
                "has_pr_template": None,
                "has_issue_template": None,
            }
        else:
            if full_name not in signals_by_repo:
                signals_by_repo[full_name] = check_contributor_friendly(
                    full_name, token=token, use_cache=not args.no_cache,
                )
            signals = signals_by_repo[full_name]
        if None in signals.values():
            print(f"Warning: contributor signals could not be fully checked for {full_name}", file=sys.stderr)
        if args.require_contributing and signals["has_contributing"] is not True:
            continue
        item["contributor_friendly"] = any(value is True for value in signals.values())
        filtered.append(item)
    items = filtered

    # Format output
    formatters = {
        "table": format_table,
        "markdown": format_markdown,
        "json": format_json,
    }
    output = formatters[args.format](items)
    if getattr(args, "output_file", None):
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(output)
            if not output.endswith("\n"):
                f.write("\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
