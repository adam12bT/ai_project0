"""Local API for the React SQL workbench."""
import csv
import json
import mimetypes
import os
import sqlite3
import sys
import time
from threading import Lock
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from prompt import SYSTEM_PROMPT as _INITIAL_SYSTEM_PROMPT, build_user_prompt
import run as run_module

# Mutable in-process copy — edits via the UI take effect immediately
# without restarting the server. Restarting resets to the value in prompt.py.
_system_prompt = _INITIAL_SYSTEM_PROMPT


def get_system_prompt():
    return _system_prompt


def set_system_prompt(text):
    global _system_prompt
    _system_prompt = text
from score import extract_sql, score
from llm_provider import call_model
import cost as cost_module
import run as run_module

DB_PATH = os.path.join(ROOT, "Chinook_Sqlite.sqlite")
ITEMS_PATH = os.path.join(ROOT, "data", "items.jsonl")
RESULTS_PATH = os.path.join(ROOT, "results", "per_item.csv")
RUNS_DIR = os.path.join(ROOT, "results", "runs")
SCHEMA_PATH = os.path.join(ROOT, "schema.sql")
STATIC_DIR = os.path.join(ROOT, "web", "dist")
TEST_RUN_LOCK = Lock()
OLLAMA_DISABLED = os.environ.get("DISABLE_OLLAMA", "") == "1"
TEST_STATUS = {
    "status": "idle", "completed": 0, "total": 0, "correct": 0,
    "model_key": "", "model": "", "started_at": None,
}


def log(message):
    """Prints a timestamped line to the terminal running server.py, so you
    can actually watch what's happening — which requests are coming in,
    how a test batch is progressing item by item, and what errors happen
    server-side (not just the short error string the client gets back)."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def load_items():
    with open(ITEMS_PATH, "r", encoding="utf-8") as file:
        return {item["id"]: item for item in map(json.loads, file)}


def read_rows():
    if not os.path.exists(RESULTS_PATH):
        return []
    with open(RESULTS_PATH, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames and "odel_key" in reader.fieldnames:
            reader.fieldnames[reader.fieldnames.index("odel_key")] = "model_key"
        items = load_items()
        rows = []
        for row in reader:
            item = items.get(row.get("item_id", ""), {})
            rows.append({
                "model_key": row.get("model_key", "unknown"),
                "model_name": row.get("model_name", ""),
                "item_id": row.get("item_id", ""),
                "question": row.get("question", ""),
                "correct": row.get("correct", "").lower() == "true",
                "reason": row.get("reason", ""),
                "latency_ms": row.get("latency_ms", ""),
                "input_tokens": row.get("input_tokens", ""),
                "output_tokens": row.get("output_tokens", ""),
                "raw_output": row.get("raw_output", ""),
                "gold_sql": item.get("gold_sql", ""),
            })
        return rows


def run_gold_validation():
    items = list(load_items().values())
    errors = []
    mismatches = []
    with sqlite3.connect(DB_PATH) as database:
        for item in items:
            try:
                actual = len(database.execute(item["gold_sql"]).fetchall())
                expected = int(item["gold_row_count"])
                if actual != expected:
                    mismatches.append({"id": item["id"], "expected": expected, "actual": actual})
            except sqlite3.Error as error:
                errors.append({"id": item["id"], "error": str(error)})
    return {"total": len(items), "errors": errors, "mismatches": mismatches, "ok": not errors and not mismatches}


def build_cost_summary():
    """Reuses src/cost.py's own math so the UI and the CLI report never drift apart."""
    if not os.path.exists(RESULTS_PATH):
        rows = []
    else:
        rows = cost_module.load_rows()

    # Always show the three standard roles (top / cheap / open) even before
    # they've been tested, plus any other model_key that shows up in the data.
    standard_roles = ["top", "cheap", "open"]
    seen_keys = sorted(set(row["model_key"] for row in rows))
    model_keys = standard_roles + [key for key in seen_keys if key not in standard_roles]
    models = []
    for key in model_keys:
        summary = cost_module.summarize_model(key, rows)
        # Prefer the model name actually configured for this role (matches
        # what src/run.py calls); fall back to whatever name shows up in the
        # data for a custom/unknown key, so the card never just shows the
        # bare role like "top" as its title.
        if key in run_module.MODEL_CONFIG:
            summary["model_name"] = run_module.MODEL_CONFIG[key]["model"]
        else:
            matching = next((row["model_name"] for row in rows if row["model_key"] == key and row.get("model_name")), None)
            summary["model_name"] = matching or key
        models.append(summary)

    break_even = None
    pricing = cost_module.PRICING.get("top")
    top_rows = [row for row in rows if row["model_key"] == "top" and row["input_tokens"]]
    if pricing and top_rows:
        avg_in = sum(int(row["input_tokens"]) for row in top_rows) / len(top_rows)
        avg_out = sum(int(row["output_tokens"]) for row in top_rows) / len(top_rows)
        api_cost_per_req = (avg_in / 1_000_000 * pricing["input_per_mtok"]) + (avg_out / 1_000_000 * pricing["output_per_mtok"])
        break_even = cost_module.break_even_volume(
            api_cost_per_req, cost_module.HARDWARE["cost_per_hour_usd"], cost_module.HARDWARE["requests_per_hour"]
        )

    return {
        "models": models,
        "break_even_requests_per_month": break_even,
        "hardware": cost_module.HARDWARE,
        "pricing": cost_module.PRICING,
    }


def append_to_per_item_csv(rows):
    """Appends web-triggered test rows to the SAME results/per_item.csv the
    CLI (src/run.py) writes to, using the exact same column schema, so a
    test run started from the website counts toward the official Cost &
    benchmarks numbers instead of only being saved to results/runs/."""
    fieldnames = ["model_key", "model_name", "item_id", "question",
                  "raw_output", "correct", "reason", "latency_ms",
                  "input_tokens", "output_tokens"]
    file_exists = os.path.exists(RESULTS_PATH)
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def json_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def save_run(rows, provider, model, item_count):
    os.makedirs(RUNS_DIR, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    correct = sum(row["correct"] for row in rows)
    payload = {
        "run_id": run_id,
        "started_at": started_at,
        "provider": provider,
        "model": model,
        "item_count": item_count,
        "correct": correct,
        "accuracy": correct / len(rows) if rows else 0,
        "rows": rows,
    }
    path = os.path.join(RUNS_DIR, f"{run_id}.json")
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return payload


def load_runs():
    if not os.path.isdir(RUNS_DIR):
        return []
    runs = []
    for name in os.listdir(RUNS_DIR):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(RUNS_DIR, name), "r", encoding="utf-8") as file:
                payload = json.load(file)
            runs.append({key: payload.get(key) for key in (
                "run_id", "started_at", "provider", "model", "item_count", "correct", "accuracy"
            )})
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(runs, key=lambda run: run["run_id"], reverse=True)


class ApiHandler(BaseHTTPRequestHandler):
    def log_message(self, format_string, *args):
        # Default BaseHTTPRequestHandler behavior silences everything if
        # this is overridden with `return` (which the original code did).
        # Route it through our timestamped log() instead so requests show
        # up in the terminal, e.g. [14:02:11] "GET /api/results HTTP/1.1" 200 -
        log(format_string % args)

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def serve_static(self, path):
        if not os.path.isdir(STATIC_DIR):
            return False

        relative_path = os.path.normpath(unquote(path.lstrip("/")))
        if relative_path in ("", "."):
            relative_path = "index.html"
        if relative_path.startswith(".."):
            return False

        file_path = os.path.join(STATIC_DIR, relative_path)
        if not os.path.isfile(file_path):
            # Vite's client-side routes need to resolve to the app shell.
            file_path = os.path.join(STATIC_DIR, "index.html")
        try:
            with open(file_path, "rb") as file:
                data = file.read()
        except OSError:
            return False

        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/results":
            rows = read_rows()
            return self.send_json({"rows": rows, "total": len(rows)})
        if path == "/api/runs":
            return self.send_json({"runs": load_runs()})
        if path == "/api/test-status":
            return self.send_json(TEST_STATUS)
        if path.startswith("/api/runs/"):
            run_id = path.rsplit("/", 1)[-1]
            run_path = os.path.join(RUNS_DIR, f"{run_id}.json")
            if not os.path.isfile(run_path):
                return self.send_json({"error": "Run not found"}, 404)
            with open(run_path, "r", encoding="utf-8") as file:
                return self.send_json(json.load(file))
        if path == "/api/items":
            return self.send_json({"items": list(load_items().values()), "name": "items.jsonl"})
        if path == "/api/schema":
            with open(SCHEMA_PATH, "r", encoding="utf-8") as file:
                return self.send_json({"schema": file.read()})
        if path == "/api/validate-items":
            return self.send_json(run_gold_validation())
        if path == "/api/cost-summary":
            return self.send_json(build_cost_summary())
        if path == "/api/system-prompt":
            return self.send_json({"system_prompt": get_system_prompt()})
        if path == "/api/prompt":
            from urllib.parse import parse_qs, urlparse as _urlparse
            qs = parse_qs(_urlparse(self.path).query)
            question = qs.get("question", [""])[0]
            return self.send_json({
                "system_prompt": get_system_prompt(),
                "user_prompt": build_user_prompt(question),
            })
        if path == "/api/run-sql":
            from urllib.parse import parse_qs, urlparse as _urlparse
            qs = parse_qs(_urlparse(self.path).query)
            gold_sql = qs.get("gold_sql", [""])[0]
            model_sql = qs.get("model_sql", [""])[0]
            def exec_sql(sql):
                if not sql or not sql.strip():
                    return {"columns": [], "rows": [], "error": "No SQL"}
                extracted = extract_sql(sql) or sql.strip()
                try:
                    with sqlite3.connect(DB_PATH) as db:
                        db.row_factory = sqlite3.Row
                        cur = db.execute(extracted)
                        rows = [dict(r) for r in cur.fetchmany(50)]
                        cols = [c[0] for c in (cur.description or [])]
                    return {"columns": cols, "rows": rows, "sql": extracted}
                except sqlite3.Error as e:
                    return {"columns": [], "rows": [], "sql": extracted, "error": str(e)}
            return self.send_json({
                "gold": exec_sql(gold_sql),
                "model": exec_sql(model_sql),
            })
        if self.serve_static(path):
            return
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/chat", "/api/run-tests", "/api/system-prompt"):
            return self.send_json({"error": "Not found"}, 404)
        try:
            body = json_body(self)
            if path == "/api/system-prompt":
                text = body.get("system_prompt", "").strip()
                if not text:
                    return self.send_json({"error": "system_prompt cannot be empty"}, 400)
                set_system_prompt(text)
                log(f"System prompt updated ({len(text)} chars)")
                return self.send_json({"ok": True, "system_prompt": get_system_prompt()})
            if path == "/api/run-tests":
                return self.run_tests(body)
            question = body.get("question", "").strip()
            provider = body.get("provider", "ollama")
            model = body.get("model", "mistral:latest")
            if not question:
                return self.send_json({"error": "Enter a question first."}, 400)
            if provider == "ollama" and OLLAMA_DISABLED:
                return self.send_json({
                    "error": "Ollama is available only when the app runs locally. Select a Groq model in the hosted Space."
                }, 400)
            text, latency_ms, usage = call_model(
                provider, model, build_user_prompt(question),
                system_prompt=get_system_prompt(), temperature=0, max_tokens=run_module.MAX_TOKENS,
            )
            sql = extract_sql(text)
            rows = []
            columns = []
            if sql and sql.strip().upper().startswith("SELECT"):
                try:
                    with sqlite3.connect(DB_PATH) as database:
                        database.row_factory = sqlite3.Row
                        cursor = database.execute(sql)
                        rows = [dict(row) for row in cursor.fetchmany(50)]
                        columns = [column[0] for column in cursor.description or []]
                except sqlite3.Error as error:
                    return self.send_json({"error": str(error), "sql": sql, "raw_output": text}, 422)
            return self.send_json({
                "question": question, "sql": sql, "raw_output": text,
                "rows": rows, "columns": columns if rows or sql else [],
                "row_count": len(rows), "truncated": len(rows) == 50,
                "latency_ms": round(latency_ms, 1), "usage": usage,
                "provider": provider, "model": model,
            })
        except Exception as error:
            log(f"ERROR in /api/chat: {error}")
            traceback.print_exc()
            return self.send_json({"error": str(error)}, 500)

    def run_tests(self, body):
        if not TEST_RUN_LOCK.acquire(blocking=False):
            return self.send_json({
                "error": "A test run is already in progress. Wait for it to finish before starting another."
            }, 409)
        try:
            return self._run_tests(body)
        finally:
            TEST_RUN_LOCK.release()

    def _run_tests(self, body):
        items = body.get("items", [])
        model_key = body.get("model_key", "")
        if model_key not in run_module.MODEL_CONFIG:
            return self.send_json({
                "error": "model_key must be one of: top, cheap, open (same roles as src/run.py)."
            }, 400)

        TEST_STATUS.update({
            "status": "running", "completed": 0, "total": len(items),
            "correct": 0, "model_key": model_key, "model": model,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        cfg = run_module.MODEL_CONFIG[model_key]
        provider, model = cfg["provider"], cfg["model"]
        if provider == "ollama" and OLLAMA_DISABLED:
            return self.send_json({
                "error": "Ollama is available only when the app runs locally. Use a Groq model in the hosted Space."
            }, 400)
        if not items or not isinstance(items, list):
            return self.send_json({"error": "Upload a JSONL file with test items first."}, 400)
        if len(items) > 100:
            return self.send_json({"error": "The browser runner allows a maximum of 100 test items."}, 400)

        log(f"Starting test run: model_key={model_key} ({provider}/{model}), {len(items)} items")
        rows = []
        for index, item in enumerate(items, start=1):
            item_id = item.get("id", "unknown")
            question = str(item.get("question", "")).strip()
            if not question or not item.get("gold_sql"):
                log(f"  [{index}/{len(items)}] {item_id}: SKIPPED (invalid_test_item — missing question or gold_sql)")
                rows.append({
                    "model_key": model_key, "model_name": model,
                    "item_id": item_id, "question": question,
                    "raw_output": "", "correct": False,
                    "reason": "invalid_test_item", "latency_ms": "",
                    "input_tokens": "", "output_tokens": "",
                    "gold_sql": item.get("gold_sql", ""),
                })
                continue
            try:
                text, latency_ms, usage = call_model(
                    provider, model, build_user_prompt(question),
                    system_prompt=get_system_prompt(), temperature=0, max_tokens=run_module.MAX_TOKENS,
                )
                # Same free-tier rate-limit courtesy delay the CLI uses, so a
                # batch of up to 100 items run from the website doesn't blow
                # through Groq's ~30 requests/minute cap.
                if provider == "groq":
                    time.sleep(run_module.GROQ_REQUEST_DELAY_SECONDS)
                result = score(text, item["gold_sql"], DB_PATH)
                status = "OK" if result["correct"] else f"WRONG ({result['reason']})"
                log(f"  [{index}/{len(items)}] {item_id}: {status} — {round(latency_ms)}ms, "
                    f"{usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out tokens")
                rows.append({
                    "model_key": model_key, "model_name": model,
                    "item_id": item_id, "question": question,
                    "raw_output": text, "correct": result["correct"],
                    "reason": result["reason"], "latency_ms": round(latency_ms, 1),
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "gold_sql": item["gold_sql"],
                })
            except Exception as error:
                log(f"  [{index}/{len(items)}] {item_id}: ERROR — {error}")
                traceback.print_exc()
                rows.append({
                    "model_key": model_key, "model_name": model,
                    "item_id": item_id, "question": question,
                    "raw_output": "", "correct": False,
                    "reason": f"api_error: {error}", "latency_ms": "",
                    "input_tokens": "", "output_tokens": "",
                    "gold_sql": item["gold_sql"],
                })
            TEST_STATUS["completed"] = index
            TEST_STATUS["correct"] = sum(1 for row in rows if row["correct"])
        append_to_per_item_csv(rows)
        payload = save_run(rows, provider, model, len(items))
        n_correct = sum(1 for row in rows if row["correct"])
        log(f"Finished test run: {n_correct}/{len(rows)} correct — appended to results/per_item.csv "
            f"(run_id={payload['run_id']})")
        TEST_STATUS["status"] = "completed"
        return self.send_json({
            "run_id": payload["run_id"], "rows": rows, "total": len(rows),
            "model_key": model_key, "provider": provider, "model": model,
        })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("API_PORT", "8000")))
    log(f"SQL workbench API running on port {port}")
    log("Watching for requests below. Ctrl+C to stop.")
    try:
        ThreadingHTTPServer(("0.0.0.0", port), ApiHandler).serve_forever()
    except OSError as error:
        log(f"Could not start server on port {port}: {error}")
        log(f"This usually means something is already listening on port {port}. "
            f"On Windows, run: netstat -ano | findstr :{port}  then taskkill /PID <the number> /F")