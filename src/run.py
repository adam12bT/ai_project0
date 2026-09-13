"""
Runs the SAME prompt, SAME 53 items, SAME order, temperature 0, against
three models, and writes one row per (model, item) to results/per_item.csv.

Usage:
    export GROQ_API_KEY=...            # for the two Groq free-tier models
    python3 src/run.py --model top
    python3 src/run.py --model cheap
    python3 src/run.py --model open     # requires Ollama running locally

Fill in MODEL_CONFIG below with the exact model names/dates you used,
per the brief's "write down the exact model name and the date" rule.
"""
import argparse
import csv
import json
import os
import time
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # for llm_provider/
from prompt import SYSTEM_PROMPT, build_user_prompt
from score import score
from llm_provider import call_model

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "Chinook_Sqlite.sqlite")
ITEMS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "items.jsonl")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "results", "per_item.csv")
MAX_TOKENS = 1500  # same output-token limit for all three, per the brief —
                    # raised from 300 so a reasoning model (e.g. the "top"
                    # role) has room to finish its <think> block and still
                    # reach a final answer, not get cut off mid-thought

# --- Fill these in with the exact models/settings you actually used ---
MODEL_CONFIG = {
    "top":   {"provider": "groq", "model": "openai/gpt-oss-120b"},  # 120B, free tier, replaces qwen/qwen3.6-27b
    "cheap": {"provider": "groq", "model": "openai/gpt-oss-20b"}, # free tier, replaces llama-3.1-8b-instant
    "open":  {"provider": "ollama", "model": "mistral:latest"},   # example; run yourself
}
GROQ_REQUEST_DELAY_SECONDS = float(os.environ.get("GROQ_REQUEST_DELAY_SECONDS", "2.5"))
# Both Groq models above run on the free developer tier (no card needed),
# rate-limited to roughly 30 requests/minute and 1,000 requests/day per
# model — comfortably enough for 53 sequential items. run_model() adds a
# short delay between Groq calls to stay under that limit. Verify current
# limits at https://console.groq.com/docs/rate-limits before your run.
# -----------------------------------------------------------------------

def load_items():
    items = []
    with open(ITEMS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            items.append(json.loads(line))
    return items

def run_model(model_key, items):
    cfg = MODEL_CONFIG[model_key]
    rows = []
    for item in items:
        user_prompt = build_user_prompt(item["question"])
        try:
            text, latency_ms, usage = call_model(
                cfg["provider"], cfg["model"], user_prompt,
                system_prompt=SYSTEM_PROMPT, temperature=0, max_tokens=MAX_TOKENS,
            )
            if cfg["provider"] == "groq":
                time.sleep(GROQ_REQUEST_DELAY_SECONDS)
        except Exception as e:
            # A failed call is still a row — counts as wrong, per the brief.
            rows.append({
                "model_key": model_key, "model_name": cfg["model"],
                "item_id": item["id"], "question": item["question"],
                "raw_output": "", "correct": False, "reason": f"api_error: {e}",
                "latency_ms": "", "input_tokens": "", "output_tokens": "",
            })
            continue

        result = score(text, item["gold_sql"], DB_PATH)
        rows.append({
            "model_key": model_key, "model_name": cfg["model"],
            "item_id": item["id"], "question": item["question"],
            "raw_output": text, "correct": result["correct"],
            "reason": result["reason"],
            "latency_ms": round(latency_ms, 1),
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
        })
        print(f"{model_key} {item['id']}: {'OK' if result['correct'] else result['reason']}")
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["top", "cheap", "open"], required=True)
    args = parser.parse_args()

    items = load_items()
    rows = run_model(args.model, items)

    file_exists = os.path.exists(OUT_PATH)
    with open(OUT_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    n_correct = sum(1 for r in rows if r["correct"])
    print(f"\n{args.model}: {n_correct}/{len(rows)} correct. Appended to {OUT_PATH}")

if __name__ == "__main__":
    main()