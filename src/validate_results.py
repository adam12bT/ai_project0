"""Re-score results/per_item.csv and report whether its saved verdicts are reliable."""
import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from score import score


BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(BASE_DIR, "Chinook_Sqlite.sqlite")
ITEMS_PATH = os.path.join(BASE_DIR, "data", "items.jsonl")
RESULTS_PATH = os.path.join(BASE_DIR, "results", "per_item.csv")


def load_items():
    with open(ITEMS_PATH, "r", encoding="utf-8") as file:
        return {item["id"]: item for item in map(json.loads, file)}


def load_results():
    with open(RESULTS_PATH, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        if "model_key" not in fieldnames and "odel_key" in fieldnames:
            fieldnames[fieldnames.index("odel_key")] = "model_key"
        return list(reader)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="validate only this model key")
    parser.add_argument("--verbose", action="store_true", help="print every failing item")
    args = parser.parse_args()

    items = load_items()
    rows = load_results()
    if args.model:
        rows = [row for row in rows if row.get("model_key") == args.model]

    if not rows:
        print("No matching result rows found.")
        return 1

    counts = Counter()
    mismatches = []
    missing_items = []
    seen = defaultdict(list)

    for row in rows:
        item_id = row.get("item_id", "")
        seen[row.get("model_key", "unknown")].append(item_id)
        item = items.get(item_id)
        if not item:
            missing_items.append(item_id)
            continue

        verdict = score(row.get("raw_output", ""), item["gold_sql"], DB_PATH)
        saved_correct = row.get("correct", "").lower() == "true"
        counts[(row.get("model_key", "unknown"), verdict["correct"])] += 1
        if saved_correct != verdict["correct"]:
            mismatches.append((row, verdict))
        if args.verbose and not verdict["correct"]:
            print(f"{row.get('model_key')} {item_id}: {verdict['reason']}")

    print(f"Validated {len(rows)} rows against {len(items)} gold questions.")
    for model_key in sorted({row.get("model_key", "unknown") for row in rows}):
        correct = counts[(model_key, True)]
        total = sum(counts[(model_key, value)] for value in (True, False))
        accuracy = correct / total if total else 0
        print(f"{model_key}: {correct}/{total} correct ({accuracy:.1%})")

    duplicate_groups = {
        model: sorted(item_ids)
        for model, item_ids in seen.items()
        if len(item_ids) != len(set(item_ids))
    }
    all_item_ids = set(items)
    missing_by_model = {
        model: sorted(all_item_ids - set(item_ids))
        for model, item_ids in seen.items()
        if all_item_ids - set(item_ids)
    }

    print(f"Verdict mismatches: {len(mismatches)}")
    print(f"Unknown item IDs: {len(missing_items)}")
    print(f"Duplicate items: {sum(len(ids) - len(set(ids)) for ids in seen.values())}")
    print(f"Missing items by model: {sum(len(ids) for ids in missing_by_model.values())}")

    if mismatches:
        print("Saved CSV verdicts disagree with score.py:")
        for row, verdict in mismatches[:10]:
            print(f"  {row.get('model_key')} {row.get('item_id')}: saved={row.get('correct')} recalculated={verdict['correct']} ({verdict['reason']})")
    return 1 if mismatches or missing_items or duplicate_groups else 0


if __name__ == "__main__":
    raise SystemExit(main())
