# Postmortem

## What went wrong

**The single biggest problem: a token-budget bug made "top" model results
meaningless, and we almost didn't catch it.** `MAX_TOKENS` was set to 1500
for all three models. `qwen/qwen3.6-27b` (the "top" role) is a reasoning
model that opens a `<think>...</think>` block before its final answer, and
on this task it reasons at enormous length — one item alone burned 1500+
tokens second-guessing case sensitivity, column names, and quoting style on
a single-table `LIKE` query before running out of budget. The result: the
model was cut off mid-`<think>` on the large majority of the 53 items and
never emitted a final SQL statement at all. Worse, an earlier version of
`extract_sql()` didn't check for an *unclosed* `<think>` tag, so it fell
through to "grab the first SELECT it finds" and picked up a rejected draft
query from inside the unfinished reasoning — which happened to look
plausible enough that the saved CSV showed "top" passing most items. Once
we added the unclosed-tag check and re-scored the saved data with
`validate_results.py`, "top"'s real accuracy on the runs so far dropped to
1–2%. This wasn't a model-quality finding, it was a harness bug: the model
was never actually being measured. We fixed the root cause (raised
`MAX_TOKENS` to 6000, and separately found `llm_provider/groq.py` was
using a fallback context-window default of 8192 tokens when Groq's real
limit for both models we use is 131K — a second, compounding conservatism
in the same direction) but the "top" role still needs to be re-run against
the fixed budget before its number in the results table is trustworthy.

**Duplicate runs silently corrupted the aggregate stats.** `run.py`
appends to `per_item.csv` with no de-duplication, and its own README said
"delete this file before re-running from scratch" — but that's an easy
step to forget, and we did: `per_item.csv` ended up with 3x the rows for
"top" and 2x for "open" from repeated runs that were never cleared. This
didn't just inflate `n_total`; because `cost.py` averages latency and
token counts across all rows for a model, it silently blended runs made
under different code (before and after the `<think>` fix) and different
`MAX_TOKENS` values into one number. We caught this only because
`validate_results.py` reports a duplicate-item count. We've since added a
guard: `run.py` now refuses to append a model that already has rows unless
you pass `--force`.

**The local model made real reasoning mistakes, not just harness bugs.**
Unlike "top", `mistral:latest` (the "open" role) genuinely got things
wrong: on `item_004` ("Which employees have the job title 'Sales Support
Agent'?") and `item_005` ("List all customers who live in Brazil"), it
returned syntactically valid queries with wrong result sets rather than
errors — the kind of mistake the brief wants a benchmark to actually
surface. It also produced two-table joins with an unqualified column name
that SQLite rejects as ambiguous (e.g. `GROUP BY PlaylistId` /
`HAVING COUNT(TrackId)` after joining `PlaylistTrack` and `Track`, both of
which have a `TrackId` column) on `item_027`, `item_031`, `item_037`,
`item_040`, `item_042`, `item_045`, and `item_048` — a real class of error
worth calling out in the two-page report as a per-model failure mode, not
just noise.

**Fairness:** `score.py`'s order-insensitive-by-default comparison was the
right call — several gold queries use `ORDER BY` for readability, not
because the question requires it, and an order-sensitive check would have
penalized correct answers that returned the same rows in a different
sequence.

## What we'd do differently

- Never share one flat `MAX_TOKENS` across models without first sanity-checking
  what a reasoning model actually needs on a handful of items — we'd run 3-5
  items per model as a smoke test before committing to a 53-item batch and a
  shared token budget.
- Treat `results/per_item.csv` as append-only was the wrong default; a
  script should refuse (or clearly warn) rather than silently duplicate.
  This is now enforced in code, but it should have been designed in from
  the start rather than left to a README instruction a human has to
  remember.
- Re-run `cost.py` as part of the same command as the last `run.py` call,
  or check that `summary.csv`'s row count matches the number of models
  actually run — `summary.csv` sat with only one model's row in it for a
  while and nobody noticed until this audit.

## What we learned

The accuracy numbers only became trustworthy once we treated "the model
produced no error" and "the model's answer was actually scored correctly
by our harness" as two separate things to verify — a parse-error rate of
98% on a supposedly frontier model was itself the signal that something
upstream of the model was broken, not that the model was bad. That's
arguably the whole point of Project 0: a benchmark that would have quietly
reported "top: 68% accuracy, use it" is worse than useless if the real
number is a token-budget artifact. Separately, "open" running locally at
p50 ≈3.5s vs. "cheap" at p50 ≈0.6s is a concrete, felt reminder of why the
brief asks for latency at all — a 45% self-hosted model that's 6x slower
than a 64% hosted one is a genuinely different trade-off than the accuracy
numbers alone would suggest, and that only shows up once you measure both.
