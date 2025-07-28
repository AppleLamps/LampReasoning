import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()

# --- OpenRouter configuration -------------------------------------------------

OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise RuntimeError(
        "Environment variable OPENROUTER_API_KEY not set. "
        "Create a .env file with OPENROUTER_API_KEY=your_key or export it before running."
    )

# Default model can be overridden in individual LLM calls
# Use OpenAI GPT-4.1 instead of OpenRouter's auto router. Override via env.
DEFAULT_MODEL: str = os.getenv("OPENROUTER_DEFAULT_MODEL", "openai/gpt-4.1")

# Model to fall back to if a call with DEFAULT_MODEL repeatedly fails.
FALLBACK_MODEL: str = os.getenv("OPENROUTER_FALLBACK_MODEL", "openai/gpt-4o-mini")

# Optional preset ID to use server-side pre-configured parameters
PRESET_ID: str | None = os.getenv("OPENROUTER_PRESET_ID")

# Enable prompt caching (true/false)
CACHE_ENABLED: bool = os.getenv("OPENROUTER_CACHE_ENABLED", "true").lower() == "true"

# Optional headers to help OpenRouter attribution (recommended by docs)
REFERER_HEADER: str | None = os.getenv("OPENROUTER_REFERER")  # e.g. https://yourapp.com
TITLE_HEADER: str | None = os.getenv("OPENROUTER_TITLE")  # e.g. "Orchestrated Solver"

# Base URL for OpenRouter's unified chat endpoint
OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
