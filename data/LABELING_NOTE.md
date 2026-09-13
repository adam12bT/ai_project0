# Labeling note

**Source database:** [Chinook](https://github.com/lerocha/chinook-database),
a public, well-known sample SQLite database modeling a digital music store
(artists, albums, tracks, customers, invoices, invoice lines, employees,
genres, media types, playlists). Downloaded directly from the project's
GitHub repo.

**How items were written:** Each of the 53 questions was written against
the real, downloaded database (not from memory of a "typical" schema), then
paired with a hand-written gold SQL query.

**How labels were checked:** every gold query was executed against the
real `Chinook_Sqlite.sqlite` at build time (`src/build_items.py`). Any
query that raised an error or returned 0 rows was rejected and rewritten —
so every label in `items.jsonl` is a verified, non-trivial, executable
query with a known result set. (One item, "invoices in 2010," was caught
this way: the actual data runs 2021–2025, so it was corrected.)

**Outstanding action item — not yet done:** the brief requires two people
to check every label. A second team member still needs to independently
read each of the 53 (question, gold_sql) pairs in `data/items.jsonl` and
confirm the SQL correctly answers the question, then this note should be
updated with their name and the date they did it. This has not happened
yet as of this audit.

**Difficulty spread (so no model gets 0% or 100%):**
- Simple filters / lookups: 10 items
- Counts and aggregates: 10 items
- Joins (2–3 tables): 10 items
- GROUP BY / HAVING: 10 items
- ORDER BY + LIMIT (top-N): 8 items
- Subqueries / DISTINCT / date filters: 5 items

**Dev/test split:** none — all 53 items are held out as the test set
consistent with the brief (one shared item set, same order, for all three
models). If you want a dev set to sanity-check your prompt before the
real run, take the first 5 items as dev and report results on the
remaining 48, or write 5 additional dev-only items so all 53 test items
stay unseen during prompt development.
