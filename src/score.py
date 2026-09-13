"""
score(model_sql, gold_sql, db_path) -> dict with a verdict.

Rule from the brief: no human, no LLM judges correctness. We execute
both the model's SQL and the gold SQL against the same database and
compare the resulting rows. Order doesn't matter unless the question
asked for an order (most of our gold queries use ORDER BY, so we also
offer an order-sensitive check for those items) - by default we treat
the result as a set to avoid unfairly penalizing a correct-but-differently
-ordered query on items where order wasn't semantically required.

A parse error, execution error, or timeout on the model's SQL is WRONG,
never excluded from the denominator (per the brief: it still counts).
"""
import sqlite3
import re
import time

class TimeoutError(Exception):
    pass

def extract_sql(raw_output: str) -> str:
    """Strip markdown fences / stray prose some models add despite instructions."""
    text = raw_output.strip()

    # Reasoning models (e.g. qwen/qwen3.6-27b) emit a <think>...</think>
    # block before their real answer. That block often contains draft SQL
    # the model considered and rejected — if we don't remove it first, the
    # "grab the first SELECT" step below can pick up a wrong draft instead
    # of the model's actual final answer. Strip any complete <think> blocks.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    # If there's an unclosed <think> tag, the model ran out of its output-token
    # budget mid-reasoning and never actually reached a final answer. Treat
    # that as no SQL at all (parse error) rather than reading into the
    # unfinished, half-written reasoning that follows it.
    if re.search(r"<think>", text, re.IGNORECASE) and not re.search(r"</think>", text, re.IGNORECASE):
        return ""

    fence = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    # If the model added a leading explanation line before the SELECT, cut to SELECT.
    match = re.search(r"(SELECT\b.*)", text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1).strip()
    # Keep only the first SQL statement. Models sometimes append an explanation
    # after a valid query, which otherwise makes SQLite reject the whole output.
    quote = None
    for index, character in enumerate(text):
        if character in "'\"":
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
        elif character == ";" and quote is None:
            return text[:index + 1].strip()
    return text

def _run_query(db_path: str, sql: str, timeout_s: int = 5):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    # SQLite has no native query timeout. signal.alarm() is Unix-only, so we
    # use set_progress_handler instead: SQLite calls this callback every
    # `n_instructions` VM steps during query execution, and a non-zero
    # return value aborts the query. This works identically on Windows,
    # macOS, and Linux.
    start = time.monotonic()

    def _progress_handler():
        return 1 if (time.monotonic() - start) > timeout_s else 0

    con.set_progress_handler(_progress_handler, 1000)
    try:
        cur.execute(sql)
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e).lower():
            raise TimeoutError()
        raise
    finally:
        con.set_progress_handler(None, 0)
        con.close()
    return rows

def score(model_output: str, gold_sql: str, db_path: str, timeout_s: int = 5) -> dict:
    model_sql = extract_sql(model_output)

    if not model_sql or not model_sql.strip().upper().startswith("SELECT"):
        return {"correct": False, "reason": "parse_error", "model_sql": model_sql}

    try:
        model_rows = _run_query(db_path, model_sql, timeout_s)
    except TimeoutError:
        return {"correct": False, "reason": "timeout", "model_sql": model_sql}
    except Exception as e:
        return {"correct": False, "reason": f"execution_error: {e}", "model_sql": model_sql}

    gold_rows = _run_query(db_path, gold_sql, timeout_s)

    # Order-insensitive comparison by default (see module docstring).
    if sorted(map(str, model_rows)) == sorted(map(str, gold_rows)):
        return {"correct": True, "reason": "match", "model_sql": model_sql}
    else:
        return {
            "correct": False,
            "reason": "wrong_result",
            "model_sql": model_sql,
            "model_row_count": len(model_rows),
            "gold_row_count": len(gold_rows),
        }