# llm_config.py

import os

# --- MODEL CONFIG ---

LLM_CONFIG = {
    "deepseek-coder": {
        "type": "local",
        "group": "FREE",
        "display": "DeepSeek Coder (Ollama)",
        "api_key": None,
        "health_check": lambda: True  # Extend for real health check
    },
    "codewhisperer": {
        "type": "api",
        "group": "FREE",
        "display": "AWS CodeWhisperer",
        "api_key": os.environ.get("CODEWHISPERER_API_KEY"),
        "health_check": lambda: True
    },
    "flowiseai": {
        "type": "api",
        "group": "FREE",
        "display": "FlowiseAI",
        "api_key": os.environ.get("FLOWISEAI_API_KEY"),
        "health_check": lambda: True
    },
    "mistral-7b": {
        "type": "local",
        "group": "VALUE",
        "display": "Mistral 7B (Ollama/HF)",
        "api_key": None,
        "health_check": lambda: True  # Change as needed
    },
    "claude-haiku": {
        "type": "anthropic",
        "group": "VALUE",
        "display": "Claude 3 Haiku",
        "api_key": os.environ.get("ANTHROPIC_API_KEY"),
        "health_check": lambda: bool(os.environ.get("ANTHROPIC_API_KEY"))
    },
    "gpt-4.1": {
        "type": "openai",
        "group": "PERFORMANCE",
        "display": "GPT-4.1 (OpenAI/OpenRouter)",
        "api_key": os.environ.get("OPENAI_API_KEY"),
        "health_check": lambda: bool(os.environ.get("OPENAI_API_KEY"))
    },
    "claude-3-opus": {
        "type": "anthropic",
        "group": "PERFORMANCE",
        "display": "Claude 3 Opus (Anthropic)",
        "api_key": os.environ.get("ANTHROPIC_OPUS_API_KEY"),
        "health_check": lambda: bool(os.environ.get("ANTHROPIC_OPUS_API_KEY"))
    },
    "gemini-1.5": {
        "type": "google",
        "group": "PREMIUM",
        "display": "Gemini 1.5 (Google)",
        "api_key": os.environ.get("GOOGLE_GEMINI_API_KEY"),
        "health_check": lambda: bool(os.environ.get("GOOGLE_GEMINI_API_KEY"))
    }
}

# --- ENSEMBLE PRESETS ---
ENSEMBLE_MODES = {
    "default": ["deepseek-coder", "codewhisperer"],
    "value": ["claude-haiku", "mistral-7b", "deepseek-coder"],
    "performance": ["claude-haiku", "gpt-4.1"],
    "premium": ["claude-3-opus", "gpt-4.1", "gemini-1.5"],
}

# --- TIERS ---
TIERS = {
    "FREE": ["deepseek-coder", "codewhisperer", "flowiseai"],
    "VALUE": ["claude-haiku", "mistral-7b", "deepseek-coder", "flowiseai"],
    "PERFORMANCE": ["gpt-4.1", "claude-haiku", "mistral-7b"],
    "PREMIUM": ["claude-3-opus", "gpt-4.1", "gemini-1.5", "claude-haiku", "mistral-7b", "deepseek-coder"],
}

# --- USE-CASE DEFAULTS (per tier, customizable) ---
DEFAULT_LLM_USE_CASE = {
    "code": "deepseek-coder",
    "chat": "codewhisperer",
    "agent": "flowiseai"
}

BEST_VALUE_LLM_USE_CASE = {
    "code": "claude-haiku",
    "chat": "claude-haiku",
    "agent": "flowiseai",
    "bot": "flowiseai",
    "verify": "gpt-4.1"
}

PERFORMANCE_LLM_USE_CASE = {
    "code": "gpt-4.1",
    "chat": "claude-haiku",
    "agent": "flowiseai",
    "bot": "flowiseai",
    "verify": "gpt-4.1"
}

PREMIUM_LLM_USE_CASE = {
    "code": "claude-3-opus",
    "chat": "claude-3-opus",
    "agent": "flowiseai",
    "bot": "flowiseai",
    "verify": "gpt-4.1"
}
