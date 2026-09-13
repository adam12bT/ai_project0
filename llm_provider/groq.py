"""
Standalone Groq caller. Import this in any project:

    from llm_provider.groq import call_groq
    text, latency_ms, usage = call_groq("llama-3.3-70b-versatile", "hello")

Reads GROQ_API_KEY from the environment. Free tier: no card needed,
rate-limited (~30 requests/min, ~1,000/day per model). Retries on
HTTP 429 using the server's Retry-After header.
"""
import json
import os
import time
import urllib.request
import urllib.error

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
# Both models used in this project (qwen/qwen3.6-27b and openai/gpt-oss-20b)
# have a 131K-token context window on Groq (verified at
# console.groq.com/docs/model/... — check again if you swap models).
# The old default of 8192 here silently clamped max_tokens far below what
# a reasoning model needs to finish its <think> block on top of a real
# prompt, which is what caused run.py's MAX_TOKENS bump to still get cut
# short. Override with GROQ_CONTEXT_LIMIT if you use a different model.
DEFAULT_CONTEXT_LIMIT = 131072
TOKEN_SAFETY_MARGIN = 128


def safe_output_tokens(user_prompt, system_prompt, requested_tokens):
    """Keep input plus requested output below a conservative context limit."""
    context_limit = int(os.environ.get("GROQ_CONTEXT_LIMIT", DEFAULT_CONTEXT_LIMIT))
    prompt_chars = len(user_prompt) + len(system_prompt or "")
    estimated_input_tokens = max(1, (prompt_chars + 3) // 4)
    available = context_limit - estimated_input_tokens - TOKEN_SAFETY_MARGIN
    if available < 32:
        raise ValueError(
            f"Groq prompt is too large: estimated {estimated_input_tokens} input "
            f"tokens for a {context_limit}-token context"
        )
    return min(requested_tokens, available)


def call_groq(model_name, user_prompt, system_prompt=None,
              temperature=0, max_tokens=300, max_retries=5):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    max_tokens = safe_output_tokens(user_prompt, system_prompt, max_tokens)

    payload = {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GROQ_ENDPOINT, data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
)

    for attempt in range(max_retries):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read())
            latency_ms = (time.perf_counter() - t0) * 1000
            text = body["choices"][0]["message"]["content"]
            usage = {
                "input_tokens": body.get("usage", {}).get("prompt_tokens", 0),
                "output_tokens": body.get("usage", {}).get("completion_tokens", 0),
            }
            return text, latency_ms, usage
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                # Some responses omit Retry-After or send 0/near-0, which
                # would just re-trigger the same 429 immediately — floor it
                # so retries actually wait out the rate-limit window, and
                # cap it so a huge value doesn't hang the batch for ages.
                retry_after = float(e.headers.get("Retry-After", 5))
                retry_after = min(max(retry_after, 3), 60)
                time.sleep(retry_after)
                continue
            raise


if __name__ == "__main__":
    text, latency_ms, usage = call_groq(
        "openai/gpt-oss-20b", "Say hello in exactly 3 words.", max_tokens=200
    )
    print(f"output: {text!r}")
    print(f"latency: {latency_ms:.0f}ms  usage: {usage}")