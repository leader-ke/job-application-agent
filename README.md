# Job Application Agent

An autonomous job search and application agent that runs daily on GitHub Actions. It searches multiple job boards, scores each listing against your resume using an LLM, emails you a digest, and applies to jobs you approve — all without touching your machine.

## How it works

```
Search → Deduplicate → Analyze (LLM) → Email Digest → You reply "APPLY: 1,3" → Agent applies
```

1. **Search** — Scrapes LinkedIn (via [JobSpy2](https://github.com/Bunsly/JobSpy)), [Crossover](https://www.crossover.com/jobs), [Arc.dev](https://arc.dev/remote-jobs), and Kenya Government job adverts ([gaa.go.ke](https://gaa.go.ke)). Jobs already seen are stored in SQLite and skipped in future runs.
2. **Filter** — Location gate: only remote (worldwide) or Kenya-based roles pass. Exclude keywords (junior, industrial automation, etc.) disqualify listings immediately.
3. **Analyze** — Each job description + your resume is sent to an LLM. Returns a fit score (0–100), rationale, rewritten resume bullets, and a cover letter.
4. **Digest email** — Actionable jobs (score ≥ `review_threshold`) are emailed as an HTML table with score, company, location, apply method badge, and a one-line rationale.
5. **Approval** — Reply to the digest email with `APPLY: 1, 3` to approve jobs by number. The agent checks for replies hourly and submits applications automatically.
6. **Confirmation** — A confirmation email is sent for each successful application, threaded under the original digest.

If no matching jobs are found, a short "no results" notification is sent so you always know the agent ran.

## Schedules (GitHub Actions)

| Workflow | Schedule | What it does |
|---|---|---|
| `digest.yml` | Daily 7 AM EAT | Search → analyze → send digest email |
| `apply-approved.yml` | Hourly 8 AM–8 PM EAT | Check Gmail for APPLY replies → submit applications |
| `keepalive.yml` | 1st of each month | Commits to `.keepalive` to prevent 60-day inactivity disabling |
| `ci.yml` | Every push / PR | Lint (ruff) + tests (pytest, 60% coverage floor) |

## LLM backends

The agent auto-selects based on available environment variables, in priority order:

| Priority | Backend | When used |
|---|---|---|
| 1 | [Groq](https://console.groq.com) (`GROQ_API_KEY`) | Free, fast — default for GitHub Actions |
| 2 | [Anthropic Claude](https://console.anthropic.com) (`ANTHROPIC_API_KEY`) | Paid, most accurate |
| 3 | [Ollama](https://ollama.com) | Local only, no API key needed |

## Job sources

| Source | Type | Notes |
|---|---|---|
| LinkedIn | JobSpy2 scraper | Remote + Kenya roles |
| Crossover | Playwright (SPA) | Remote only, high-paying roles |
| Arc.dev | Next.js `__NEXT_DATA__` + Playwright fallback | Remote developer roles |
| gaa.go.ke | HTML scraper | Kenya government ICT/software adverts |

## Setup

### 1. Clone and install

```bash
git clone https://github.com/leader-ke/job-application-agent.git
cd job-application-agent
uv sync --group dev
uv run playwright install chromium
```

### 2. Configure

```bash
# Copy and fill in credentials
cp .env.example .env
```

**`.env` keys:**

| Key | Description |
|---|---|
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | [Gmail App Password](https://myaccount.google.com/apppasswords) (not your regular password) |
| `GROQ_API_KEY` | From [console.groq.com](https://console.groq.com) — free tier is sufficient |
| `ANTHROPIC_API_KEY` | Optional Claude fallback |
| `APPLICANT_NAME` | Your full name (used in application forms) |
| `APPLICANT_PHONE` | Your phone number |

Edit your resume and preferences:

```bash
nano config/resume.md       # Your master resume in Markdown
nano config/preferences.yaml  # Roles, locations, thresholds
```

### 3. GitHub Actions secrets

Add these in **Settings → Secrets and variables → Actions**:

- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `GROQ_API_KEY`
- `ANTHROPIC_API_KEY` (optional)

### 4. Install pre-commit hooks (local dev)

```bash
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
```

Ruff lint + format run on every commit. Tests run on every push.

## Configuration

### `config/preferences.yaml`

| Key | Description |
|---|---|
| `roles` | Job titles to search for |
| `locations` | `"Remote"`, `"Nairobi, Kenya"`, `"Kenya"` |
| `sources` | Job boards for JobSpy2 (currently `linkedin`) |
| `auto_apply_threshold` | Score ≥ this → held for approval in digest mode (default: 75) |
| `review_threshold` | Score below this → skipped entirely (default: 65) |
| `exclude_keywords` | Strings that disqualify a listing immediately |
| `results_per_search` | Listings to fetch per role/location combination |

### `config/resume.md`

Your master resume in Markdown. The LLM reads this to score fit and tailor bullets — keep it detailed and up to date.

## Manual usage

```bash
# Search, analyze, and send digest email
uv run main.py --digest

# Check Gmail for APPLY replies and submit approved applications
uv run main.py --apply-approved

# Dry run — search and analyze, print results, no email sent
uv run main.py --dry-run
```

## Approval flow

1. Receive the daily digest email at 7 AM EAT
2. Review the job table — each row shows score, company, location, apply method, and rationale
3. Reply with the numbers you want applied to:
   ```
   APPLY: 1, 3, 5
   ```
4. Within the hour, the agent applies and sends a confirmation email

**Apply method badges:**
- 🟢 **Auto** — Greenhouse or Lever portal (fully automated)
- 🔴 **Manual** — Other portal (open the link and apply yourself)
- 🟡 **PDF** — Government advert (download and follow instructions)

## Supported ATS portals

| Portal | Automated |
|---|---|
| Greenhouse | Yes |
| Lever | Yes |
| Others | Flagged — URL provided for manual action |

## Project structure

```
job-application-agent/
├── main.py                          # Orchestrator (--digest, --apply-approved, --dry-run)
├── config/
│   ├── preferences.yaml             # Roles, locations, thresholds, sources
│   └── resume.md                    # Master resume (Markdown)
├── agent/
│   ├── search/
│   │   ├── scraper.py               # JobSpy2 + deduplication (SQLite)
│   │   ├── mygov_scraper.py         # Kenya government jobs (gaa.go.ke)
│   │   ├── crossover_scraper.py     # Crossover (Playwright)
│   │   └── arc_scraper.py           # Arc.dev (Next.js JSON + Playwright fallback)
│   ├── analyze/scorer.py            # LLM scoring, bullet rewriting, cover letter
│   ├── apply/browser.py             # Playwright ATS automation
│   ├── notify/
│   │   ├── emailer.py               # Digest + confirmation + no-results emails
│   │   └── reply_checker.py         # IMAP reader for APPLY replies
│   └── data/store.py                # SQLite store (digests, pending jobs)
├── tests/                           # pytest suite (114 tests, 66% coverage)
├── .github/workflows/
│   ├── digest.yml                   # Daily 7 AM EAT
│   ├── apply-approved.yml           # Hourly 8 AM–8 PM EAT
│   ├── keepalive.yml                # Monthly keepalive commit
│   └── ci.yml                       # Lint + test on push/PR
└── scripts/                         # Legacy launchd plists (no longer used)
```

## Notes

- Place a PDF copy of your resume at `data/resume.pdf` — required for file upload fields in Greenhouse/Lever forms.
- IMAP must be enabled in Gmail: **Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP**.
- The SQLite database (`data/jobs.db`) is persisted between GitHub Actions runs via the Actions cache.
- GitHub workflow runs do not count as repository activity for the 60-day inactivity rule — that is why the monthly keepalive commit exists.
