#!/usr/bin/env python3
"""
Multi-LLM Debater Script v3

Complete debate system with proper context isolation, phased execution,
and production-grade robustness features.

v3 Improvements:
- Timeout handling with asyncio.wait_for
- Retry logic with exponential backoff
- Dependency validation
- Robust JSON parsing with recovery
- API key validation
- Structured logging

Phases:
1. initial_research - Pre-debate independent research (WebSearch enabled)
2. round_claim - First speaker makes claim
3. round_claim_attack - 2nd/3rd speakers make claim + attack
4. prep_defense - Between-round preparation with additional research
5. round_defense - Defense + counterattack

Usage:
    # Phase 0: Initial research (parallel for all debaters)
    python multi_llm_debater.py --provider claude --role A --phase initial_research \
        --topic "AI regulation"

    # Round 1: First claim
    python multi_llm_debater.py --provider gemini --role A --phase round_claim \
        --topic "AI regulation" --own-research '{...}'

    # Round 1: Claim + Attack
    python multi_llm_debater.py --provider codex --role B --phase round_claim_attack \
        --topic "AI regulation" --own-research '{...}' --visible-statements '{...}'

    # Validation commands
    python multi_llm_debater.py --validate-deps
    python multi_llm_debater.py --validate-api-key claude
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable

# =============================================================================
# DEPENDENCY VALIDATION
# =============================================================================

def validate_dependencies() -> Dict[str, Any]:
    """Validate all required dependencies are installed and configured."""
    errors = []
    warnings = []

    # Check u-llm-sdk
    try:
        from u_llm_sdk import LLM, LLMConfig
        from llm_types import Provider, ModelTier, AutoApproval, ReasoningLevel
    except ImportError as e:
        errors.append({
            "type": "missing_dependency",
            "package": "u-llm-sdk",
            "fix": "pip install u-llm-sdk",
            "detail": str(e)
        })

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }


def validate_api_keys(provider: str) -> Dict[str, Any]:
    """Validate API keys for the specified provider."""
    env_vars = {
        "claude": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "gpt": ["OPENAI_API_KEY", "CODEX_API_KEY"],
        "codex": ["OPENAI_API_KEY", "CODEX_API_KEY"],
        "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    }

    required_vars = env_vars.get(provider, [])
    found = False
    checked_vars = []

    for var in required_vars:
        checked_vars.append(var)
        if os.environ.get(var):
            found = True
            break

    return {
        "valid": found,
        "provider": provider,
        "checked_vars": checked_vars,
        "error": None if found else f"No API key found for {provider}. Set one of: {', '.join(required_vars)}"
    }


# Validate dependencies at import time
_dep_check = validate_dependencies()
if not _dep_check["valid"]:
    print(json.dumps({
        "success": False,
        "error": "Dependency validation failed",
        "details": _dep_check["errors"]
    }))
    sys.exit(1)

# Now safe to import
from u_llm_sdk import LLM, LLMConfig
from llm_types import Provider, ModelTier, AutoApproval, ReasoningLevel


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0


@dataclass
class TimeoutConfig:
    """Timeout configuration per phase."""
    initial_research: float = 180.0  # WebSearch included
    round_claim: float = 90.0
    round_claim_attack: float = 90.0
    prep_defense: float = 180.0  # WebSearch included
    round_defense: float = 90.0

    def get(self, phase: str) -> float:
        return getattr(self, phase, 90.0)


PROVIDER_MAP = {
    "claude": Provider.CLAUDE,
    "gpt": Provider.CODEX,
    "codex": Provider.CODEX,
    "gemini": Provider.GEMINI,
}

RETRY_CONFIG = RetryConfig()
TIMEOUT_CONFIG = TimeoutConfig()


# =============================================================================
# FALLBACK CONFIGURATION
# =============================================================================

@dataclass
class FallbackConfig:
    """Configuration for automatic provider fallback."""
    enabled: bool = True
    fallback_provider: str = "claude"
    health_check_timeout: float = 15.0


@dataclass
class ProviderStatus:
    """Result of provider availability check."""
    provider: str
    available: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    error_type: Optional[str] = None


@dataclass
class FallbackEvent:
    """Record of a fallback occurrence."""
    phase: str
    original_provider: str
    fallback_provider: str
    error_type: str
    error_message: str
    timestamp: str
    recovery_time_ms: Optional[float] = None


FALLBACK_CONFIG = FallbackConfig()


# =============================================================================
# ERROR CLASSIFICATION
# =============================================================================

FALLBACK_ERROR_PATTERNS = {
    "rate_limit": ["rate limit", "429", "too many requests", "rate-limit"],
    "quota": ["quota exceeded", "quota", "billing", "insufficient credits"],
    "timeout": ["timeout", "timed out", "deadline exceeded"],
    "service_unavailable": ["503", "service unavailable", "temporarily unavailable"],
    "overloaded": ["overloaded", "capacity", "busy", "try again later"],
}

HARD_FAILURE_PATTERNS = {
    "auth": ["401", "403", "api key", "authentication", "unauthorized", "invalid key"],
    "invalid_input": ["invalid", "malformed", "bad request", "400"],
    "content_policy": ["content policy", "safety", "blocked", "harmful", "refused"],
}


def classify_error(error_message: str) -> str:
    """Classify error message into error type for fallback decision."""
    error_lower = error_message.lower()

    # Check fallback-triggering patterns first
    for error_type, patterns in FALLBACK_ERROR_PATTERNS.items():
        if any(p in error_lower for p in patterns):
            return error_type

    # Check hard failure patterns
    for error_type, patterns in HARD_FAILURE_PATTERNS.items():
        if any(p in error_lower for p in patterns):
            return error_type

    return "unknown"


def should_fallback(result: dict) -> bool:
    """Determine if error should trigger fallback to alternative provider."""
    if result.get("success"):
        return False

    error = result.get("error", "") or ""
    error_type = result.get("error_type", "")

    # Timeout always triggers fallback
    if error_type == "timeout":
        return True

    # Classify and check
    classified = classify_error(error)
    return classified in FALLBACK_ERROR_PATTERNS


# =============================================================================
# PROVIDER HEALTH CHECK
# =============================================================================

AVAILABILITY_TEST_PROMPT = "Reply with only the word 'OK'."


async def test_provider_availability(
    provider_name: str,
    timeout: float = 15.0
) -> ProviderStatus:
    """Test if a provider is available and responsive.

    Only tests gemini and codex - Claude is assumed always available.

    Args:
        provider_name: Provider to test ("gemini" or "codex")
        timeout: Maximum time to wait for response

    Returns:
        ProviderStatus with availability information
    """
    # Claude is assumed always available
    if provider_name == "claude":
        return ProviderStatus(provider="claude", available=True)

    provider = PROVIDER_MAP.get(provider_name)
    if not provider:
        return ProviderStatus(
            provider=provider_name,
            available=False,
            error=f"Unknown provider: {provider_name}",
            error_type="invalid_provider"
        )

    # Check API key first
    api_check = validate_api_keys(provider_name)
    if not api_check["valid"]:
        return ProviderStatus(
            provider=provider_name,
            available=False,
            error=api_check["error"],
            error_type="auth"
        )

    start_time = time.time()

    try:
        config = LLMConfig(
            provider=provider,
            tier=ModelTier.LOW,  # Use cheap tier for health check
            timeout=timeout,
        )

        async with LLM(config) as llm:
            result = await llm.run(AVAILABILITY_TEST_PROMPT)

        latency_ms = (time.time() - start_time) * 1000

        if result.success:
            return ProviderStatus(
                provider=provider_name,
                available=True,
                latency_ms=latency_ms
            )
        else:
            error_type = classify_error(result.error or "")
            return ProviderStatus(
                provider=provider_name,
                available=False,
                error=result.error,
                error_type=error_type,
                latency_ms=latency_ms
            )

    except asyncio.TimeoutError:
        return ProviderStatus(
            provider=provider_name,
            available=False,
            error=f"Health check timed out after {timeout}s",
            error_type="timeout"
        )
    except Exception as e:
        return ProviderStatus(
            provider=provider_name,
            available=False,
            error=str(e),
            error_type=classify_error(str(e))
        )


async def run_pre_debate_health_checks(
    requested_providers: List[str]
) -> Dict[str, ProviderStatus]:
    """Run health checks for all non-Claude providers before debate.

    Args:
        requested_providers: List of provider names to check

    Returns:
        Dict mapping provider name to ProviderStatus
    """
    health_results = {}

    # Filter to only check gemini and codex (Claude assumed available)
    providers_to_check = [p for p in requested_providers if p in ["gemini", "codex"]]

    # Run checks in parallel
    if providers_to_check:
        tasks = [test_provider_availability(p) for p in providers_to_check]
        results = await asyncio.gather(*tasks)
        for status in results:
            health_results[status.provider] = status

    return health_results


# =============================================================================
# ROBUST JSON PARSING
# =============================================================================

def fix_trailing_commas(text: str) -> str:
    """Remove trailing commas before closing brackets/braces."""
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    return text


def fix_unquoted_keys(text: str) -> str:
    """Attempt to fix unquoted keys in JSON-like text."""
    pattern = r'(?<=[{,\s])(\w+)(?=\s*:)'
    return re.sub(pattern, r'"\1"', text)


def extract_json_block(text: str) -> str:
    """Extract JSON from markdown code blocks or find JSON object."""
    # Try markdown code block first
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()

    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()

    # Try to find JSON object boundaries
    brace_start = text.find('{')
    if brace_start >= 0:
        depth = 0
        for i, char in enumerate(text[brace_start:], brace_start):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    return text[brace_start:i+1]

    return text


def robust_json_parse(text: str) -> Dict[str, Any]:
    """
    Try multiple parsing strategies before giving up.

    Returns parsed JSON or a structured error response.
    """
    strategies: List[tuple] = [
        ("direct", lambda t: t),
        ("extract_block", extract_json_block),
        ("fix_commas", lambda t: fix_trailing_commas(extract_json_block(t))),
        ("fix_keys", lambda t: fix_unquoted_keys(fix_trailing_commas(extract_json_block(t)))),
    ]

    last_error = None
    for strategy_name, transform in strategies:
        try:
            transformed = transform(text)
            parsed = json.loads(transformed)
            return {
                "parsed": True,
                "data": parsed,
                "strategy_used": strategy_name
            }
        except json.JSONDecodeError as e:
            last_error = str(e)
            continue

    # All strategies failed
    return {
        "parsed": False,
        "raw_response": text,
        "parse_error": last_error,
        "strategies_tried": [s[0] for s in strategies]
    }


# =============================================================================
# RETRY LOGIC WITH EXPONENTIAL BACKOFF
# =============================================================================

class RetryableError(Exception):
    """Exception that should trigger a retry."""
    pass


class NonRetryableError(Exception):
    """Exception that should not be retried."""
    pass


async def with_retry(
    func: Callable,
    config: RetryConfig = RETRY_CONFIG,
    on_retry: Optional[Callable[[int, Exception], None]] = None
) -> Any:
    """
    Execute an async function with exponential backoff retry.

    Args:
        func: Async function to execute
        config: Retry configuration
        on_retry: Optional callback for retry events

    Returns:
        Result from successful function execution

    Raises:
        Last exception if all retries exhausted
    """
    last_exception = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func()
        except NonRetryableError:
            raise
        except Exception as e:
            last_exception = e

            if attempt == config.max_attempts:
                break

            # Calculate delay with exponential backoff
            delay = min(
                config.base_delay * (config.exponential_base ** (attempt - 1)),
                config.max_delay
            )

            if on_retry:
                on_retry(attempt, e)

            await asyncio.sleep(delay)

    raise last_exception


# =============================================================================
# PHASE PROMPTS - Each phase has specific context and output requirements
# =============================================================================

PHASE_PROMPTS = {
    "initial_research": """You are preparing for a debate on the following topic.

TOPIC: {topic}

YOUR ASSIGNED VIEWPOINT: {viewpoint}

INSTRUCTIONS:
1. Research this topic thoroughly from your assigned viewpoint
2. Gather evidence, statistics, expert opinions, and logical arguments
3. Identify potential weaknesses in your position (for self-awareness)
4. Note potential attack vectors against opposing viewpoints

You may use web search to find current data and authoritative sources.

OUTPUT FORMAT (JSON):
{{
    "viewpoint": "{viewpoint}",
    "core_thesis": "Your main argument in one clear sentence",
    "key_arguments": [
        {{
            "point": "Argument point",
            "evidence": "Supporting evidence or logic",
            "source": "Source (URL, study name, or 'logical reasoning')"
        }}
    ],
    "potential_counterarguments": [
        "Counterargument you anticipate"
    ],
    "attack_vectors": [
        {{
            "target_viewpoint": "Opposing view to attack",
            "weakness": "Their potential weakness",
            "attack_strategy": "How to exploit it"
        }}
    ]
}}

Be thorough. This research will be your foundation for the entire debate.""",

    "round_claim": """You are Debater {role} in a structured debate.

TOPIC: {topic}
YOUR VIEWPOINT: {viewpoint}
ROUND: {round} (You speak FIRST this round)

YOUR PRIVATE RESEARCH:
{own_research}

INSTRUCTIONS:
As the first speaker of Round {round}, you must:
1. Present your position clearly and persuasively
2. Support your claims with evidence from your research
3. Establish the strongest possible foundation for your viewpoint

NOTE: Since you speak first, you cannot attack anyone yet. Focus on building your case.

OUTPUT FORMAT (JSON):
{{
    "round": {round},
    "speaker": "{role}",
    "type": "claim",
    "statement": {{
        "position": "Your clear position statement",
        "main_argument": "Your primary argument",
        "supporting_points": [
            {{
                "point": "Supporting point",
                "evidence": "Evidence",
                "source": "Source"
            }}
        ],
        "challenge_to_opponents": "What you challenge others to address"
    }},
    "confidence_level": 0.0-1.0
}}""",

    "round_claim_attack": """You are Debater {role} in a structured debate.

TOPIC: {topic}
YOUR VIEWPOINT: {viewpoint}
ROUND: {round}
SPEAKING ORDER: You are speaker #{speaker_order} this round

YOUR PRIVATE RESEARCH:
{own_research}

STATEMENTS MADE SO FAR THIS ROUND:
{visible_statements}

INSTRUCTIONS:
1. Present your position clearly
2. ATTACK the previous speakers' arguments:
   - Identify logical flaws, weak evidence, or unsupported claims
   - Challenge their credibility where appropriate
   - Point out what they failed to address or test
3. Use your research to strengthen your attacks

Attack types you can use:
- "logical_flaw": Point out reasoning errors
- "weak_evidence": Challenge the quality of their sources
- "untested_claim": They made claims without verification
- "missing_consideration": They ignored important factors
- "counterexample": Provide examples that contradict their claims

OUTPUT FORMAT (JSON):
{{
    "round": {round},
    "speaker": "{role}",
    "type": "claim_attack",
    "statement": {{
        "position": "Your clear position statement",
        "main_argument": "Your primary argument",
        "supporting_points": [...]
    }},
    "attacks": [
        {{
            "target": "A or B",
            "target_claim": "What they said that you're attacking",
            "attack_type": "logical_flaw|weak_evidence|untested_claim|missing_consideration|counterexample",
            "attack_content": "Your detailed attack",
            "your_counter_evidence": "Evidence supporting your attack"
        }}
    ],
    "confidence_level": 0.0-1.0
}}""",

    "prep_defense": """You are Debater {role} preparing for the next round.

TOPIC: {topic}
YOUR VIEWPOINT: {viewpoint}
PREPARING FOR: Round {next_round}

YOUR ORIGINAL RESEARCH:
{own_research}

COMPLETE DEBATE HISTORY:
{debate_history}

ATTACKS YOU RECEIVED:
{attacks_received}

INSTRUCTIONS:
1. Analyze each attack against you carefully
2. For attacks that have merit, conduct ADDITIONAL RESEARCH (WebSearch) to:
   - Find verified data to counter their claims
   - Locate official documents or authoritative sources
   - Gather new evidence they haven't considered
3. Prepare strong defenses for each attack
4. Plan counterattacks for your next turn

You MUST use web search if:
- Your original evidence was challenged as weak
- You need current statistics or data
- You need authoritative sources to back your claims

OUTPUT FORMAT (JSON):
{{
    "preparing_for_round": {next_round},
    "attacks_analysis": [
        {{
            "attacker": "B or C",
            "their_attack": "What they said",
            "attack_validity": "valid|partially_valid|invalid",
            "defense_strategy": "How you'll defend"
        }}
    ],
    "additional_research": [
        {{
            "research_goal": "What you searched for",
            "findings": "What you found",
            "source": "URL or source name",
            "how_it_helps": "How this strengthens your position"
        }}
    ],
    "prepared_defenses": [
        {{
            "against_attack": "The attack you're defending",
            "defense": "Your defense",
            "counter_evidence": "New evidence if any",
            "counterattack": "Your planned counterattack"
        }}
    ],
    "updated_confidence": 0.0-1.0
}}""",

    "round_defense": """You are Debater {role} defending and counterattacking.

TOPIC: {topic}
YOUR VIEWPOINT: {viewpoint}
ROUND: {round}
{final_round_notice}

YOUR ORIGINAL RESEARCH:
{own_research}

YOUR PREPARATION (including additional research):
{own_prep}

COMPLETE DEBATE HISTORY:
{debate_history}

THIS ROUND SO FAR:
{round_statements}

ATTACKS YOU MUST ADDRESS:
{attacks_to_address}

INSTRUCTIONS:
1. DEFEND against each attack on you with evidence
2. COUNTERATTACK your opponents, especially targeting:
   - Weak defenses they've made this round
   - New weaknesses exposed by their statements
3. Use your additional research to strengthen both defense and attack
{final_round_instructions}

OUTPUT FORMAT (JSON):
{{
    "round": {round},
    "speaker": "{role}",
    "type": "defense_counterattack",
    "defenses": [
        {{
            "against": "Attacker role",
            "their_attack": "What they claimed",
            "your_defense": "Your response",
            "evidence": "Supporting evidence",
            "source": "Source"
        }}
    ],
    "counterattacks": [
        {{
            "target": "Target role",
            "attack_point": "What you're attacking",
            "attack_content": "Your attack",
            "evidence": "Supporting evidence"
        }}
    ],
    "updated_position": "Your refined position after this exchange",
    {consensus_field}
    "confidence_level": 0.0-1.0
}}"""
}


def build_prompt(phase: str, **kwargs) -> str:
    """Build the appropriate prompt for the given phase."""
    template = PHASE_PROMPTS.get(phase)
    if not template:
        raise ValueError(f"Unknown phase: {phase}")

    # Handle final round special fields
    if phase == "round_defense":
        is_final = kwargs.get("is_final", False)
        kwargs["final_round_notice"] = (
            "\n⚠️ THIS IS THE FINAL ROUND. You must propose consensus points.\n"
            if is_final else ""
        )
        kwargs["final_round_instructions"] = (
            "\n4. PROPOSE CONSENSUS: What can all debaters agree on?\n"
            "5. Identify remaining disagreements clearly"
            if is_final else ""
        )
        kwargs["consensus_field"] = (
            '"consensus_proposal": ["Point all can agree on", ...],'
            if is_final else ""
        )

    return template.format(**kwargs)


# =============================================================================
# MAIN EXECUTION LOGIC
# =============================================================================

async def run_phase(
    provider: Provider,
    role: str,
    phase: str,
    topic: str,
    viewpoint: str,
    round_num: int = 1,
    speaker_order: int = 1,
    is_final: bool = False,
    own_research: str = "",
    visible_statements: str = "",
    debate_history: str = "",
    attacks_received: str = "",
    own_prep: str = "",
    round_statements: str = "",
    attacks_to_address: str = "",
) -> dict:
    """Run a debate phase with the specified LLM provider."""

    start_time = time.time()

    prompt = build_prompt(
        phase=phase,
        role=role,
        topic=topic,
        viewpoint=viewpoint,
        round=round_num,
        next_round=round_num + 1 if phase == "prep_defense" else round_num,
        speaker_order=speaker_order,
        is_final=is_final,
        own_research=own_research,
        visible_statements=visible_statements,
        debate_history=debate_history,
        attacks_received=attacks_received,
        own_prep=own_prep,
        round_statements=round_statements,
        attacks_to_address=attacks_to_address,
    )

    # Enable web search for research and prep phases
    enable_web = phase in ["initial_research", "prep_defense"]

    config = LLMConfig(
        provider=provider,
        tier=ModelTier.HIGH,
        auto_approval=AutoApproval.FULL if enable_web else AutoApproval.NONE,
        reasoning_level=ReasoningLevel.HIGH,
        timeout=TIMEOUT_CONFIG.get(phase),
    )

    # Add web search instruction if needed
    if enable_web:
        prompt = f"[You have access to web search. Use it to find current, verified information.]\n\n{prompt}"

    async def execute_llm():
        async with LLM(config) as llm:
            return await llm.run(prompt)

    retry_attempts = []

    def on_retry(attempt: int, error: Exception):
        retry_attempts.append({
            "attempt": attempt,
            "error": str(error),
            "timestamp": time.time() - start_time
        })

    try:
        # Execute with timeout and retry
        timeout = TIMEOUT_CONFIG.get(phase)

        result = await asyncio.wait_for(
            with_retry(execute_llm, RETRY_CONFIG, on_retry),
            timeout=timeout + 10  # Extra buffer for retries
        )

        response_text = result.text.strip()

        # Parse JSON with robust recovery
        parse_result = robust_json_parse(response_text)

        response = {
            "success": True,
            "provider": provider.value,
            "role": role,
            "phase": phase,
            "round": round_num,
            "session_id": result.session_id,
            "execution_time": time.time() - start_time,
        }

        if parse_result["parsed"]:
            response["result"] = parse_result["data"]
            if parse_result["strategy_used"] != "direct":
                response["parse_recovery"] = parse_result["strategy_used"]
        else:
            response["result"] = {"raw_response": parse_result["raw_response"]}
            response["warning"] = "JSON parsing failed after all recovery attempts"
            response["parse_details"] = {
                "error": parse_result["parse_error"],
                "strategies_tried": parse_result["strategies_tried"]
            }

        if retry_attempts:
            response["retry_history"] = retry_attempts

        return response

    except asyncio.TimeoutError:
        return {
            "success": False,
            "provider": provider.value,
            "role": role,
            "phase": phase,
            "round": round_num,
            "error": f"Timeout after {TIMEOUT_CONFIG.get(phase)}s",
            "error_type": "timeout",
            "execution_time": time.time() - start_time,
            "retry_history": retry_attempts,
        }

    except Exception as e:
        return {
            "success": False,
            "provider": provider.value,
            "role": role,
            "phase": phase,
            "round": round_num,
            "error": str(e),
            "error_type": type(e).__name__,
            "execution_time": time.time() - start_time,
            "retry_history": retry_attempts,
        }


# =============================================================================
# FALLBACK WRAPPER
# =============================================================================

async def run_phase_with_fallback(
    provider: Provider,
    role: str,
    phase: str,
    topic: str,
    viewpoint: str,
    fallback_config: FallbackConfig = FALLBACK_CONFIG,
    **kwargs
) -> dict:
    """Run a debate phase with automatic fallback on recoverable errors.

    This wrapper attempts the phase with the primary provider, and if a
    recoverable error occurs (rate limit, quota, timeout, etc.), automatically
    retries with the fallback provider (default: Claude).

    Args:
        provider: Primary LLM provider to use
        role: Debater role (A, B, or C)
        phase: Debate phase to execute
        topic: Debate topic
        viewpoint: Assigned viewpoint for this debater
        fallback_config: Configuration for fallback behavior
        **kwargs: Additional arguments passed to run_phase()

    Returns:
        Phase result dict, with fallback metadata if fallback occurred
    """
    fallback_history = []

    # Try with primary provider
    result = await run_phase(
        provider=provider,
        role=role,
        phase=phase,
        topic=topic,
        viewpoint=viewpoint,
        **kwargs
    )

    # Check if fallback is needed
    if not result["success"] and fallback_config.enabled and should_fallback(result):
        fallback_provider = PROVIDER_MAP.get(fallback_config.fallback_provider)

        # Only fallback if we have a different provider
        if fallback_provider and fallback_provider != provider:
            # Record the fallback event
            event = FallbackEvent(
                phase=phase,
                original_provider=provider.value,
                fallback_provider=fallback_config.fallback_provider,
                error_type=classify_error(result.get("error", "")),
                error_message=result.get("error", ""),
                timestamp=datetime.utcnow().isoformat() + "Z",
            )

            # Execute with fallback provider
            fallback_start = time.time()
            result = await run_phase(
                provider=fallback_provider,
                role=role,
                phase=phase,
                topic=topic,
                viewpoint=viewpoint,
                **kwargs
            )

            # Record recovery time
            event.recovery_time_ms = (time.time() - fallback_start) * 1000
            fallback_history.append(asdict(event))

            # Add fallback metadata to result
            result["fallback_used"] = True
            result["original_provider"] = provider.value

    # Include fallback history if any fallbacks occurred
    if fallback_history:
        result["fallback_history"] = fallback_history

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Multi-LLM Debater v3 - Production-grade debate system"
    )

    # Validation commands
    parser.add_argument("--validate-deps", action="store_true",
                        help="Validate dependencies and exit")
    parser.add_argument("--validate-api-key", type=str,
                        help="Validate API key for specified provider")

    # Required arguments
    parser.add_argument("--provider",
                        choices=["claude", "gpt", "codex", "gemini"])
    parser.add_argument("--role", choices=["A", "B", "C"])
    parser.add_argument("--phase",
                        choices=["initial_research", "round_claim", "round_claim_attack",
                                 "prep_defense", "round_defense"])
    parser.add_argument("--topic")
    parser.add_argument("--viewpoint")

    # Round information
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--speaker-order", type=int, default=1,
                        help="1=first, 2=second, 3=third in round")
    parser.add_argument("--is-final", action="store_true")

    # Fallback options
    parser.add_argument("--disable-fallback", action="store_true",
                        help="Disable automatic fallback to Claude on provider errors")
    parser.add_argument("--skip-health-check", action="store_true",
                        help="Skip pre-debate provider availability test")
    parser.add_argument("--health-check-only", action="store_true",
                        help="Run health check and exit (requires --provider)")

    # Context inputs (JSON strings)
    parser.add_argument("--own-research", default="{}")
    parser.add_argument("--visible-statements", default="")
    parser.add_argument("--debate-history", default="")
    parser.add_argument("--attacks-received", default="")
    parser.add_argument("--own-prep", default="{}")
    parser.add_argument("--round-statements", default="")
    parser.add_argument("--attacks-to-address", default="")

    args = parser.parse_args()

    # Handle validation commands
    if args.validate_deps:
        result = validate_dependencies()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["valid"] else 1)

    if args.validate_api_key:
        result = validate_api_keys(args.validate_api_key)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["valid"] else 1)

    # Handle health-check-only mode
    if args.health_check_only:
        if not args.provider:
            parser.error("--provider is required for --health-check-only")
        health_result = asyncio.run(run_pre_debate_health_checks([args.provider]))
        output = {
            "health_check": {k: asdict(v) for k, v in health_result.items()}
        }
        # Claude is always available (not actually tested)
        if args.provider == "claude":
            output["health_check"]["claude"] = asdict(ProviderStatus(
                provider="claude", available=True
            ))
        print(json.dumps(output, indent=2))
        sys.exit(0)

    # Validate required arguments for debate execution
    if not all([args.provider, args.role, args.phase, args.topic, args.viewpoint]):
        parser.error("--provider, --role, --phase, --topic, and --viewpoint are required")

    # Validate API key before execution
    api_check = validate_api_keys(args.provider)
    if not api_check["valid"]:
        print(json.dumps({
            "success": False,
            "error": api_check["error"],
            "error_type": "api_key_missing"
        }))
        sys.exit(1)

    provider = PROVIDER_MAP.get(args.provider)
    if not provider:
        print(json.dumps({
            "success": False,
            "error": f"Unknown provider: {args.provider}",
            "available_providers": list(PROVIDER_MAP.keys())
        }))
        sys.exit(1)

    # Pre-debate health check for gemini/codex (Claude is assumed available)
    effective_provider = provider
    pre_debate_warning = None

    if not args.skip_health_check and args.provider in ["gemini", "codex"]:
        health_results = asyncio.run(run_pre_debate_health_checks([args.provider]))
        status = health_results.get(args.provider)

        if status and not status.available:
            if not args.disable_fallback:
                # Switch to Claude before debate starts
                effective_provider = PROVIDER_MAP["claude"]
                pre_debate_warning = {
                    "message": f"{args.provider} unavailable, using claude",
                    "original_provider": args.provider,
                    "error": status.error,
                    "error_type": status.error_type
                }
                print(json.dumps({"warning": pre_debate_warning}), file=sys.stderr)
            else:
                # Fallback disabled - fail immediately
                print(json.dumps({
                    "success": False,
                    "error": f"Provider {args.provider} unavailable: {status.error}",
                    "error_type": status.error_type,
                    "provider_status": asdict(status)
                }))
                sys.exit(1)

    # Configure fallback behavior
    fallback_config = FallbackConfig(enabled=not args.disable_fallback)

    # Execute with fallback wrapper
    result = asyncio.run(run_phase_with_fallback(
        provider=effective_provider,
        role=args.role,
        phase=args.phase,
        topic=args.topic,
        viewpoint=args.viewpoint,
        fallback_config=fallback_config,
        round_num=args.round,
        speaker_order=args.speaker_order,
        is_final=args.is_final,
        own_research=args.own_research,
        visible_statements=args.visible_statements,
        debate_history=args.debate_history,
        attacks_received=args.attacks_received,
        own_prep=args.own_prep,
        round_statements=args.round_statements,
        attacks_to_address=args.attacks_to_address,
    ))

    # Include pre-debate warning in result if provider was switched
    if pre_debate_warning:
        result["pre_debate_fallback"] = pre_debate_warning

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
