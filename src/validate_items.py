"""Verify every gold SQL query and gold_row_count in data/items.jsonl."""
import json
import os
import sqlite3


BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(BASE_DIR, "Chinook_Sqlite.sqlite")
ITEMS_PATH = os.path.join(BASE_DIR, "data", "items.jsonl")


def main():
    with open(ITEMS_PATH, "r", encoding="utf-8") as file:
        items = [json.loads(line) for line in file]

    mismatches = []
    errors = []
    with sqlite3.connect(DB_PATH) as database:
        for item in items:
            try:
                actual_count = len(database.execute(item["gold_sql"]).fetchall())
            except sqlite3.Error as error:
                errors.append((item["id"], str(error)))
                continue
            expected_count = int(item["gold_row_count"])
            if actual_count != expected_count:
                mismatches.append((item["id"], expected_count, actual_count))

    print(f"Checked {len(items)} gold queries.")
    print(f"SQL errors: {len(errors)}")
    print(f"Row-count mismatches: {len(mismatches)}")
    for item_id, error in errors:
        print(f"  {item_id}: {error}")
    for item_id, expected, actual in mismatches:
        print(f"  {item_id}: expected {expected}, actual {actual}")

    return 1 if errors or mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
