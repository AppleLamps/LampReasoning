"""Flask web UI for the orchestrated AI problem-solver."""
from __future__ import annotations

import json
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from typing import Generator, Any

from main import solve_complex_query
from agents import (
    decompose_problem,
    generate_code_for_step,
    self_critique_output,
    synthesize_answer,
)
from main import safe_exec, MAX_CRITIQUE_ATTEMPTS

app = Flask(__name__)

@app.route('/')
def index():
    """Main page with query input form."""
    return render_template('index.html')

@app.route('/solve', methods=['POST'])
def solve():
    """Process query and return step-by-step results."""
    data = request.get_json()
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'error': 'Query cannot be empty'}), 400
    
    try:
        # Generate the solution step by step
        result = solve_query_with_steps(query)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def solve_query_with_steps(query: str) -> dict[str, Any]:
    """Solve query and return structured results for UI."""
    
    # Step 1: Decompose problem
    try:
        plan = decompose_problem(query)
    except Exception as e:
        raise Exception(f"Failed to decompose problem: {str(e)}")
    
    steps_data = []
    intermediate_results: dict[str, Any] = {}
    
    # Process each step
    if "plan" not in plan:
        raise Exception("Invalid plan structure: missing 'plan' key")
    
    for i, step in enumerate(plan["plan"]):
        # Handle case where step_num might not be present
        step_num = step.get("step_num", i + 1)
        step_type = step.get("type", "unknown")
        step_desc = step.get("description", "No description")
        
        step_data = {
            'step_num': step_num,
            'type': step_type,
            'description': step_desc,
            'attempts': []
        }
        
        if step_type in {"calculation", "data_lookup"}:
            attempt = 0
            while attempt < MAX_CRITIQUE_ATTEMPTS:
                # Generate code
                code = generate_code_for_step(step_desc, intermediate_results)
                
                # Execute code
                output = safe_exec(code, intermediate_results)
                
                # Get critique with enhanced context
                expected_values = {}
                for key, value in intermediate_results.items():
                    if key.startswith("step_") and key.endswith("_result") and value != "FAILED_TO_REFINE":
                        step_key = key.replace("_result", "")
                        expected_values[step_key] = value
                
                if isinstance(output, str) and output.startswith("EXECUTION_ERROR"):
                    feedback = f"Execution failed: {output}"
                else:
                    feedback = self_critique_output(step_desc, str(output), query, expected_values)
                
                attempt_data = {
                    'attempt': attempt + 1,
                    'code': code,
                    'output': output,
                    'feedback': feedback,
                    'success': feedback.lower().startswith("correct")
                }
                step_data['attempts'].append(attempt_data)
                
                if attempt_data['success']:
                    intermediate_results[f"step_{step_num}_result"] = output
                    break
                
                # Enhanced feedback with explicit corrections
                intermediate_results["last_feedback"] = feedback
                
                # Parse and store explicit corrections
                if feedback.startswith("Incorrect:"):
                    import re
                    numbers = re.findall(r'\d+(?:\.\d+)?', feedback)
                    if numbers:
                        intermediate_results["expected_correction"] = float(numbers[-1])
                
                attempt += 1
            else:
                intermediate_results[f"step_{step_num}_result"] = "FAILED_TO_REFINE"
                
        steps_data.append(step_data)
    
    # Generate final answer
    final_answer = synthesize_answer(query, intermediate_results)
    
    return {
        'query': query,
        'plan': plan["plan"],
        'steps': steps_data,
        'final_answer': final_answer,
        'intermediate_results': intermediate_results
    }

# ---------- Streaming generator and endpoint ----------
def solve_query_stream(query: str) -> Generator[str, None, None]:
    """Stream solution steps as Server-Sent Events (SSE)."""
    try:
        plan = decompose_problem(query)
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'data': f'Failed to decompose problem: {str(e)}'})}\\n\\n"
        yield "data: [DONE]\\n\\n"
        return

    # Send decomposition
    yield f"data: {json.dumps({'type': 'plan', 'data': plan.get('plan', [])})}\\n\\n"

    intermediate_results: dict[str, Any] = {}
    if 'plan' not in plan:
        yield f"data: {json.dumps({'type': 'error', 'data': 'Invalid plan structure'})}\\n\\n"
        yield "data: [DONE]\\n\\n"
        return

    for i, step in enumerate(plan['plan']):
        step_num = step.get('step_num', i + 1)
        step_type = step.get('type', 'unknown')
        step_desc = step.get('description', 'No description')

        attempt = 0
        while attempt < MAX_CRITIQUE_ATTEMPTS:
            code = generate_code_for_step(step_desc, intermediate_results)
            output = safe_exec(code, intermediate_results)

            expected_values = {
                key.replace('_result', ''): value
                for key, value in intermediate_results.items()
                if key.startswith('step_') and key.endswith('_result') and value != 'FAILED_TO_REFINE'
            }

            if isinstance(output, str) and output.startswith('EXECUTION_ERROR'):
                feedback = f"Execution failed: {output}"
            else:
                feedback = self_critique_output(step_desc, str(output), query, expected_values)

            attempt_data = {
                'step_num': step_num,
                'type': step_type,
                'description': step_desc,
                'attempt': attempt + 1,
                'code': code,
                'output': output,
                'feedback': feedback,
                'success': feedback.lower().startswith('correct'),
            }

            yield f"data: {json.dumps({'type': 'attempt', 'data': attempt_data})}\\n\\n"

            if attempt_data['success']:
                intermediate_results[f'step_{step_num}_result'] = output
                break

            intermediate_results['last_feedback'] = feedback
            if feedback.startswith('Incorrect:'):
                import re
                numbers = re.findall(r'\\d+(?:\\.\\d+)?', feedback)
                if numbers:
                    intermediate_results['expected_correction'] = float(numbers[-1])

            attempt += 1
        else:
            intermediate_results[f'step_{step_num}_result'] = 'FAILED_TO_REFINE'

    final_answer = synthesize_answer(query, intermediate_results)
    yield f"data: {json.dumps({'type': 'final_answer', 'data': final_answer})}\\n\\n"
    yield "data: [DONE]\\n\\n"


@app.route('/solve_stream', methods=['POST'])
def solve_stream():
    """Stream the solving process to the client as SSE."""
    data = request.get_json()
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'Query cannot be empty'}), 400

    return Response(stream_with_context(solve_query_stream(query)), mimetype='text/event-stream')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
