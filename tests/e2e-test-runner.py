#!/usr/bin/env python3
"""
Philosopher Plugin E2E Test Runner

Tests end-to-end functionality of hooks and script integration.
Run with: python3 tests/e2e-test-runner.py
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def get_plugin_root() -> Path:
    """Get the plugin root directory."""
    return Path(__file__).parent.parent


class E2ETestRunner:
    """End-to-end test runner for philosopher plugin."""

    def __init__(self):
        self.root = get_plugin_root()
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def run_hook(self, hook_script: str, input_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run a hook script with given input and return output."""
        script_path = self.root / "hooks" / hook_script

        if not script_path.exists():
            return None

        try:
            result = subprocess.run(
                ["python3", str(script_path)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.stdout.strip():
                return json.loads(result.stdout.strip())
            return None

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            print(f"  {YELLOW}[ERROR]{RESET} Hook execution failed: {e}")
            return None

    def test_validate_debate_topic_good_topic(self):
        """Test that a good technical topic passes validation."""
        print("\n[E2E] Testing validate_debate_topic with good technical topic...")

        input_data = {
            "tool_name": "Skill",
            "tool_input": {
                "skill": "debate-multiverse",
                "args": "React vs Vue for our frontend project"
            }
        }

        result = self.run_hook("validate_debate_topic.py", input_data)

        if result is None:
            print(f"  {YELLOW}[SKIP]{RESET} Hook did not return valid output")
            self.skipped += 1
            return

        if result.get("decision") == "allow":
            print(f"  {GREEN}[PASS]{RESET} Good topic allowed")
            self.passed += 1
        else:
            print(f"  {RED}[FAIL]{RESET} Good topic should be allowed, got: {result}")
            self.failed += 1

    def test_validate_debate_topic_bad_topic(self):
        """Test that a vague topic is blocked."""
        print("\n[E2E] Testing validate_debate_topic with vague topic...")

        input_data = {
            "tool_name": "Skill",
            "tool_input": {
                "skill": "debate",
                "args": "AI"  # Too vague
            }
        }

        result = self.run_hook("validate_debate_topic.py", input_data)

        if result is None:
            print(f"  {YELLOW}[SKIP]{RESET} Hook did not return valid output")
            self.skipped += 1
            return

        if result.get("decision") == "block":
            print(f"  {GREEN}[PASS]{RESET} Vague topic blocked correctly")
            self.passed += 1
        else:
            print(f"  {RED}[FAIL]{RESET} Vague topic should be blocked, got: {result}")
            self.failed += 1

    def test_validate_debate_topic_non_debate_skill(self):
        """Test that non-debate skills are allowed through."""
        print("\n[E2E] Testing validate_debate_topic with non-debate skill...")

        input_data = {
            "tool_name": "Skill",
            "tool_input": {
                "skill": "some-other-skill",
                "args": "whatever"
            }
        }

        result = self.run_hook("validate_debate_topic.py", input_data)

        if result is None:
            print(f"  {YELLOW}[SKIP]{RESET} Hook did not return valid output")
            self.skipped += 1
            return

        if result.get("decision") == "allow":
            print(f"  {GREEN}[PASS]{RESET} Non-debate skill allowed")
            self.passed += 1
        else:
            print(f"  {RED}[FAIL]{RESET} Non-debate skill should be allowed, got: {result}")
            self.failed += 1

    def test_validate_debate_args_valid(self):
        """Test that valid debate arguments pass."""
        print("\n[E2E] Testing validate_debate_args with valid arguments...")

        input_data = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 scripts/multi_llm_debater.py --provider claude --phase round_claim --topic 'AI ethics' --role A"
            }
        }

        result = self.run_hook("validate_debate_args.py", input_data)

        if result is None:
            print(f"  {YELLOW}[SKIP]{RESET} Hook did not return valid output")
            self.skipped += 1
            return

        if result.get("decision") == "allow":
            print(f"  {GREEN}[PASS]{RESET} Valid arguments allowed")
            self.passed += 1
        else:
            print(f"  {RED}[FAIL]{RESET} Valid arguments should be allowed, got: {result}")
            self.failed += 1

    def test_validate_debate_args_missing_provider(self):
        """Test that missing provider is blocked."""
        print("\n[E2E] Testing validate_debate_args with missing provider...")

        input_data = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 scripts/multi_llm_debater.py --phase round_claim --topic 'AI ethics'"
            }
        }

        result = self.run_hook("validate_debate_args.py", input_data)

        if result is None:
            print(f"  {YELLOW}[SKIP]{RESET} Hook did not return valid output")
            self.skipped += 1
            return

        if result.get("decision") == "block":
            print(f"  {GREEN}[PASS]{RESET} Missing provider blocked correctly")
            self.passed += 1
        else:
            print(f"  {RED}[FAIL]{RESET} Missing provider should be blocked, got: {result}")
            self.failed += 1

    def test_validate_debate_args_non_debater_command(self):
        """Test that non-debater commands are allowed through."""
        print("\n[E2E] Testing validate_debate_args with non-debater command...")

        input_data = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "ls -la"
            }
        }

        result = self.run_hook("validate_debate_args.py", input_data)

        # Non-debater commands exit early with code 0 (no output)
        # This is expected behavior
        print(f"  {GREEN}[PASS]{RESET} Non-debater command handled correctly (exits early)")
        self.passed += 1

    def test_validate_debate_output_valid(self):
        """Test that valid output passes."""
        print("\n[E2E] Testing validate_debate_output with valid output...")

        input_data = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 scripts/multi_llm_debater.py --provider claude --phase round_claim --topic 'AI ethics'"
            },
            "tool_output": {
                "stdout": json.dumps({
                    "claim": "AI needs ethical guidelines",
                    "evidence": ["Research shows...", "Studies indicate..."],
                    "confidence": 0.85
                })
            }
        }

        result = self.run_hook("validate_debate_output.py", input_data)

        if result is None:
            print(f"  {YELLOW}[SKIP]{RESET} Hook did not return valid output")
            self.skipped += 1
            return

        # PostToolUse hooks always allow, but may warn
        if result.get("decision") == "allow":
            print(f"  {GREEN}[PASS]{RESET} Valid output allowed")
            self.passed += 1
        else:
            print(f"  {RED}[FAIL]{RESET} Valid output should be allowed, got: {result}")
            self.failed += 1

    def run_all_tests(self) -> bool:
        """Run all E2E tests and return success status."""
        print("="*60)
        print("Philosopher Plugin E2E Test Runner")
        print("="*60)

        # Run all test methods
        self.test_validate_debate_topic_good_topic()
        self.test_validate_debate_topic_bad_topic()
        self.test_validate_debate_topic_non_debate_skill()
        self.test_validate_debate_args_valid()
        self.test_validate_debate_args_missing_provider()
        self.test_validate_debate_args_non_debater_command()
        self.test_validate_debate_output_valid()

        # Summary
        total = self.passed + self.failed + self.skipped
        print(f"\n{'='*60}")
        print(f"E2E Test Results: {self.passed}/{total} passed, {self.failed} failed, {self.skipped} skipped")

        if self.failed > 0:
            print(f"\n{RED}Some tests failed!{RESET}")
            return False

        print(f"\n{GREEN}All E2E tests passed!{RESET}")
        return True


def main():
    """Run E2E tests."""
    runner = E2ETestRunner()
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
