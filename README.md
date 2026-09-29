# OSS Contribution Finder
[![CI](https://github.com/yunaremaia/oss-contribution-finder/actions/workflows/ci.yml/badge.svg)](https://github.com/yunaremaia/oss-contribution-finder/actions)
[![PyPI](https://img.shields.io/pypi/v/oss-contribution-finder)](https://pypi.org/project/oss-contribution-finder/)
[![License](https://img.shields.io/github/license/yunaremaia/oss-contribution-finder) ![Stars](https://img.shields.io/github/stars/yunaremaia/oss-contribution-finder)](https://github.com/yunaremaia/oss-contribution-finder/blob/main/LICENSE)


Find open-source contribution opportunities via the GitHub API.

Searches for issues labeled "good first issue" (or any label you choose), filtered by language, topic, star count, and activity. Outputs a ranked list ready for contribution.

## Install

```bash
pip install git+https://github.com/yunaremaia/oss-contribution-finder.git
```

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
| `--language`, `-l` | Programming language | — |
| `--topic`, `-t` | GitHub topic | — |
| `--min-stars` | Minimum star count | — |
| `--created-after` | Issues created after (YYYY-MM-DD) | — |
| `--updated-after` | Issues updated after (YYYY-MM-DD) | 30 days ago |
| `--sort` | Sort field (`comments`, `reactions`, `updated`) | `updated` |
| `--limit`, `-n` | Max results | 20 |
| `--format`, `-f` | Output (`table`, `markdown`, `json`) | `table` |
| `--no-enrich` | Skip repo metadata (faster) | false |
| `--require-contributing` | Only include repos with a root `CONTRIBUTING.md` | false |
| `--check-rate-limit` | Show rate limit and exit | — |

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

## License

MIT
