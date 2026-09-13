"""
The ONE prompt template used for all three models, unchanged.
Do not edit this per-model — that would break the bake-off's fairness rule.
"""

with open("schema.sql", "r", encoding="utf-8") as f:
    SCHEMA = f.read().strip()

SYSTEM_PROMPT = (
    "You are a SQL generator for a SQLite database. Output ONLY a single valid "
    "SQLite SELECT query that answers the question. Do not output any explanation, "
    "comments, or markdown fences. Output the raw SQL query only, ending in a semicolon. "
    "Select ONLY the columns explicitly requested in the question — do not add extra columns "
    "such as IDs or technical keys unless the question specifically asks for them.\n\n"
    f"### SQLite schema\n{SCHEMA}"
)

def build_user_prompt(question: str) -> str:
    return question