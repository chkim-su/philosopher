#!/usr/bin/env python3
"""
Philosopher Plugin Test Runner

Validates plugin structure, hooks, agents, and skills.
Run with: python3 tests/test-runner.py
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


class TestResult:
    """Container for test results."""

    def __init__(self):
        self.passed: List[str] = []
        self.failed: List[Tuple[str, str]] = []
        self.warnings: List[str] = []

    def add_pass(self, name: str):
        self.passed.append(name)
        print(f"  {GREEN}[PASS]{RESET} {name}")

    def add_fail(self, name: str, reason: str):
        self.failed.append((name, reason))
        print(f"  {RED}[FAIL]{RESET} {name}: {reason}")

    def add_warning(self, msg: str):
        self.warnings.append(msg)
        print(f"  {YELLOW}[WARN]{RESET} {msg}")

    def summary(self) -> bool:
        """Print summary and return True if all tests passed."""
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*60}")
        print(f"Test Results: {len(self.passed)}/{total} passed")

        if self.warnings:
            print(f"Warnings: {len(self.warnings)}")

        if self.failed:
            print(f"\n{RED}Failed Tests:{RESET}")
            for name, reason in self.failed:
                print(f"  - {name}: {reason}")
            return False

        print(f"\n{GREEN}All tests passed!{RESET}")
        return True


def get_plugin_root() -> Path:
    """Get the plugin root directory."""
    # Assuming test-runner.py is in tests/
    return Path(__file__).parent.parent


def test_plugin_structure(result: TestResult):
    """Test basic plugin structure."""
    print("\n[Structure Tests]")
    root = get_plugin_root()

    # Required files
    required_files = [
        ("plugin.json", "Main plugin configuration"),
        ("README.md", "Plugin documentation"),
        (".claude-plugin/marketplace.json", "Marketplace configuration"),
    ]

    for file_path, desc in required_files:
        if (root / file_path).exists():
            result.add_pass(f"{desc} exists")
        else:
            result.add_fail(f"{desc} exists", f"Missing {file_path}")

    # Required directories
    required_dirs = [
        ("agents", "Agents directory"),
        ("skills", "Skills directory"),
        ("hooks", "Hooks directory"),
    ]

    for dir_path, desc in required_dirs:
        if (root / dir_path).is_dir():
            result.add_pass(f"{desc} exists")
        else:
            result.add_fail(f"{desc} exists", f"Missing {dir_path}/")


def test_plugin_json(result: TestResult):
    """Test plugin.json validity."""
    print("\n[plugin.json Tests]")
    root = get_plugin_root()
    plugin_path = root / "plugin.json"

    try:
        with open(plugin_path) as f:
            plugin = json.load(f)
        result.add_pass("plugin.json is valid JSON")
    except json.JSONDecodeError as e:
        result.add_fail("plugin.json is valid JSON", str(e))
        return
    except FileNotFoundError:
        result.add_fail("plugin.json exists", "File not found")
        return

    # Required fields
    required_fields = ["name", "version", "description"]
    for field in required_fields:
        if field in plugin:
            result.add_pass(f"plugin.json has '{field}' field")
        else:
            result.add_fail(f"plugin.json has '{field}' field", "Missing field")

    # Check agents array
    if "agents" in plugin:
        result.add_pass("plugin.json has 'agents' array")
        for agent in plugin["agents"]:
            if isinstance(agent, dict):
                if "name" in agent and "path" in agent:
                    # Check agent file exists
                    agent_path = root / agent["path"]
                    if agent_path.exists():
                        result.add_pass(f"Agent '{agent['name']}' file exists")
                    else:
                        result.add_fail(f"Agent '{agent['name']}' file exists", f"Missing {agent['path']}")

    # Check skills array
    if "skills" in plugin:
        result.add_pass("plugin.json has 'skills' array")
        for skill in plugin["skills"]:
            if isinstance(skill, dict):
                if "name" in skill and "path" in skill:
                    # Check skill directory exists
                    skill_path = root / skill["path"]
                    if skill_path.is_dir():
                        result.add_pass(f"Skill '{skill['name']}' directory exists")
                        # Check SKILL.md
                        skill_md = skill_path / "SKILL.md"
                        if skill_md.exists():
                            result.add_pass(f"Skill '{skill['name']}' has SKILL.md")
                        else:
                            result.add_fail(f"Skill '{skill['name']}' has SKILL.md", "Missing SKILL.md")
                    else:
                        result.add_fail(f"Skill '{skill['name']}' directory exists", f"Missing {skill['path']}/")


def test_hooks_json(result: TestResult):
    """Test hooks.json validity."""
    print("\n[hooks.json Tests]")
    root = get_plugin_root()
    hooks_path = root / "hooks" / "hooks.json"

    if not hooks_path.exists():
        result.add_warning("No hooks.json found (optional)")
        return

    try:
        with open(hooks_path) as f:
            hooks_config = json.load(f)
        result.add_pass("hooks.json is valid JSON")
    except json.JSONDecodeError as e:
        result.add_fail("hooks.json is valid JSON", str(e))
        return

    # Check version
    if "version" in hooks_config:
        result.add_pass("hooks.json has version field")

    # Check hooks array
    hooks = hooks_config.get("hooks", [])
    if hooks:
        result.add_pass(f"hooks.json defines {len(hooks)} hook(s)")

        for i, hook in enumerate(hooks):
            # Check required fields
            if "event" not in hook:
                result.add_fail(f"Hook {i} has 'event' field", "Missing event")
            elif hook["event"] in ["PreToolUse", "PostToolUse", "Stop", "SubagentStop"]:
                result.add_pass(f"Hook {i} has valid event type")
            else:
                result.add_fail(f"Hook {i} has valid event type", f"Invalid: {hook['event']}")

            # Check hook implementation exists
            inner_hooks = hook.get("hooks", [])
            for ih in inner_hooks:
                if ih.get("type") == "command":
                    cmd = ih.get("command", "")
                    # Extract Python file from command
                    if ".py" in cmd:
                        parts = cmd.split()
                        for part in parts:
                            if part.endswith(".py"):
                                py_file = root / part
                                if py_file.exists():
                                    result.add_pass(f"Hook script '{part}' exists")
                                else:
                                    result.add_fail(f"Hook script '{part}' exists", "File not found")
                                break


def test_hook_scripts(result: TestResult):
    """Test hook Python scripts for basic validity."""
    print("\n[Hook Script Tests]")
    root = get_plugin_root()
    hooks_dir = root / "hooks"

    if not hooks_dir.exists():
        result.add_warning("No hooks directory found")
        return

    for py_file in hooks_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        # Check syntax validity
        try:
            with open(py_file) as f:
                code = f.read()
            compile(code, py_file.name, "exec")
            result.add_pass(f"Hook '{py_file.name}' has valid Python syntax")
        except SyntaxError as e:
            result.add_fail(f"Hook '{py_file.name}' has valid Python syntax", str(e))
            continue

        # Check for required patterns
        if "json.dumps" in code or "json.dump" in code:
            result.add_pass(f"Hook '{py_file.name}' outputs JSON")
        elif "print(" in code:
            result.add_pass(f"Hook '{py_file.name}' has output")
        else:
            result.add_warning(f"Hook '{py_file.name}' may not produce output")


def test_agents(result: TestResult):
    """Test agent markdown files."""
    print("\n[Agent Tests]")
    root = get_plugin_root()
    agents_dir = root / "agents"

    if not agents_dir.exists():
        result.add_fail("Agents directory exists", "Missing agents/")
        return

    for agent_file in agents_dir.glob("*.md"):
        with open(agent_file) as f:
            content = f.read()

        # Check for YAML frontmatter
        if content.startswith("---"):
            end_idx = content[3:].find("---")
            if end_idx > 0:
                result.add_pass(f"Agent '{agent_file.name}' has YAML frontmatter")

                # Parse frontmatter
                frontmatter = content[3:end_idx+3]
                if "name:" in frontmatter:
                    result.add_pass(f"Agent '{agent_file.name}' has name field")
                else:
                    result.add_fail(f"Agent '{agent_file.name}' has name field", "Missing name")
            else:
                result.add_fail(f"Agent '{agent_file.name}' has valid frontmatter", "Unclosed frontmatter")
        else:
            result.add_fail(f"Agent '{agent_file.name}' has YAML frontmatter", "No frontmatter found")


def test_skills(result: TestResult):
    """Test skill directories."""
    print("\n[Skill Tests]")
    root = get_plugin_root()
    skills_dir = root / "skills"

    if not skills_dir.exists():
        result.add_fail("Skills directory exists", "Missing skills/")
        return

    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            result.add_pass(f"Skill '{skill_dir.name}' has SKILL.md")

            with open(skill_md) as f:
                content = f.read()

            # Check content quality
            if len(content) > 100:
                result.add_pass(f"Skill '{skill_dir.name}' has substantial content")
            else:
                result.add_warning(f"Skill '{skill_dir.name}' has minimal content")
        else:
            result.add_fail(f"Skill '{skill_dir.name}' has SKILL.md", "Missing SKILL.md")


def test_marketplace_json(result: TestResult):
    """Test marketplace.json validity."""
    print("\n[marketplace.json Tests]")
    root = get_plugin_root()
    marketplace_path = root / ".claude-plugin" / "marketplace.json"

    if not marketplace_path.exists():
        result.add_fail("marketplace.json exists", "Missing .claude-plugin/marketplace.json")
        return

    try:
        with open(marketplace_path) as f:
            marketplace = json.load(f)
        result.add_pass("marketplace.json is valid JSON")
    except json.JSONDecodeError as e:
        result.add_fail("marketplace.json is valid JSON", str(e))
        return

    # Check required fields
    required_fields = ["name", "version", "description"]
    for field in required_fields:
        if field in marketplace:
            result.add_pass(f"marketplace.json has '{field}' field")
        else:
            result.add_fail(f"marketplace.json has '{field}' field", "Missing field")


def main():
    """Run all tests."""
    print("="*60)
    print("Philosopher Plugin Test Runner")
    print("="*60)

    result = TestResult()

    # Run all test suites
    test_plugin_structure(result)
    test_plugin_json(result)
    test_hooks_json(result)
    test_hook_scripts(result)
    test_agents(result)
    test_skills(result)
    test_marketplace_json(result)

    # Print summary
    success = result.summary()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
