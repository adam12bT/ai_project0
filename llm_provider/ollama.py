"""
Standalone Ollama caller. Import this in any project:

    from llm_provider.ollama import call_ollama
    text, latency_ms, usage = call_ollama("qwen2.5-coder:7b", "hello")

Requires Ollama running locally (https://ollama.com), default at
http://localhost:11434. Pull a model first: `ollama pull qwen2.5-coder:7b`.
"""
import json
import time
import urllib.request

OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"


def call_ollama(model_name, user_prompt, system_prompt=None,
                 temperature=0, max_tokens=300, host=OLLAMA_ENDPOINT):
    payload = {
        "model": model_name,
        "prompt": user_prompt,
        "stream": False,
        # num_ctx: Ollama's default context window (often 2048) can be
        # smaller than prompt_tokens + max_tokens once max_tokens is raised
        # for reasoning-style budgets — that would silently truncate input
        # or cut the response short. Size it to comfortably fit both.
        "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 4096},
    }
    if system_prompt:
        payload["system"] = system_prompt

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        host, data=data, headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read())
    latency_ms = (time.perf_counter() - t0) * 1000
    text = body.get("response", "")
    usage = {
        "input_tokens": body.get("prompt_eval_count", 0),
        "output_tokens": body.get("eval_count", 0),
    }
    return text, latency_ms, usage


if __name__ == "__main__":
    # Quick smoke test: python3 -m llm_provider.ollama
    text, latency_ms, usage = call_ollama(
        "qwen2.5-coder:7b", "Say hello in exactly 3 words.", max_tokens=20
    )
    print(f"output: {text!r}")
    print(f"latency: {latency_ms:.0f}ms  usage: {usage}")