#!/usr/bin/env python3
"""
Pre-execution validator for multi_llm_debater.py
Validates required arguments and provider configuration before debate execution.
"""

import sys
import json
import os

# Valid phases and providers
VALID_PHASES = [
    "initial_research",
    "round_claim",
    "round_claim_attack",
    "prep_defense",
    "round_defense"
]

VALID_PROVIDERS = ["claude", "gpt", "codex", "gemini"]

VALID_ROLES = ["A", "B", "C"]


def validate_input():
    """Validate hook input from stdin."""
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        # Not JSON input, skip validation
        sys.exit(0)

    # Extract command from tool input
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only validate multi_llm_debater.py calls
    if "multi_llm_debater.py" not in command:
        sys.exit(0)

    errors = []
    warnings = []

    # Check for required arguments
    if "--provider" not in command:
        errors.append("Missing required argument: --provider")
    else:
        # Validate provider value
        for provider in VALID_PROVIDERS:
            if f"--provider {provider}" in command or f"--provider={provider}" in command:
                break
        else:
            # Check if any valid provider is mentioned
            provider_found = False
            for provider in VALID_PROVIDERS:
                if provider in command:
                    provider_found = True
                    break
            if not provider_found:
                errors.append(f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}")

    if "--phase" not in command:
        errors.append("Missing required argument: --phase")
    else:
        # Validate phase value
        phase_valid = False
        for phase in VALID_PHASES:
            if phase in command:
                phase_valid = True
                break
        if not phase_valid:
            errors.append(f"Invalid phase. Must be one of: {', '.join(VALID_PHASES)}")

    if "--topic" not in command:
        errors.append("Missing required argument: --topic")

    if "--role" not in command:
        warnings.append("Consider specifying --role (A, B, or C) for context isolation")

    # Check for validation-only commands (these are always valid)
    if "--validate-deps" in command or "--validate-api-key" in command:
        sys.exit(0)

    # Output result
    result = {
        "decision": "block" if errors else "allow",
        "reason": None
    }

    if errors:
        result["reason"] = "Debate script validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
    elif warnings:
        # Allow but with informational message (printed to stderr)
        print(f"Warnings: {'; '.join(warnings)}", file=sys.stderr)

    print(json.dumps(result))


if __name__ == "__main__":
    validate_input()
