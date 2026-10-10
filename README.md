# OSS Contribution Finder
[![CI](https://github.com/yunaremaia/oss-contribution-finder/actions/workflows/ci.yml/badge.svg)](https://github.com/yunaremaia/oss-contribution-finder/actions) ![py](https://img.shields.io/badge/python-3.10-blue.svg) ![release](https://img.shields.io/github/v/release/yunaremaia/oss-contribution-finder)
[![License](https://img.shields.io/github/license/yunaremaia/oss-contribution-finder) ![Stars](https://img.shields.io/github/stars/yunaremaia/oss-contribution-finder)](https://github.com/yunaremaia/oss-contribution-finder/blob/main/LICENSE)


Find open-source contribution opportunities via the GitHub API.

Searches for issues labeled "good first issue" (or any label you choose), filtered by language, topic, star count, and activity. Outputs a ranked list ready for contribution.

## Install

```bash
pip install git+https://github.com/yunaremaia/oss-contribution-finder.git
```

> **Not yet on PyPI.** Install from git with the line above. A PyPI release is
> pending; the distribution name `oss-contribution-finder` is currently free.

## Usage

```bash
# Find Python good-first-issues
oss-contribution-finder --language python --limit 10

# Find Rust CLI projects with 100+ stars
oss-contribution-finder --language rust --topic cli --min-stars 100

# Export as markdown
oss-contribution-finder --language go --format markdown >> opportunities.md

# JSON output for automation
oss-contribution-finder --language typescript --format json --limit 50

# Only show issues from repositories with a root CONTRIBUTING.md
oss-contribution-finder --language python --require-contributing

# Check rate limit status
oss-contribution-finder --check-rate-limit
```

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `--label` | Labels to filter (repeatable) | `good first issue` |
| `--language`, `-l` | Programming language | - |
| `--topic`, `-t` | GitHub topic | - |
| `--min-stars` | Minimum star count | - |
| `--created-after` | Issues created after (YYYY-MM-DD) | - |
| `--updated-after` | Issues updated after (YYYY-MM-DD) | 30 days ago |
| `--sort` | Sort field (`comments`, `reactions`, `updated`) | `updated` |
| `--limit`, `-n` | Max results | 20 |
| `--page` | Results page number | 1 |
| `--per-page` | Items per page (1-100) | `min(limit, 100)` |
| `--format`, `-f` | Output (`table`, `markdown`, `json`) | `table` |
| `--no-enrich` | Skip repo metadata (faster) | false |
| `--require-contributing` | Only include repos with a root `CONTRIBUTING.md` | false |
| `--check-rate-limit` | Show rate limit and exit | - |
| `--retry` | Max retry attempts on rate limits or network errors | 3 |
| `--no-cache` | Disable in-memory API caching (default TTL: 1 hour) | false |

## Caching

API responses are cached in memory with a default TTL of 1 hour (3600 seconds) to avoid redundant requests during repeated operations. Use `--no-cache` to bypass cached responses and fetch fresh data directly from GitHub.

## Authentication

Set `GH_TOKEN` or `GITHUB_TOKEN` in your environment to avoid rate limits:

```bash
export GH_TOKEN=ghp_your_token_here
```

Without a token, searches are limited to 10 requests per minute.

Results include a `contributor_friendly` boolean in JSON (and a Friendly column
in the table / line in Markdown). It is true when a repository has a root
`CONTRIBUTING.md`, a `.github/PULL_REQUEST_TEMPLATE.md` file, a
`.github/PULL_REQUEST_TEMPLATE/` directory, or a `.github/ISSUE_TEMPLATE/`
directory. Detection uses up to two additional GitHub API requests per unique
repository, even with `--no-enrich` or no token. `--require-contributing`
filters on the root file specifically, not on the broader friendly signal.
API errors emit a warning; results may then be incomplete, and the filter
excludes repositories whose root file it cannot verify.

## Examples

```bash
# Find documentation contributions
oss-contribution-finder --label "good first issue" --label "documentation" --limit 15

# Find recently updated Python issues in AI/ML
oss-contribution-finder --language python --topic machine-learning --updated-after 2026-08-01

# Generate a weekly digest
oss-contribution-finder --language rust --format markdown --limit 25 > weekly-opportunities.md
```

## Sponsoring

`oss-contribution-finder` is MIT licensed and free to use. If it saved you time, you can support continued maintenance via GitHub Sponsors or by sending SOL to the project treasury wallet:

```text
Eeztv1nCYUt1fwGWpzKC948gaWfjejYCAuLtUMgzDWbW
```

Funding platforms are configured in [`.github/FUNDING.yml`](.github/FUNDING.yml).

If this tool is useful to you, a star helps other people find it.

## Related tools

- **[gfi](https://github.com/yunaremaia/gfi)** — find well-scoped good first issues to start on
- **[aipr](https://github.com/yunaremaia/aipr)** — pre-screen repos for AI contribution policy
- **[ghstats](https://github.com/yunaremaia/ghstats)** — generate a GitHub stats dashboard
- **[agent-guard](https://github.com/yunaremaia/agent-guard)** — enforce guardrails on AI agent tool calls

Part of a family of focused, single-purpose developer tools — each one does one thing
and does it well.

## License

MIT

