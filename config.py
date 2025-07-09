# config.py
import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gpt-4o").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Example: support for additional providers
LLAMA_SERVER_URL = os.getenv("LLAMA_SERVER_URL", "http://localhost:11434")
