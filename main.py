"""Entry point for the orchestrated AI problem-solver.

Run with:
    python main.py "<your complex query>"

Requires env var OPENROUTER_API_KEY to be set (or provided in a .env file).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import CodeType
from typing import Any, Dict

from agents import (
    decompose_problem,
    generate_code_for_step,
    self_critique_output,
    synthesize_answer,
)

MAX_CRITIQUE_ATTEMPTS = 3

# ---------------------------------------------------------------------------
# Very small and strict sandbox for arithmetic-only code execution
# ---------------------------------------------------------------------------

_ALLOWED_AST_NODES: tuple[type[Any], ...] = (
    ast.Expression,
    ast.Module,
    ast.Assign,
    ast.Load,
    ast.Store,
    ast.BinOp,
    ast.UnaryOp,
    ast.Num,
    ast.Name,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Pow,
    ast.Mod,
    ast.USub,
)


def _validate_ast(node: ast.AST) -> None:
    """Raise ValueError if *node* contains disallowed operations."""
    for child in ast.walk(node):
        if not isinstance(child, _ALLOWED_AST_NODES):
            raise ValueError(f"Disallowed Python syntax: {type(child).__name__}")


def safe_exec(code_str: str, context: Dict[str, Any]) -> Any | str:
    """Execute simple arithmetic code safely.

    The code must assign its answer to variable `result`.
    Returns the value of `result` or an error string on failure.
    """
    try:
        tree = ast.parse(code_str, mode="exec")
        _validate_ast(tree)
        compiled: CodeType = compile(tree, filename="<generated>", mode="exec")
        local_scope = dict(context)  # shallow copy
        local_scope["result"] = None
        exec(compiled, {}, local_scope)
        return local_scope.get("result")
    except Exception as exc:  # pylint: disable=broad-except
        return f"EXECUTION_ERROR: {exc}"


# ---------------------------------------------------------------------------
# Orchestration logic
# ---------------------------------------------------------------------------

def solve_complex_query(query: str) -> None:  # noqa: C901
    print(f"\n=== Solving Query ===\n{query}\n====================")

    plan = decompose_problem(query)
    print("\n[Plan]\n" + json.dumps(plan["plan"], indent=2))

    intermediate_results: dict[str, Any] = {}

    for step in plan["plan"]:
        num = step["step_num"]
        s_type = step["type"]
        desc = step["description"]
        print(f"\n--- Step {num}: {desc} ({s_type}) ---")

        if s_type in {"calculation", "data_lookup"}:
            attempt = 0
            while attempt < MAX_CRITIQUE_ATTEMPTS:
                code = generate_code_for_step(desc, intermediate_results)
                print("[Generated Code]\n" + code)
                output = safe_exec(code, intermediate_results)
                print(f"[Execution Output] {output}")

                if isinstance(output, str) and output.startswith("EXECUTION_ERROR"):
                    feedback = f"Execution failed: {output}"
                    print(f"[Self-Critic] {feedback}")
                else:
                    # Extract expected values from previous correct steps
                    expected_values = {}
                    for key, value in intermediate_results.items():
                        if key.startswith("step_") and key.endswith("_result") and value != "FAILED_TO_REFINE":
                            step_key = key.replace("_result", "")
                            expected_values[step_key] = value
                    
                    feedback = self_critique_output(desc, str(output), query, expected_values)
                    print(f"[Self-Critic] {feedback}")

                if feedback.lower().startswith("correct"):
                    intermediate_results[f"step_{num}_result"] = output
                    break

                # Enhanced feedback with explicit corrections
                intermediate_results["last_feedback"] = feedback
                
                # Parse and store explicit corrections
                if feedback.startswith("Incorrect:"):
                    # Extract numerical correction if provided
                    import re
                    numbers = re.findall(r'\d+(?:\.\d+)?', feedback)
                    if numbers:
                        intermediate_results["expected_correction"] = float(numbers[-1])
                
                attempt += 1
                print("↺ Refining…")
            else:
                print("⚠️  Failed to refine after max attempts.")
                intermediate_results[f"step_{num}_result"] = "FAILED_TO_REFINE"

        elif s_type == "final_synthesis":
            # handled after loop
            continue
        else:
            print(f"Unknown step type: {s_type}")

    answer = synthesize_answer(query, intermediate_results)
    print("\n=== Final Answer ===\n" + answer + "\n====================\n")


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
    else:
        user_query = (
            "Sarah has 5 apples. She gives 2 to John. Then, she doubles her "
            "remaining apples. If she buys 3 more, how many apples does she have "
            "now? If apples cost $0.50 each, what is the total value of her apples?"
        )

    try:
        solve_complex_query(user_query)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
