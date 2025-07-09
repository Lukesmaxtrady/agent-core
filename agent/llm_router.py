import os
import time
import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional, Callable, Tuple

try:
    import openai
except ImportError:
    openai = None

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import requests
except ImportError:
    requests = None

# Optional: Ollama for local LLMs (REST API)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Google Gemini support (REST API)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/"

# Central usage logging for analytics/dashboards
LLM_USAGE_LOG = "logs/llm_usage_log.json"
os.makedirs(os.path.dirname(LLM_USAGE_LOG), exist_ok=True)

def log_usage(provider, model, prompt, tokens, duration, extra=None):
    data = {
        "timestamp": time.time(),
        "provider": provider,
        "model": model,
        "prompt": prompt[:200],
        "tokens": tokens,
        "duration": duration,
        "extra": extra or {},
    }
    try:
        with open(LLM_USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(str(data) + "\n")
    except Exception:
        pass

# --- Prompt Templating Registry (optional) ---
PROMPT_TEMPLATES = {
    "default": "{prompt}",
    "qa": "Q: {prompt}\nA:",
    "summarize": "Summarize the following:\n\n{prompt}\n\nSummary:",
}

def format_prompt(template: str, prompt: str) -> str:
    return PROMPT_TEMPLATES.get(template, "{prompt}").format(prompt=prompt)

# --- LLM Config ---
LLM_CONFIG = {
    "gpt-4o": {
        "provider": "openai",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": "gpt-4o"
    },
    "gpt-4": {
        "provider": "openai",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": "gpt-4"
    },
    "gpt-3.5-turbo": {
        "provider": "openai",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": "gpt-3.5-turbo"
    },
    "claude-3-opus": {
        "provider": "anthropic",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "model": "claude-3-opus-20240229"
    },
    "claude-3-haiku": {
        "provider": "anthropic",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "model": "claude-3-haiku-20240307"
    },
    "ollama-mistral": {
        "provider": "ollama",
        "model": "mistral"
    },
    "ollama-llama3": {
        "provider": "ollama",
        "model": "llama3"
    },
    "gemini-pro": {
        "provider": "google",
        "api_key": GOOGLE_API_KEY,
        "model": "gemini-pro"
    }
}

DEFAULT_LLM_USE_CASE = {
    "App Building": "gpt-4o",
    "Bot Building": "gpt-4",
    "Agent Upgrades": "claude-3-opus",
    "Coding": "gpt-4o",
    "Summary": "gemini-pro",
    "Quick Reply": "ollama-mistral",
}

# --- Smart LLM Router ---

def route_llm(
    prompt: str,
    use_case: str = "default",
    model_name: Optional[str] = None,
    template: str = "default",
    max_tokens: int = 800,
    stream: bool = False,
    retry: int = 2,
    **kwargs
) -> str:
    """
    Calls the optimal LLM for the use_case, with retries, streaming, fallback, and logging.
    """
    model = model_name or DEFAULT_LLM_USE_CASE.get(use_case, "gpt-4o")
    conf = LLM_CONFIG.get(model)
    if not conf:
        raise ValueError(f"Unknown LLM model: {model}")

    provider = conf["provider"]
    start = time.time()
    result = ""
    tokens = 0

    # Templating
    real_prompt = format_prompt(template, prompt)
    last_exc = None

    for attempt in range(1, retry + 2):
        try:
            if provider == "openai":
                if openai is None:
                    raise ImportError("openai package not installed.")
                client = openai.OpenAI(api_key=conf["api_key"])
                response = client.chat.completions.create(
                    model=conf["model"],
                    messages=[{"role": "user", "content": real_prompt}],
                    max_tokens=max_tokens,
                    stream=stream
                )
                if stream:
                    collected = []
                    for chunk in response:
                        c = chunk.choices[0].delta.content
                        if c:
                            collected.append(c)
                            print(c, end="", flush=True)
                    result = "".join(collected)
                else:
                    result = response.choices[0].message.content
                tokens = response.usage.total_tokens if hasattr(response, "usage") else 0

            elif provider == "anthropic":
                if anthropic is None:
                    raise ImportError("anthropic package not installed.")
                client = anthropic.Anthropic(api_key=conf["api_key"])
                completion = client.messages.create(
                    model=conf["model"],
                    messages=[{"role": "user", "content": real_prompt}],
                    max_tokens=max_tokens,
                    temperature=0.1
                )
                result = completion.content[0].text if hasattr(completion, "content") else completion.completion
                tokens = getattr(completion, "usage", {}).get("total_tokens", 0)

            elif provider == "ollama":
                if requests is None:
                    raise ImportError("requests package not installed.")
                url = f"{OLLAMA_URL}/api/generate"
                res = requests.post(url, json={
                    "model": conf["model"],
                    "prompt": real_prompt,
                    "stream": stream,
                    "options": {"num_predict": max_tokens}
                }, timeout=120)
                if not res.ok:
                    raise RuntimeError(res.text)
                if stream:
                    for line in res.iter_lines(decode_unicode=True):
                        print(line, end="", flush=True)
                    result = ""  # Could collect lines if needed
                else:
                    out = res.json()
                    result = out.get("response", "")
                    tokens = out.get("eval_count", 0)

            elif provider == "google":
                if requests is None or not conf.get("api_key"):
                    raise ImportError("requests or Google API key not configured.")
                url = f"{GOOGLE_API_URL}{conf['model']}:generateContent?key={conf['api_key']}"
                payload = {
                    "contents": [{"parts": [{"text": real_prompt}]}],
                    "generationConfig": {"maxOutputTokens": max_tokens}
                }
                res = requests.post(url, json=payload, timeout=60)
                if not res.ok:
                    raise RuntimeError(res.text)
                out = res.json()
                result = out.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                tokens = 0  # Not always available

            else:
                raise ValueError(f"Unsupported provider: {provider}")

            duration = time.time() - start
            log_usage(provider, model, prompt, tokens, duration, {"use_case": use_case, "attempt": attempt})
            return result

        except Exception as e:
            last_exc = e
            logging.warning(f"[LLM Router] {provider} failed (attempt {attempt}): {e}")
            time.sleep(1)

    logging.error(f"[LLM Router] All retries failed for provider {provider}. Last exception: {last_exc}")
    raise RuntimeError(f"LLM call failed after retries: {last_exc}")

# --- High-level public helpers ---
def llm_infer(prompt, use_case="default", **kwargs):
    return route_llm(prompt, use_case=use_case, **kwargs)

def available_models() -> List[str]:
    return [k for k, v in LLM_CONFIG.items() if v.get("provider")]

def available_providers() -> List[str]:
    return list(set(v.get("provider") for v in LLM_CONFIG.values() if v.get("provider")))

def usage_summary(n=100):
    """Quick analytics for your LLM usage dashboard."""
    log_path = LLM_USAGE_LOG
    stats = {}
    if not os.path.exists(log_path):
        return {}
    with open(log_path, encoding="utf-8") as f:
        lines = f.readlines()[-n:]
    for line in lines:
        try:
            rec = eval(line)
            key = (rec["provider"], rec["model"])
            stats.setdefault(key, 0)
            stats[key] += rec.get("tokens", 0)
        except Exception:
            pass
    return stats

# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    print("Available LLMs:", available_models())
    print("Available Providers:", available_providers())
    print("LLM Usage:", usage_summary())
    out = llm_infer("How can I make my Python agent code more reliable and self-improving?", use_case="Agent Upgrades")
    print("LLM Output:\n", out)
