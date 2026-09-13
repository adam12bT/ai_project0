"""
Reads results/per_item.csv and produces results/summary.csv with, per model:
  - accuracy as n/total
  - p50 / p95 latency (ms)
  - cost per 1k requests today, and at 100x traffic
  - (for the API models) break-even request volume vs the self-hosted model

Fill in PRICING with your models' real list prices (USD per 1M tokens) and
HARDWARE with your self-hosted model's real hourly cost and throughput.
Prices change — verify current numbers on the provider's pricing page
before you turn this in.
"""
import csv
import statistics
import os

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "results", "per_item.csv")
SUMMARY_PATH = os.path.join(os.path.dirname(__file__), "..", "results", "summary.csv")

# --- USD per 1,000,000 tokens, PAID (Developer) tier rates — used only for
# the 100x-traffic projection, since the free tier is rate-limited (see
# FREE_TIER_DAILY_REQUESTS below) and can't sustain 100x volume. Today's
# actual cost is $0 on the free tier. These must match MODEL_CONFIG in
# src/run.py exactly — verify current numbers at https://groq.com/pricing
# before you submit, Groq revises these often (checked 2026-09-12, from
# Groq's own model docs at console.groq.com/docs/models). ---
PRICING = {
    "top":   {"input_per_mtok": 0.15, "output_per_mtok": 0.60},   # openai/gpt-oss-120b
    "cheap": {"input_per_mtok": 0.075, "output_per_mtok": 0.30},  # openai/gpt-oss-20b
}
# Free-tier daily request cap per model — 1,000 requests/day for both
# openai/gpt-oss-120b and openai/gpt-oss-20b as of 2026-09-12. Check
# https://console.groq.com/docs/rate-limits for current numbers.
FREE_TIER_DAILY_REQUESTS = {
    "top": 1000,
    "cheap": 1000,
}
# --- Self-hosted "open" model hardware cost model. Fill in your real setup. ---
HARDWARE = {
    "cost_per_hour_usd": 0.50,   # e.g. cloud GPU rental, or amortized local GPU cost
    "requests_per_hour": 1200,   # measured throughput at your batch size
}
# ---------------------------------------------------------------------

def load_rows():
    rows = []
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows

def percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)

def summarize_model(model_key, rows):
    model_rows = [r for r in rows if r["model_key"] == model_key]
    n = len(model_rows)
    n_correct = sum(1 for r in model_rows if r["correct"] == "True")
    latencies = [float(r["latency_ms"]) for r in model_rows if r["latency_ms"]]
    in_toks = sum(int(r["input_tokens"]) for r in model_rows if r["input_tokens"])
    out_toks = sum(int(r["output_tokens"]) for r in model_rows if r["output_tokens"])
    avg_in = in_toks / n if n else 0
    avg_out = out_toks / n if n else 0

    summary = {
        "model_key": model_key,
        "n_correct": n_correct,
        "n_total": n,
        "accuracy": round(n_correct / n, 3) if n else None,
        "p50_latency_ms": round(percentile(latencies, 50), 1) if latencies else None,
        "p95_latency_ms": round(percentile(latencies, 95), 1) if latencies else None,
    }

    if model_key in PRICING:
        p = PRICING[model_key]
        paid_cost_per_req = (avg_in / 1_000_000 * p["input_per_mtok"]) + \
                             (avg_out / 1_000_000 * p["output_per_mtok"])
        # Today's real cost on the free tier is $0 (rate-limited, not metered).
        summary["cost_per_1k_requests_usd"] = 0.0
        summary["cost_per_1k_requests_note"] = "free tier (rate-limited, not metered)"
        # What this SAME usage would cost if billed at Groq's published
        # paid-tier rate, based on the actual average input/output tokens
        # measured from your real runs — i.e. "the price is $0 because it's
        # free, but here's what you'd actually be paying for this traffic
        # if it weren't." Always computed, regardless of volume/free-tier
        # cap (unlike cost_at_100x_traffic_usd below, which only applies
        # once volume would realistically force you onto the paid tier).
        summary["estimated_paid_price_per_1k_requests_usd"] = round(paid_cost_per_req * 1000, 4)
        summary["estimated_paid_price_note"] = (
            "what this usage would cost at Groq's paid-tier rate, if it weren't free"
        )
        # At 100x traffic, check whether daily volume would blow past the
        # free-tier cap; if so, the realistic cost is the paid tier rate.
        # NOTE: this is still "cost per 1,000 requests" (same unit as the
        # "today" figure above), just priced at whichever tier applies at
        # that volume — it is NOT "total cost of 100,000 requests". API
        # pricing is linear per token, so the per-1k-request price doesn't
        # itself change with volume; only *which tier* (free vs paid) does.
        daily_cap = FREE_TIER_DAILY_REQUESTS.get(model_key)
        projected_daily_reqs = n * 100  # rough proxy: today's test volume x 100
        if daily_cap and projected_daily_reqs > daily_cap:
            summary["cost_at_100x_traffic_usd"] = round(paid_cost_per_req * 1000, 2)
            summary["cost_at_100x_traffic_note"] = (
                f"exceeds free-tier cap (~{daily_cap}/day) — priced at paid tier rate"
            )
        else:
            summary["cost_at_100x_traffic_usd"] = 0.0
            summary["cost_at_100x_traffic_note"] = "still within free-tier daily cap"
    elif model_key == "open":
        cost_per_req = HARDWARE["cost_per_hour_usd"] / HARDWARE["requests_per_hour"]
        summary["cost_per_1k_requests_usd"] = round(cost_per_req * 1000, 4)
        # Fixed hardware cost per request doesn't change with traffic volume
        # (as long as you stay within the box's throughput capacity), so
        # this is intentionally the same number as cost_per_1k_requests_usd
        # above — that flat line vs. the API's free-to-paid jump is exactly
        # the point of the self-hosted vs. API comparison.
        summary["cost_at_100x_traffic_usd"] = round(cost_per_req * 1000, 4)

    return summary

def break_even_volume(api_cost_per_req, self_hosted_hourly_cost, self_hosted_req_per_hour):
    """
    Requests per month at which self-hosting becomes cheaper than the API,
    assuming the self-hosted box runs 24/7 regardless of load
    (fixed hourly cost) once you commit to it.
    """
    self_hosted_cost_per_req = self_hosted_hourly_cost / self_hosted_req_per_hour
    if api_cost_per_req <= self_hosted_cost_per_req:
        return None  # API is always cheaper per request at this throughput assumption
    # Fixed monthly self-hosting cost vs marginal API cost per request:
    monthly_fixed = self_hosted_hourly_cost * 24 * 30
    return monthly_fixed / api_cost_per_req  # requests/month where costs cross

def main():
    rows = load_rows()
    model_keys = sorted(set(r["model_key"] for r in rows))
    summaries = [summarize_model(k, rows) for k in model_keys]

    with open(SUMMARY_PATH, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["model_key", "n_correct", "n_total", "accuracy",
                      "p50_latency_ms", "p95_latency_ms",
                      "cost_per_1k_requests_usd",
                      "estimated_paid_price_per_1k_requests_usd",
                      "cost_at_100x_traffic_usd"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for s in summaries:
            writer.writerow(s)

    print(f"Wrote {SUMMARY_PATH}")
    for s in summaries:
        print(s)

    # Example break-even: top model's PAID-tier rate vs self-hosted open model.
    # (Uses the paid rate, not $0, since the free tier can't sustain the
    # volume where break-even questions become relevant in the first place.)
    if "top" in PRICING:
        p = PRICING["top"]
        top_rows = [r for r in rows if r["model_key"] == "top" and r["input_tokens"]]
        if top_rows:
            avg_in = sum(int(r["input_tokens"]) for r in top_rows) / len(top_rows)
            avg_out = sum(int(r["output_tokens"]) for r in top_rows) / len(top_rows)
            api_cost_per_req = (avg_in / 1_000_000 * p["input_per_mtok"]) + \
                                (avg_out / 1_000_000 * p["output_per_mtok"])
            be = break_even_volume(api_cost_per_req, HARDWARE["cost_per_hour_usd"],
                                    HARDWARE["requests_per_hour"])
            if be:
                print(f"\nBreak-even (top model's paid-tier rate vs self-hosted): "
                      f"~{be:,.0f} requests/month")
            else:
                print("\nThe paid API tier is cheaper than self-hosting at this "
                      "throughput assumption.")

if __name__ == "__main__":
    main()