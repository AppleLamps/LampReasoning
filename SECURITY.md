# Python Execution Environment Security Model

## Overview
This system uses a restricted Python execution environment (`safe_exec`) designed specifically for arithmetic calculations while maintaining security boundaries.

## Security Design Decisions

### Current Restrictions
The `safe_exec` function in `main.py` implements a strict AST-based whitelist approach:

**Allowed Operations:**
- Basic arithmetic: `+`, `-`, `*`, `/`, `//`, `%`, `**`
- Unary operations: `-` (negation)
- Variable assignment and access
- Numeric literals

**Disallowed Operations:**
- Import statements (`import`, `from ... import ...`)
- Conditional expressions (`if`, `if/else`, ternary operators)
- Function definitions and calls (except basic arithmetic)
- Class definitions
- File I/O operations
- Network operations
- Any other Python constructs beyond basic arithmetic

### Rationale for Restrictions

#### 1. Import Disallowance
**Decision**: No imports allowed
**Rationale**: Prevents access to system modules, file operations, network requests, or any potentially harmful functionality. The system handles this limitation by using iterative refinement loops instead of complex conditional logic.

#### 2. Conditional Logic Disallowance
**Decision**: No `if` statements or ternary operators
**Rationale**: While this limits expressiveness, it ensures:
- Predictable execution paths
- No branching logic that could hide malicious code
- Simpler validation and debugging

**Workaround**: The system uses iterative refinement with LLM feedback to handle conditional logic at a higher level rather than in the execution environment.

### Security Trade-offs

| Security Level | Flexibility | Use Case |
|----------------|-------------|----------|
| **Current (High)** | Low | Arithmetic-only calculations |
| **Medium** | Medium | Allow math module imports |
| **Low** | High | Full Python with sandboxing |

### Recommendations for Extension

If more flexibility is needed, consider:

1. **Math Module**: Add `ast.Call` and whitelist specific math functions
2. **Safe Builtins**: Allow a restricted set of Python built-ins
3. **Resource Limits**: Add execution time and memory limits
4. **Containerization**: Run in isolated containers for full Python support

### Example Usage Within Constraints

Instead of:
```python
# NOT ALLOWED
import math
result = math.sqrt(16) if x > 0 else 0
```

Use:
```python
# ALLOWED
result = 16 ** 0.5  # Square root via exponentiation
```

The system handles complex logic through the orchestration layer rather than the execution environment.
