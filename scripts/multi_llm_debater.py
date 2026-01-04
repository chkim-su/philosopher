#!/usr/bin/env python3
"""
Multi-LLM Debater Script

Enables cross-provider debates using u-llm-sdk.
Each debater can use a different LLM provider (Claude, GPT, Gemini).

Usage:
    python multi_llm_debater.py --provider claude --role A --stage research \
        --topic "AI ethics" --viewpoint "Pro-regulation"
"""

import argparse
import asyncio
import json
import sys
from typing import Optional

try:
    from u_llm_sdk import LLM, LLMConfig
    from llm_types import Provider, ModelTier, AutoApproval, ReasoningLevel
except ImportError:
    print(json.dumps({
        "error": "u-llm-sdk not installed. Run: pip install u-llm-sdk",
        "success": False
    }))
    sys.exit(1)


# Provider mapping
PROVIDER_MAP = {
    "claude": Provider.CLAUDE,
    "gpt": Provider.CODEX,
    "codex": Provider.CODEX,
    "gemini": Provider.GEMINI,
}

# Stage-specific prompts
STAGE_PROMPTS = {
    "research": """You are Debater {role} with viewpoint: {viewpoint}

Topic: {topic}

STAGE: RESEARCH

Your task:
1. Gather evidence supporting your viewpoint
2. Identify key arguments and counterarguments
3. Note potential weaknesses in your position

Output your findings in JSON format:
{{
    "viewpoint": "{viewpoint}",
    "core_thesis": "Your main argument in one sentence",
    "evidence": [
        {{"type": "research|statistics|expert|logic", "content": "...", "source": "..."}}
    ],
    "potential_weaknesses": ["weakness1", "weakness2"]
}}

Be thorough but concise. Focus on quality arguments over quantity.""",

    "preparation": """You are Debater {role} with viewpoint: {viewpoint}

Topic: {topic}

STAGE: PREPARATION

Your research: {own_research}

Opponent research:
{opponent_research}

Your task:
1. Analyze opponents' arguments for weaknesses
2. Prepare attack points against each opponent
3. Identify potential allies for support
4. Prepare defenses against expected attacks

Output in JSON format:
{{
    "attacks": [
        {{"target": "B|C", "point": "...", "strategy": "logical_flaw|weak_evidence|counterexample"}}
    ],
    "supports": [
        {{"target": "B|C", "point": "...", "reason": "..."}}
    ],
    "defense_prep": [
        {{"anticipated_attack": "...", "defense": "..."}}
    ]
}}""",

    "debate": """You are Debater {role} with viewpoint: {viewpoint}

Topic: {topic}

STAGE: DEBATE - Round {round}
{final_round_notice}

Your preparation: {preparation}

Debate history so far:
{debate_history}

Constraints: {constraints}

Your task:
1. Analyze the current debate state
2. Choose your action (attack/support/defend)
3. Make your argument clearly and persuasively

Output in JSON format:
{{
    "round": {round},
    "speaker": "{role}",
    "actions": [
        {{
            "type": "attack|support|defend",
            "target": "A|B|C",
            "content": "Your argument in markdown format",
            "key_point": "One-sentence summary"
        }}
    ],
    "stance_summary": "Your current position after this round",
    "consensus_proposal": "If final round, propose what you can agree on"
}}

Be assertive but respectful. Attack ideas, not personalities.""",
}


def build_prompt(stage: str, **kwargs) -> str:
    """Build the appropriate prompt for the given stage."""
    template = STAGE_PROMPTS.get(stage)
    if not template:
        raise ValueError(f"Unknown stage: {stage}")

    # Handle final round notice
    if stage == "debate":
        kwargs["final_round_notice"] = (
            "\n⚠️ THIS IS THE FINAL ROUND. Make your strongest case and propose consensus points.\n"
            if kwargs.get("is_final") else ""
        )

    return template.format(**kwargs)


async def run_debater(
    provider: Provider,
    role: str,
    stage: str,
    topic: str,
    viewpoint: str,
    round_num: int = 1,
    is_final: bool = False,
    own_research: str = "",
    opponent_research: str = "",
    preparation: str = "",
    debate_history: str = "",
    constraints: str = "attack, support, defend all allowed",
) -> dict:
    """Run a debater with the specified LLM provider."""

    # Build the prompt
    prompt = build_prompt(
        stage=stage,
        role=role,
        viewpoint=viewpoint,
        topic=topic,
        round=round_num,
        is_final=is_final,
        own_research=own_research,
        opponent_research=opponent_research,
        preparation=preparation,
        debate_history=debate_history,
        constraints=constraints,
    )

    # Configure LLM
    config = LLMConfig(
        provider=provider,
        tier=ModelTier.HIGH,
        auto_approval=AutoApproval.NONE,
        reasoning_level=ReasoningLevel.HIGH,
        timeout=300.0,
    )

    try:
        async with LLM(config) as llm:
            result = await llm.run(prompt)

            # Try to parse JSON from response
            response_text = result.text.strip()

            # Extract JSON if wrapped in code blocks
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            try:
                parsed = json.loads(response_text)
                return {
                    "success": True,
                    "provider": provider.value,
                    "role": role,
                    "stage": stage,
                    "result": parsed,
                    "session_id": result.session_id,
                }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "provider": provider.value,
                    "role": role,
                    "stage": stage,
                    "result": {"raw_response": response_text},
                    "session_id": result.session_id,
                }

    except Exception as e:
        return {
            "success": False,
            "provider": provider.value,
            "role": role,
            "stage": stage,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="Multi-LLM Debater")
    parser.add_argument("--provider", required=True, choices=["claude", "gpt", "codex", "gemini"],
                        help="LLM provider to use")
    parser.add_argument("--role", required=True, choices=["A", "B", "C"],
                        help="Debater role")
    parser.add_argument("--stage", required=True, choices=["research", "preparation", "debate"],
                        help="Debate stage")
    parser.add_argument("--topic", required=True, help="Debate topic")
    parser.add_argument("--viewpoint", required=True, help="Debater's viewpoint")
    parser.add_argument("--round", type=int, default=1, help="Round number (for debate stage)")
    parser.add_argument("--is-final", action="store_true", help="Is this the final round?")
    parser.add_argument("--own-research", default="", help="Own research results (JSON)")
    parser.add_argument("--opponent-research", default="", help="Opponent research (JSON)")
    parser.add_argument("--preparation", default="", help="Preparation results (JSON)")
    parser.add_argument("--debate-history", default="", help="Previous debate history")
    parser.add_argument("--constraints", default="attack, support, defend all allowed",
                        help="Action constraints")

    args = parser.parse_args()

    provider = PROVIDER_MAP.get(args.provider)
    if not provider:
        print(json.dumps({"success": False, "error": f"Unknown provider: {args.provider}"}))
        sys.exit(1)

    result = asyncio.run(run_debater(
        provider=provider,
        role=args.role,
        stage=args.stage,
        topic=args.topic,
        viewpoint=args.viewpoint,
        round_num=args.round,
        is_final=args.is_final,
        own_research=args.own_research,
        opponent_research=args.opponent_research,
        preparation=args.preparation,
        debate_history=args.debate_history,
        constraints=args.constraints,
    ))

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
