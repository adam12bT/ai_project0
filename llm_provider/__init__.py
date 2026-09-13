"""
llm_provider — a tiny, dependency-free package for calling LLMs.

Standalone use:
    from llm_provider import call_model
    text, latency_ms, usage = call_model("groq", "llama-3.3-70b-versatile", "hello")
    text, latency_ms, usage = call_model("ollama", "qwen2.5-coder:7b", "hello")

Or import a provider directly:
    from llm_provider.groq import call_groq
    from llm_provider.ollama import call_ollama

Each call returns (text: str, latency_ms: float, usage: dict with
'input_tokens'/'output_tokens'). This is the exact interface Project 0's
src/run.py uses, factored out here so you can drop it into any project.
"""
from ._env import load_dotenv
load_dotenv()

from .groq import call_groq
from .ollama import call_ollama

PROVIDERS = {
    "groq": call_groq,
    "ollama": call_ollama,
}


def call_model(provider, model_name, user_prompt, system_prompt=None,
                temperature=0, max_tokens=300, **kwargs):
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider '{provider}'. Options: {list(PROVIDERS)}")
    fn = PROVIDERS[provider]
    return fn(model_name, user_prompt, system_prompt=system_prompt,
               temperature=temperature, max_tokens=max_tokens, **kwargs)


__all__ = ["call_model", "call_groq", "call_ollama"]
