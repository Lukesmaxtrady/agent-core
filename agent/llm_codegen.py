# agent/llm_codegen.py

import os
import requests
from termcolor import cprint, colored

# Optional: import Anthropic, Ollama, DeepSeek, etc. as needed
try:
    import openai
except ImportError:
    openai = None

try:
    import anthropic
except ImportError:
    anthropic = None

# --- API Keys and URLs (edit your .env or config as needed!) ---
OPENAI_KEY     = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
DEEPSEEK_KEY   = os.getenv("DEEPSEEK_API_KEY", "")

def usage_tip(backend):
    tips = {
        "openai":     "💡 Using OpenAI GPT-4o/3.5. Best for most code, docs, multi-modal tasks.",
        "anthropic":  "💡 Using Anthropic Claude models. Great for logic, summaries, safer code.",
        "ollama":     "💡 Using Ollama (local or private LLMs). Run big models on your own server!",
        "deepseek":   "💡 Using DeepSeek. Fast, affordable, trending for code and research.",
    }
    cprint(tips.get(backend, ""), "cyan")

def llm_codegen(
    prompt, backend="openai", model="gpt-4o", system_msg=None, max_tokens=2048, print_prompt=True
):
    """
    Call any supported LLM backend for code/text output.
    Supported: openai, anthropic, ollama, deepseek (add more as needed).
    Returns string (code or response).
    """
    if print_prompt:
        cprint(f"\n[LLM Codegen] Backend: {backend} | Model: {model}", "magenta")
        cprint(f"Prompt: {colored(prompt[:180], 'yellow')}{'...' if len(prompt)>180 else ''}", "white")
        usage_tip(backend)
    try:
        # --- OpenAI (gpt-4o, gpt-4, gpt-3.5, etc) ---
        if backend == "openai":
            if openai is None:
                raise ImportError("openai not installed. Please pip install openai.")
            openai.api_key = OPENAI_KEY
            messages = [
                {
                    "role": "system",
                    "content": system_msg or "You are a world-class AI software engineer. Output only code files, never explanations."
                },
                {"role": "user", "content": prompt}
            ]
            resp = openai.ChatCompletion.create(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=0.2
            )
            return resp['choices'][0]['message']['content'].strip()
        # --- Anthropic Claude (claude-3-opus, sonnet, haiku) ---
        elif backend == "anthropic" and anthropic is not None:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            completion = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                system=system_msg or "You are a world-class coder. Output only code files."
            )
            return completion.content[0].text.strip()
        # --- Ollama (local/private models: phi, llama3, codeqwen, etc) ---
        elif backend == "ollama":
            data = {
                "model": model,
                "prompt": prompt,
                "options": {"temperature": 0.18, "num_predict": max_tokens}
            }
            r = requests.post(OLLAMA_URL, json=data, timeout=120)
            r.raise_for_status()
            return r.json().get("response", "").strip()
        # --- DeepSeek (https://deepseek.com/) ---
        elif backend == "deepseek":
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            }
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        # --- Future: add more backends here! ---
        else:
            raise RuntimeError(f"Unknown or unsupported LLM backend: {backend}")

    except Exception as e:
        cprint(f"\n[LLM ERROR] {str(e)}", "red", attrs=["bold"])
        if backend != "openai":
            cprint("💡 Tip: Try fallback backend: openai, anthropic, or ollama.", "yellow")
        return f"# ERROR: {str(e)}"

# === Usage Example (test) ===
if __name__ == "__main__":
    resp = llm_codegen("Write a function that returns Fibonacci numbers as a list.", backend="openai", model="gpt-4o")
    print("\n[LLM Response]\n")
    print(resp)
