"""LLM-powered agents for the orchestrated AI solver.

Each helper wraps a call to OpenRouter's /chat/completions endpoint with a
pre-defined system prompt tailored to the agent's role.
"""
from __future__ import annotations

import json
import typing as _t

import requests

import time

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    PRESET_ID,
    CACHE_ENABLED,
    REFERER_HEADER,
    TITLE_HEADER,
)

__all__ = [
    "decompose_problem",
    "generate_code_for_step",
    "self_critique_output",
    "synthesize_answer",
]

_HEADERS: dict[str, str] = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
}
if REFERER_HEADER:
    _HEADERS["HTTP-Referer"] = REFERER_HEADER
if TITLE_HEADER:
    _HEADERS["X-Title"] = TITLE_HEADER


# ---------------------------------------------------------------------------
# Core HTTP helper
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BACKOFF_SECONDS = 2.0


def _call_llm(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    response_format: dict[str, _t.Any] | None = None,
    stream: bool = False,
) -> dict:
    """Robust OpenRouter call with retry, backoff, and model fallback.

    Parameters
    ----------
    messages : list[dict]
        Standard OpenAI-style messages.
    model : str | None
        Model ID; if ``None`` uses DEFAULT_MODEL.
    response_format : dict | None
        JSON schema or other response format spec.
    stream : bool, default False
        If True, enables SSE streaming. Caller must handle stream chunks.
    """

    chosen_model = model or DEFAULT_MODEL

    for attempt in range(_MAX_RETRIES):
        payload: dict[str, _t.Any] = {
            "model": chosen_model,
            "messages": messages,
            "temperature": 0.0,
            "stream": stream,
            "usage": {"include": True},
        }
        if response_format is not None:
            payload["response_format"] = response_format
            # Add this line to ensure the model supports the specified response_format
            payload["provider"] = {"require_parameters": True}

        try:
            resp = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=_HEADERS,
                json=payload,
                timeout=60,
                stream=stream,
            )
            resp.raise_for_status()
            return resp.json() if not stream else resp  # caller handles stream
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response else None
            is_retryable = status in {429, 500, 502, 503, 504}

            if not is_retryable:
                # Print detailed error info for debugging
                error_text = exc.response.text if exc.response else "No response"
                print(f"HTTP {status} Error: {error_text}")
                print(f"Request payload: {json.dumps(payload, indent=2)}")
                raise

            # Switch to fallback after first failure with default model
            if chosen_model != FALLBACK_MODEL and attempt == 0:
                chosen_model = FALLBACK_MODEL

            if attempt == _MAX_RETRIES - 1:
                raise

            time.sleep(_BACKOFF_SECONDS * (attempt + 1))


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

_JSON_SCHEMA_PLAN = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step_num": {"type": "integer"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "calculation",
                            "data_lookup",
                            "final_synthesis",
                        ],
                    },
                    "description": {"type": "string"},
                },
                "required": ["step_num", "type", "description"],
            },
        }
    },
    "required": ["plan"],
}

def decompose_problem(query: str) -> dict:
    """Return a structured decomposition JSON for *query*."""

    msgs = [
        {
            "role": "system",
            "content": (
                "You are an expert problem solver. Given a complex query, break it "
                "down into atomic, numbered steps. For each step, indicate its "
                "'type' (calculation, data_lookup, final_synthesis) and a "
                "'description'. Output ONLY a JSON object with the key 'plan'. "
                "Each step must have 'step_num', 'type', and 'description' fields."
            ),
        },
        {
            "role": "user",
            "content": f"Problem: {query}\n\nOutput plan as JSON:",
        },
    ]
    resp = _call_llm(msgs, response_format={"type": "json_object"})
    try:
        result = json.loads(resp["choices"][0]["message"]["content"])
        # Validate structure
        if "plan" not in result:
            raise ValueError("LLM response missing 'plan' key")
        if not isinstance(result["plan"], list):
            raise ValueError("'plan' must be a list")
        for i, step in enumerate(result["plan"]):
            if not isinstance(step, dict):
                raise ValueError(f"Step {i} must be a dictionary")
            if "step_num" not in step:
                step["step_num"] = i + 1
            if "type" not in step:
                step["type"] = "calculation"
            if "description" not in step:
                raise ValueError(f"Step {i} missing 'description'")
        return result
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise Exception(f"Failed to parse LLM response: {str(e)}")


def generate_code_for_step(step_description: str, context: dict[str, _t.Any]) -> str:
    """Return Python code string that assigns the result to variable `result`."""

    # Extract correction information from context
    corrections = {}
    feedback_context = ""
    if "last_feedback" in context:
        feedback = context["last_feedback"]
        feedback_context = f"Previous attempt was incorrect. Feedback: {feedback}\n"
        
        if feedback.startswith("Incorrect:"):
            # Parse numerical corrections from feedback
            import re
            numbers = re.findall(r'\d+(?:\.\d+)?', feedback)
            if numbers:
                corrections["expected_value"] = float(numbers[-1])
    
    # Build enhanced context with explicit corrections
    enhanced_context = dict(context)
    if corrections:
        enhanced_context["corrections"] = corrections
    
    msgs = [
        {
            "role": "system",
            "content": (
                "You are a Python expert. Given a calculation description and its "
                "context (JSON), output ONLY the Python code needed to compute the "
                "answer. The final numeric result MUST be assigned to a variable "
                "named `result`. "
                "IMPORTANT: If the context contains 'corrections' with an 'expected_value', "
                "verify your calculation against this value and ensure you use the correct "
                "intermediate results from previous steps. Do not add explanations or comments."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{feedback_context}Calculation: {step_description}\nContext: {json.dumps(enhanced_context)}\nPython code:"
            ),
        },
    ]
    resp = _call_llm(msgs)
    return resp["choices"][0]["message"]["content"].strip()


def self_critique_output(step_description: str, output: str, original_query: str, expected_values: dict[str, _t.Any] | None = None, code_str: str | None = None) -> str:
    """Return critique string: "Correct." or feedback with specific corrections."""

    expected_context = ""
    if expected_values:
        expected_context = f"\nExpected intermediate values from context: {json.dumps(expected_values)}"
    
    code_context = ""
    if code_str:
        code_context = f"\nGenerated Code: {code_str}"

    msgs = [
        {
            "role": "system",
            "content": (
                "You are an AI auditor. Given a problem step, its output, the "
                "original query, any expected intermediate values, and the generated code, judge correctness. "
                "For numerical results: If the output is numerically incorrect, you MUST respond with 'Incorrect:' followed by the correct numerical value. "
                "For non-numerical results: If the logic or reasoning is flawed, respond with 'Incorrect:' followed by specific feedback. "
                "When code is provided, you can identify specific logical flaws in the implementation. "
                "Only respond 'Correct.' if the output is completely accurate. "
                "Be precise and unambiguous in your assessment."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Original Query: {original_query}\n"
                f"Step: {step_description}\n"
                f"Output: {output}"
                f"{code_context}"
                f"{expected_context}\n\n"
                f"Critique:"
            ),
        },
    ]
    resp = _call_llm(msgs)
    return resp["choices"][0]["message"]["content"].strip()


def synthesize_answer(original_query: str, final_results: dict[str, _t.Any]) -> str:
    """Return a synthesized final answer string."""

    msgs = [
        {
            "role": "system",
            "content": (
                "You are an expert communicator. Using the original query and a "
                "JSON dict of validated intermediate results, produce a clear, "
                "concise final answer."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Original Query: {original_query}\nFinal Results: {json.dumps(final_results)}\n\nFinal Answer:"  # noqa: E501
            ),
        },
    ]
    resp = _call_llm(msgs)
    return resp["choices"][0]["message"]["content"].strip()
