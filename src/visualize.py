"""Build an interactive, evidence-focused HTML report from the evaluation CSV."""
import csv
import html
import json
import os
import re
from collections import Counter, defaultdict


BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
INPUT_PATH = os.path.join(BASE_DIR, "results", "per_item.csv")
ITEMS_PATH = os.path.join(BASE_DIR, "data", "items.jsonl")
OUTPUT_PATH = os.path.join(BASE_DIR, "results", "report.html")


def read_items():
    with open(ITEMS_PATH, "r", encoding="utf-8") as file:
        return {item["id"]: item for item in map(json.loads, file)}


def load_rows():
    with open(INPUT_PATH, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        if "model_key" not in fieldnames and "odel_key" in fieldnames:
            fieldnames[fieldnames.index("odel_key")] = "model_key"
        required = {"model_key", "item_id", "correct"}
        missing = required - set(fieldnames)
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
        return list(reader)


def number(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def extract_sql(raw_output):
    text = (raw_output or "").strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    match = re.search(r"SELECT\b.*", text, re.DOTALL | re.IGNORECASE)
    text = match.group(0).strip() if match else text
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


def prepare_rows(rows, items):
    prepared = []
    for row in rows:
        item = items.get(row.get("item_id", ""), {})
        prepared.append({
            "model_key": row.get("model_key", "unknown"),
            "model_name": row.get("model_name", ""),
            "item_id": row.get("item_id", ""),
            "question": row.get("question", ""),
            "correct": row.get("correct", "").lower() == "true",
            "reason": row.get("reason", "unknown"),
            "latency_ms": number(row.get("latency_ms"), None),
            "input_tokens": number(row.get("input_tokens"), None),
            "output_tokens": number(row.get("output_tokens"), None),
            "model_sql": extract_sql(row.get("raw_output", "")),
            "raw_output": row.get("raw_output", ""),
            "gold_sql": item.get("gold_sql", "Not available for this item."),
        })
    return prepared


def summarize(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["model_key"]].append(row)
    output = []
    for model_key, model_rows in grouped.items():
        latencies = [r["latency_ms"] for r in model_rows if r["latency_ms"] is not None]
        inputs = [r["input_tokens"] for r in model_rows if r["input_tokens"] is not None]
        outputs = [r["output_tokens"] for r in model_rows if r["output_tokens"] is not None]
        correct = sum(r["correct"] for r in model_rows)
        output.append({
            "key": model_key,
            "name": model_rows[0]["model_name"],
            "correct": correct,
            "total": len(model_rows),
            "accuracy": correct / len(model_rows) if model_rows else 0,
            "avg_latency": sum(latencies) / len(latencies) if latencies else None,
            "p95_latency": sorted(latencies)[max(0, int(len(latencies) * .95) - 1)] if latencies else None,
            "avg_output": sum(outputs) / len(outputs) if outputs else None,
            "errors": dict(Counter(r["reason"] for r in model_rows if not r["correct"])),
        })
    return sorted(output, key=lambda item: (-item["accuracy"], item["key"]))


def display(value, suffix=""):
    return f"{value:,.0f}{suffix}" if value is not None else "-"


def make_report(rows):
    summaries = summarize(rows)
    correct_count = sum(row["correct"] for row in rows)
    errors = len(rows) - correct_count
    model_options = "".join(
        f'<option value="{html.escape(s["key"])}">{html.escape(s["key"])}</option>'
        for s in summaries
    )
    row_json = json.dumps(rows, ensure_ascii=True).replace("</", "<\\/")
    top_accuracy = summaries[0]["accuracy"] if summaries else 0
    cards = f"""
      <div class="headline-card"><span>Rows evaluated</span><strong>{len(rows):,}</strong><small>Every row counts toward accuracy</small></div>
      <div class="headline-card"><span>Overall correct</span><strong>{correct_count:,} <em>/ {len(rows):,}</em></strong><small>{correct_count / len(rows):.1%} overall accuracy</small></div>
      <div class="headline-card"><span>Incorrect or failed</span><strong class="bad">{errors:,}</strong><small>Use the table below to inspect why</small></div>
      <div class="headline-card"><span>Best model accuracy</span><strong class="good">{top_accuracy:.1%}</strong><small>{html.escape(summaries[0]["key"]) if summaries else "-"}</small></div>
    """
    model_cards = "".join(f"""
      <article class="model-card">
        <div class="model-heading"><div><b>{html.escape(s['key'])}</b><small>{html.escape(s['name'])}</small></div><strong>{s['accuracy']:.1%}</strong></div>
        <div class="accuracy-track"><i style="width:{s['accuracy']:.1%}"></i></div>
        <div class="metric-grid"><span><b>{s['correct']}/{s['total']}</b> correct</span><span><b>{display(s['avg_latency'], ' ms')}</b> avg latency</span><span><b>{display(s['p95_latency'], ' ms')}</b> p95 latency</span><span><b>{display(s['avg_output'])}</b> avg output tokens</span></div>
      </article>""" for s in summaries)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Text-to-SQL | Results</title>
<style>
:root {{ --ink:#17242a; --muted:#65757a; --paper:#f4f6f3; --panel:#fff; --line:#d9e1dc; --green:#087f6c; --red:#c4493d; --navy:#173d4b; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.45 Georgia,serif; }}
main {{ max-width:1280px; margin:auto; padding:34px 22px 70px; }} header {{ display:flex; justify-content:space-between; gap:25px; align-items:end; padding-bottom:30px; border-bottom:1px solid var(--line); }}
h1 {{ max-width:680px; margin:0; font:700 clamp(2.5rem,6vw,5.8rem)/.88 Georgia,serif; letter-spacing:-.055em; }} header p {{ max-width:350px; margin:0; color:var(--muted); }}
.eyebrow {{ margin:0 0 12px; color:var(--green); font:700 12px Consolas,monospace; letter-spacing:.1em; text-transform:uppercase; }}
h2 {{ margin:42px 0 16px; font-size:1.55rem; }} .headline-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:25px; }}
.headline-card,.model-card,.results-panel {{ background:var(--panel); border:1px solid var(--line); border-radius:7px; box-shadow:0 7px 20px #173d4b0b; }} .headline-card {{ padding:18px; }}
.headline-card span,.headline-card small,.metric-grid span,.model-heading small {{ display:block; color:var(--muted); }} .headline-card strong {{ display:block; margin:11px 0 3px; color:var(--navy); font-size:2rem; }} .headline-card em {{ color:var(--muted); font-size:1rem; font-style:normal; }} .headline-card .bad {{ color:var(--red); }} .headline-card .good {{ color:var(--green); }}
.model-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:14px; }} .model-card {{ padding:18px; }} .model-heading {{ display:flex; justify-content:space-between; gap:12px; }} .model-heading b {{ display:block; color:var(--green); font:700 1.1rem Consolas,monospace; text-transform:uppercase; }} .model-heading strong {{ color:var(--green); font-size:1.8rem; }} .accuracy-track {{ height:9px; margin:17px 0; overflow:hidden; background:#e8eeea; border-radius:9px; }} .accuracy-track i {{ display:block; height:100%; background:var(--green); border-radius:inherit; }}
.metric-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; font-size:13px; }} .metric-grid b {{ color:var(--ink); font-size:15px; }}
.results-panel {{ overflow:hidden; }} .toolbar {{ display:flex; flex-wrap:wrap; gap:10px; padding:15px; background:#edf2ee; border-bottom:1px solid var(--line); }} input,select {{ min-height:38px; padding:8px 11px; color:var(--ink); background:white; border:1px solid #bccbc2; border-radius:4px; font:14px Georgia,serif; }} input {{ flex:1 1 260px; }} .count {{ margin-left:auto; align-self:center; color:var(--muted); }} .table-wrap {{ overflow:auto; max-height:670px; }} table {{ width:100%; min-width:1050px; border-collapse:collapse; }} th,td {{ padding:12px 14px; text-align:left; vertical-align:top; border-bottom:1px solid var(--line); }} th {{ position:sticky; top:0; z-index:1; color:var(--muted); background:#f8faf8; font:700 11px Consolas,monospace; letter-spacing:.06em; text-transform:uppercase; }} td {{ max-width:360px; }} tr.hidden {{ display:none; }} .status {{ display:inline-block; padding:4px 7px; border-radius:3px; font:700 11px Consolas,monospace; text-transform:uppercase; }} .status.ok {{ color:#086b5b; background:#dff3eb; }} .status.fail {{ color:#a2342c; background:#ffe7e2; }} .mono {{ white-space:pre-wrap; word-break:break-word; font:12px/1.45 Consolas,monospace; }} details {{ min-width:230px; }} summary {{ cursor:pointer; color:var(--navy); font-weight:bold; }} details div {{ margin-top:8px; padding:10px; overflow:auto; max-height:180px; background:#f5f7f5; border-left:3px solid var(--line); }} .reason {{ color:var(--red); font:12px Consolas,monospace; }} footer {{ margin-top:16px; color:var(--muted); font-size:13px; }}
@media(max-width:780px) {{ main {{ padding:24px 14px 50px; }} header {{ display:block; }} header p {{ margin-top:18px; }} .headline-grid {{ grid-template-columns:1fr 1fr; }} .count {{ width:100%; margin-left:0; }} }} @media(max-width:470px) {{ .headline-grid {{ grid-template-columns:1fr; }} }}
</style></head><body><main>
<header><div><p class="eyebrow">Project 0 / text-to-SQL bake-off</p><h1>What actually happened?</h1></div><p>This report turns every CSV row into evidence: whether it passed, why it failed, what SQL the model produced, and what SQL the test expected.</p></header>
<section class="headline-grid">{cards}</section>
<h2>Model comparison</h2><section class="model-grid">{model_cards or '<p>No model rows found.</p>'}</section>
<h2>Every evaluated item</h2><section class="results-panel"><div class="toolbar"><input id="search" type="search" placeholder="Search questions, item IDs, SQL, or reasons..."><select id="model"><option value="">All models</option>{model_options}</select><select id="status"><option value="">All outcomes</option><option value="correct">Correct only</option><option value="failed">Failed only</option></select><span class="count" id="count"></span></div><div class="table-wrap"><table><thead><tr><th>Outcome</th><th>Model / item</th><th>Question</th><th>Why</th><th>Generated SQL</th><th>Expected SQL</th><th>Raw model output</th></tr></thead><tbody id="rows"></tbody></table></div></section>
<footer>Generated from <strong>results/per_item.csv</strong> with <code>python src/visualize.py</code>. Expand a row's SQL or raw output to inspect the exact response.</footer>
</main><script>
const results = {row_json};
const rowsElement = document.getElementById('rows'); const countElement = document.getElementById('count');
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
function render() {{ const query = document.getElementById('search').value.toLowerCase(); const model = document.getElementById('model').value; const status = document.getElementById('status').value; let visible = 0;
rowsElement.innerHTML = results.map(row => {{ const haystack = [row.item_id,row.question,row.reason,row.model_sql,row.gold_sql,row.raw_output].join(' ').toLowerCase(); const matches = (!query || haystack.includes(query)) && (!model || row.model_key === model) && (!status || (status === 'correct' ? row.correct : !row.correct)); if (!matches) return ''; visible++;
const outcome = row.correct ? '<span class="status ok">Correct</span>' : '<span class="status fail">Failed</span>'; const details = (label, value) => '<details><summary>'+label+'</summary><div class="mono">'+esc(value)+'</div></details>';
return '<tr><td>'+outcome+'</td><td><b>'+esc(row.model_key)+'</b><br><small>'+esc(row.item_id)+'</small></td><td>'+esc(row.question)+'</td><td><span class="reason">'+esc(row.reason)+'</span><br><small>'+ (row.latency_ms == null ? '-' : Math.round(row.latency_ms)+' ms') +' / '+ (row.input_tokens == null ? '-' : Math.round(row.input_tokens)+' in, '+Math.round(row.output_tokens)+' out') +'</small></td><td>'+details('View generated SQL',row.model_sql)+'</td><td>'+details('View expected SQL',row.gold_sql)+'</td><td>'+details('View raw output',row.raw_output)+'</td></tr>'; }}).join(''); countElement.textContent = visible+' of '+results.length+' rows'; }}
['search','model','status'].forEach(id => document.getElementById(id).addEventListener('input', render)); render();
</script></body></html>"""


def main():
    rows = prepare_rows(load_rows(), read_items())
    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        file.write(make_report(rows))
    print(f"Wrote {OUTPUT_PATH} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
