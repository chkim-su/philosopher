#!/usr/bin/env python3
"""
Post-execution validator for multi_llm_debater.py
Validates JSON output structure and quality after debate execution.
"""

import sys
import json


# Expected fields per phase
EXPECTED_FIELDS = {
    "initial_research": ["findings", "sources", "key_points"],
    "round_claim": ["claim", "evidence", "confidence"],
    "round_claim_attack": ["claim", "evidence", "attacks", "confidence"],
    "prep_defense": ["defense_points", "counter_arguments", "additional_research"],
    "round_defense": ["defense", "counterattacks", "final_position"]
}


def validate_output():
    """Validate hook output from stdin."""
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        # Not JSON input, skip validation
        sys.exit(0)

    # Extract tool input and output
    tool_input = input_data.get("tool_input", {})
    tool_output = input_data.get("tool_output", {})

    command = tool_input.get("command", "")
    stdout = tool_output.get("stdout", "")

    # Only validate multi_llm_debater.py calls
    if "multi_llm_debater.py" not in command:
        sys.exit(0)

    # Skip validation commands
    if "--validate-deps" in command or "--validate-api-key" in command:
        sys.exit(0)

    warnings = []

    # Try to extract JSON from output
    json_result = None
    try:
        # Try direct parse
        json_result = json.loads(stdout.strip())
    except json.JSONDecodeError:
        # Try to find JSON in output
        import re
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'(\{[\s\S]*\})'
        ]
        for pattern in json_patterns:
            match = re.search(pattern, stdout)
            if match:
                try:
                    json_result = json.loads(match.group(1))
                    break
                except json.JSONDecodeError:
                    continue

    if json_result is None:
        warnings.append("Output does not contain valid JSON - may need manual review")
    else:
        # Check for expected fields based on phase
        for phase, expected in EXPECTED_FIELDS.items():
            if phase in command:
                missing_fields = [f for f in expected if f not in json_result]
                if missing_fields:
                    warnings.append(f"Missing expected fields for {phase}: {', '.join(missing_fields)}")
                break

        # Check for error indicators
        if json_result.get("error") or json_result.get("status") == "error":
            warnings.append(f"Debate execution reported an error: {json_result.get('error', 'Unknown')}")

        # Check confidence level if present
        confidence = json_result.get("confidence")
        if confidence is not None and isinstance(confidence, (int, float)):
            if confidence < 0.3:
                warnings.append(f"Low confidence score ({confidence}) - results may be unreliable")

    # Output result (PostToolUse hooks don't block, just report)
    result = {
        "decision": "allow",
        "reason": None
    }

    if warnings:
        # Print warnings to stderr for visibility
        print(f"Debate output warnings:\n" + "\n".join(f"  - {w}" for w in warnings), file=sys.stderr)

    print(json.dumps(result))


if __name__ == "__main__":
    validate_output()
