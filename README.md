---
title: Text-to-SQL Workbench
emoji: "📊"
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Project 0 — Bake-Off: Text-to-SQL

**Task:** Given a natural-language question and the schema of the Chinook
sample database (a music store: artists, albums, tracks, customers,
invoices, employees, playlists), generate a single SQLite `SELECT` query
that answers it. Scored automatically by executing the model's query and
the gold query against the real database and comparing result rows — no
human or LLM judge.

## Setup

```bash
# Both API models run on Groq's free developer tier — no card, no cost,
# just rate limits (~30 requests/min, ~1,000/day per model).
# Copy the example env file and put your real key in it:
#   cp .env.example .env        (Windows: copy .env.example .env)
# then edit .env and paste your key — get a free one at https://console.groq.com
# Open-weights model: install Ollama (https://ollama.com) and pull a model, e.g.
ollama pull qwen2.5-coder:7b
```

`.env` is loaded automatically by `llm_provider` (no `python-dotenv` install
needed) — see `llm_provider/_env.py`. It's git-ignored, so your key never
gets committed. If a variable is already set in your real shell environment,
that takes priority over `.env`.

The Chinook database (`Chinook_Sqlite.sqlite`) and its schema
(`schema.sql`) are already included in this repo — no setup needed there.

## Run

```bash
python3 src/build_items.py          # (already run — regenerates data/items.jsonl)
python3 src/run.py --model top      # calls the top API model on all 53 items
python3 src/run.py --model cheap    # calls the cheap API model
python3 src/run.py --model open     # calls your local Ollama model
python3 src/cost.py                 # builds results/summary.csv from per_item.csv
python3 src/visualize.py            # builds results/report.html for browser viewing
python3 build_report_pdf.py         # builds results/report.pdf, the 2-page handed-in report
python3 src/validate_results.py     # re-checks every CSV result against SQLite
python3 src/validate_items.py       # checks every gold SQL and row count
```

Each `run.py` call appends to `results/per_item.csv`. As of the 2026-09-12
audit, `run.py` now refuses to append a second run for a model that
already has rows in that file (this is what let duplicate "top"/"open"
runs silently triple- and double-count earlier) — delete the file, or the
matching rows, before re-running, or pass `--force` if you really mean to
append another run on top.

## React workbench

The project also includes a local React interface for asking questions,
previewing SQL results, uploading JSONL test files, and exploring every saved
benchmark result.

Start the API in one terminal:

```powershell
python server.py
```

Start the React app in another terminal:

```powershell
cd web
npm install                 # first run only
npm run dev
```

Open `http://127.0.0.1:5173/`. The **Ask SQL** view uses Ollama by default;
switch to Groq and enter a configured model when `GROQ_API_KEY` is available.
The **Test lab** view loads `results/per_item.csv`, supports `.jsonl` uploads
for local preview, and can verify all gold queries against SQLite.
Each new frontend test run replaces the visible table and is saved under
`results/runs/`; use the **View run** selector to reopen older runs later.
The **Cost & benchmarks** view calls the same `src/cost.py` math the CLI uses
(`/api/cost-summary`) to show accuracy, p50/p95 latency, cost per 1,000
requests today and at 100x traffic, and the self-hosted break-even point —
so it always matches `results/summary.csv` without duplicating the pricing
logic in the frontend.

Open `results/report.html` in a browser to compare accuracy and latency and
to scan incorrect results without the long raw model outputs.

`validate_results.py` is the correctness test. It executes each saved model
query and its gold query against the database, then checks for stale verdicts,
duplicate items, missing items, and unknown item IDs. Use `--verbose` to print
each failure, or `--model open` to validate one model only. It exits with code
`0` when the CSV is internally consistent and code `1` when a problem is found.

`validate_items.py` checks the gold side independently: every query in
`data/items.jsonl` must execute successfully and return its recorded
`gold_row_count`.

## Models used

A note on why Groq isn't used for all three roles: the brief requires the
third model to be an open-weights model *"run by you"* on your own
hardware, and explicitly states *"calling an open model through someone
else's API does not count."* Groq is a legitimate choice for the top and
cheap **API** slots (it's just an inference API), but it can't stand in
for the self-hosted slot — hence Ollama for `open`.

| Role   | Model                     | Provider | Cost today | Paid-tier rate (per 1M tok, in/out) |
|--------|----------------------------|----------|------------|----------------------------------------|
| Top    | `qwen/qwen3.6-27b`         | Groq     | $0 (free tier) | $0.60 / $3.00 |
| Cheap  | `openai/gpt-oss-20b`       | Groq     | $0 (free tier) | $0.075 / $0.30 |
| Open   | `mistral:latest`, Ollama, local | — | hardware only | — |

**A caveat on "top" vs. "cheap":** both roles are served by Groq rather than
by two different providers' flagship-vs-mini pair (e.g. Opus vs. Haiku).
Groq only hosts open-weight models, so there's no single "best model this
provider sells" in the proprietary sense the brief's own examples use.
`qwen/qwen3.6-27b` and `openai/gpt-oss-20b` are still a reasonable stand-in
for the top/cheap price-performance split, but flag this choice with the
instructor before the demo — it's the one part of the model selection that
deviates from the brief's spirit rather than just its letter.

**Open-weights hardware:** *(fill in — e.g. "Ollama 0.x, Mistral 7B Q4_K_M,
Apple M2 16GB" or your actual GPU/CPU)*. See `results/hardware_note.md`.

Both API models run through Groq's OpenAI-compatible endpoint
(`https://api.groq.com/openai/v1/chat/completions`) — `GROQ_API_KEY`
must be set. The free tier is genuinely $0, gated only by rate limits
(~30 requests/min, ~1,000/day per model — plenty for 53 items). The
"paid-tier rate" column is what `src/cost.py` uses for the 100x-traffic
projection, since 100x volume would blow past the free-tier daily cap.
Groq revises pricing/limits often — verify at
[groq.com/pricing](https://groq.com/pricing) and
[console.groq.com/docs/rate-limits](https://console.groq.com/docs/rate-limits)
before you submit. Fill in `src/cost.py::HARDWARE` with your real
self-hosted cost/throughput.

## Results

| Model | Accuracy (n/53) | p50 latency (ms) | p95 latency (ms) | Cost / 1k requests (free tier today) | at 100x traffic |
|-------|------------------|-------------------|-------------------|-----------------------|-------------------|
| Top   | 1/53 (1.9%)      | 1321.0            | 1836.4            | $0.00                 | $1.74             |
| Cheap | 34/53 (64.2%)    | 572.3             | 1006.3            | $0.00                 | $0.14             |
| Open  | 24/53 (45.3%)    | 3511.7            | 5694.3            | $0.4167               | $0.4167           |

**"Top" is not a real result — it needs to be re-run.** The 2026-09-12 audit
(see `postmortem.md`) found `MAX_TOKENS` was set too low (1500) for
`qwen/qwen3.6-27b`'s `<think>` reasoning on nearly every item, so the model
was cut off before producing a final answer on most of the 53 questions.
That's a token-budget bug, not a real accuracy signal. `src/run.py` has
been fixed (`MAX_TOKENS = 6000`, and `llm_provider/groq.py`'s context-window
default corrected from 8192 to the model's real 131K) — **delete the "top"
rows from `results/per_item.csv` and re-run `python3 src/run.py --model
top`, then `python3 src/cost.py`, before trusting this row.** Cheap and
Open above are real, validated numbers (`validate_results.py` reports 0
verdict mismatches and 0 duplicates as of this audit).

Break-even (top model's paid-tier rate vs. self-hosted): ~206,440
requests/month — but recompute this once "top" has real numbers.

## Data

53 hand-written natural-language questions against the public
[Chinook sample database](https://github.com/lerocha/chinook-database),
each paired with a gold SQL query. See `data/LABELING_NOTE.md` for how
questions were written and checked.

## Repo layout

```
data/items.jsonl        53 (question, gold_sql) pairs
src/prompt.py           the one shared prompt template
src/build_items.py      builds+validates data/items.jsonl against the real DB
src/run.py              calls each model, records latency/tokens/output
src/score.py            executes model SQL vs gold SQL, compares rows
src/cost.py             accuracy/latency/cost summary + break-even calc
results/per_item.csv    one row per (model, item) after running
results/summary.csv     aggregated metrics after running cost.py
results/report.pdf      the 2-page handed-in report (build_report_pdf.py)
results/hardware_note.md  self-hosted hardware/throughput details
Chinook_Sqlite.sqlite   the test database
schema.sql              CREATE TABLE statements embedded in the prompt
```

## Contributions

*(one entry per team member — I don't have your team's names, so this
still needs you to fill it in before submission; everything else in this
README has been completed)*
- Name — what they worked on
- Name — what they worked on

## No API keys in this repo

`GROQ_API_KEY` is read from the environment only. Do not commit keys.
