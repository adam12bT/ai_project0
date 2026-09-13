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
_next_request_at = 0.0


def _reset_seconds(value):
    """Convert Groq reset values such as '6s' or '1m2.5s' to seconds."""
    if not value:
        return 0.0
    text = str(value).strip().lower()
    total = 0.0
    number = ""
    units = {"h": 3600, "m": 60, "s": 1, "ms": 0.001}
    index = 0
    while index < len(text):
        if text[index].isdigit() or text[index] == ".":
            number += text[index]
            index += 1
            continue
        unit = "ms" if text[index:index + 2] == "ms" else text[index]
        if number and unit in units:
            total += float(number) * units[unit]
        number = ""
        index += len(unit)
    return total


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
              temperature=0, max_tokens=300, max_retries=None):
    global _next_request_at
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    if max_retries is None:
        max_retries = int(os.environ.get("GROQ_MAX_RETRIES", "5"))

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
        wait_seconds = _next_request_at - time.time()
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read())
                remaining_tokens = resp.headers.get("x-ratelimit-remaining-tokens")
                reset_tokens = _reset_seconds(resp.headers.get("x-ratelimit-reset-tokens"))
                remaining_requests = resp.headers.get("x-ratelimit-remaining-requests")
                reset_requests = _reset_seconds(resp.headers.get("x-ratelimit-reset-requests"))
                estimated_input_tokens = max(1, (len(user_prompt) + len(system_prompt or "") + 3) // 4)
                if remaining_tokens and int(remaining_tokens) <= estimated_input_tokens + 128:
                    _next_request_at = max(_next_request_at, time.time() + reset_tokens)
                if remaining_requests and int(remaining_requests) <= 1:
                    _next_request_at = max(_next_request_at, time.time() + reset_requests)
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
            if e.code == 429:
                reset = max(
                    _reset_seconds(e.headers.get("x-ratelimit-reset-tokens")),
                    _reset_seconds(e.headers.get("x-ratelimit-reset-requests")),
                )
                _next_request_at = max(_next_request_at, time.time() + reset)
                raise RuntimeError(
                    f"Groq rate limit reached. Retry in about {max(1, round(reset))} seconds "
                    "or use a smaller batch."
                ) from e
            raise


if __name__ == "__main__":
    text, latency_ms, usage = call_groq(
        "openai/gpt-oss-20b", "Say hello in exactly 3 words.", max_tokens=200
    )
    print(f"output: {text!r}")
    print(f"latency: {latency_ms:.0f}ms  usage: {usage}")