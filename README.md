# Job Application Agent

An autonomous job search and application agent with three layers: **Search**, **Analyze**, and **Apply**.

Scrapes job boards, scores each listing against your resume using a local LLM (no API key required), and automates applications on supported ATS portals. Unsupported portals are flagged for manual review.

## How it works

```
Search → Deduplicate → Filter → Analyze (LLM) → Gate → Apply / Flag / Skip
```

1. **Search** — Scrapes configured job boards (Indeed, Glassdoor, etc.) using [JobSpy](https://github.com/Bunsly/JobSpy). Stores seen job IDs in SQLite so listings are never processed twice.
2. **Analyze** — Sends each job description + your master resume to a local [Ollama](https://ollama.com) model. The model returns a fit score (0–100), explains gaps, rewrites resume bullets to mirror the JD's language, and drafts a cover letter.
3. **Gate** — Jobs below `review_threshold` are skipped. Jobs between `review_threshold` and `auto_apply_threshold` are flagged for manual review. Jobs above `auto_apply_threshold` are applied to automatically.
4. **Apply** — Playwright fills and submits Greenhouse and Lever application forms. Any other portal is flagged with the URL for manual action.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- [Ollama](https://ollama.com) running locally with at least one model pulled

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/leader-ke/job-application-agent.git
cd job-application-agent

# 2. Install dependencies
uv sync

# 3. Install Playwright browser
uv run playwright install chromium

# 4. Pull an Ollama model (if you haven't already)
ollama pull llama3.2

# 5. Copy and edit the env file
cp .env.example .env

# 6. Edit your master resume
nano config/resume.md

# 7. Configure your search preferences
nano config/preferences.yaml
```

## Configuration

### `config/preferences.yaml`

| Key | Description |
|-----|-------------|
| `roles` | Job titles to search for |
| `locations` | Locations or `"Remote"` |
| `sources` | Job boards: `indeed`, `glassdoor`, `linkedin`, `zip_recruiter` |
| `auto_apply_threshold` | Score at or above which the agent applies automatically (default: 75) |
| `review_threshold` | Score below which the listing is skipped entirely (default: 55) |
| `salary_floor` | Minimum salary in USD/year — set to `0` to disable |
| `exclude_keywords` | Strings that disqualify a listing immediately |
| `results_per_search` | Listings to fetch per role/location combination |

### `config/resume.md`

Your master resume in Markdown. The LLM reads this to score fit and tailor bullets — keep it detailed and up to date.

### `OLLAMA_MODEL` (optional)

Set in `.env` to override the model. Any model you have pulled locally works:

```
OLLAMA_MODEL=llama3.1:8b
```

## Usage

```bash
# Dry run — search and analyze, no applications submitted
uv run main.py --dry-run

# Full run
uv run main.py
```

Output is a Rich table showing each listing, its score, and the outcome (applied / review / skip / flagged).

## Supported ATS portals

| Portal | Automated |
|--------|-----------|
| Greenhouse | Yes |
| Lever | Yes |
| Others | Flagged with URL for manual action |

LinkedIn Easy Apply and Workday are not automated — they are flagged for manual review due to bot detection and complex multi-step flows.

## Project structure

```
job-application-agent/
├── main.py                    # Orchestrator
├── config/
│   ├── preferences.yaml       # Search and threshold config
│   └── resume.md              # Master resume
├── agent/
│   ├── search/scraper.py      # JobSpy scraper + SQLite deduplication
│   ├── analyze/scorer.py      # Ollama LLM scoring and writing
│   └── apply/browser.py       # Playwright ATS automation
├── data/                      # Gitignored — holds jobs.db at runtime
└── tests/
```

## Notes

- Job boards actively block scrapers. LinkedIn in particular is aggressive — treat it as a "flag and open in browser" source rather than a fully automated one.
- Place a PDF copy of your resume at `data/resume.pdf` for the file upload step in apply forms.
- Ollama must be running before you execute the agent (`ollama serve`).
