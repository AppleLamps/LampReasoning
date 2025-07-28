# Orchestrated AI Solver

A minimal, fully-runnable reference implementation of a multi-agent "structured reasoning" system inspired by Aman Madaan’s thesis *Enhancing Language Models with Structured Reasoning*.

The orchestrator decomposes a complex natural-language query, generates Python code for sub-calculations, self-critiques intermediate results, refines if needed, and finally synthesizes an answer.

## Directory layout

```
.
├── agents.py         # All LLM-powered agent helper functions
├── config.py         # Loads OpenRouter API key & model config
├── main.py           # Orchestrator CLI entry point
├── requirements.txt  # Python deps (requests, python-dotenv)
└── README.md         # You are here
```

## Quick start

1. **Install deps**

   ```bash
   python -m venv venv            # optional but recommended
   source venv/bin/activate       # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure OpenRouter**

   Create a `.env` file next to `config.py`:

   ```text
   OPENROUTER_API_KEY="sk-or-your-key-here"
   # Optional overrides
   # OPENROUTER_DEFAULT_MODEL="openai/gpt-4o"
   # OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
   ```

3. **Run**

   ```bash
   python main.py                 # uses built-in apple example
   # or
   python main.py "Your complex word problem here"
   ```

The console shows the plan, generated code, self-critique feedback loops, and the final answer.

## Security note

`main.py` includes a tiny AST-based sandbox that allows only basic arithmetic operations. **Do not** execute untrusted code beyond those constraints without additional hardening.

## Extending

See the original project write-up for ideas: add web-search agents, richer memory, a web UI, etc. Contribution welcome!
