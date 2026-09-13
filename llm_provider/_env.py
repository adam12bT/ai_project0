"""
Minimal .env loader — no python-dotenv dependency needed.

Looks for a .env file in the project root (one level up from this file)
and loads KEY=VALUE lines into os.environ, without overwriting anything
already set in the real environment (so `$env:GROQ_API_KEY=...` in your
terminal still wins if you set both).
"""
import os

def load_dotenv():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
