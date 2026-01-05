#!/usr/bin/env python3
"""
Multi-LLM Debater Script v2

Complete debate system with proper context isolation and phased execution.

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
"""

import argparse
import asyncio
import json
import sys
from typing import Optional, Dict, Any

try:
    from u_llm_sdk import LLM, LLMConfig
    from llm_types import Provider, ModelTier, AutoApproval, ReasoningLevel
except ImportError:
    print(json.dumps({
        "error": "u-llm-sdk not installed. Run: pip install u-llm-sdk",
        "success": False
    }))
    sys.exit(1)


PROVIDER_MAP = {
    "claude": Provider.CLAUDE,
    "gpt": Provider.CODEX,
    "codex": Provider.CODEX,
    "gemini": Provider.GEMINI,
}

# =============================================================================
# PHASE PROMPTS - Each phase has specific context and output requirements
# =============================================================================

PHASE_PROMPTS = {
    # -------------------------------------------------------------------------
    # PHASE 0: Initial Research (Pre-debate)
    # Context: Topic only
    # Output: Research notes (private to this debater)
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # ROUND CLAIM: First speaker of a round (no one to attack yet)
    # Context: Topic + own research
    # Output: Claim with supporting arguments
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # ROUND CLAIM + ATTACK: 2nd or 3rd speaker
    # Context: Topic + own research + previous speakers' statements
    # Output: Claim + attacks on previous speakers
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # PREP DEFENSE: Between-round preparation
    # Context: All previous rounds + attacks received
    # Output: Defense strategy + additional research results
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # ROUND DEFENSE: Defense + counterattack during debate
    # Context: All history + own prep + other defenses in this round
    # -------------------------------------------------------------------------
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
        timeout=300.0,
    )

    # Add web search instruction if needed
    if enable_web:
        prompt = f"[You have access to web search. Use it to find current, verified information.]\n\n{prompt}"

    try:
        async with LLM(config) as llm:
            result = await llm.run(prompt)
            response_text = result.text.strip()

            # Extract JSON from response
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
                    "phase": phase,
                    "round": round_num,
                    "result": parsed,
                    "session_id": result.session_id,
                }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "provider": provider.value,
                    "role": role,
                    "phase": phase,
                    "round": round_num,
                    "result": {"raw_response": response_text},
                    "session_id": result.session_id,
                    "warning": "Failed to parse JSON, returning raw response"
                }

    except Exception as e:
        return {
            "success": False,
            "provider": provider.value,
            "role": role,
            "phase": phase,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="Multi-LLM Debater v2")

    # Required arguments
    parser.add_argument("--provider", required=True,
                        choices=["claude", "gpt", "codex", "gemini"])
    parser.add_argument("--role", required=True, choices=["A", "B", "C"])
    parser.add_argument("--phase", required=True,
                        choices=["initial_research", "round_claim", "round_claim_attack",
                                 "prep_defense", "round_defense"])
    parser.add_argument("--topic", required=True)
    parser.add_argument("--viewpoint", required=True)

    # Round information
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--speaker-order", type=int, default=1,
                        help="1=first, 2=second, 3=third in round")
    parser.add_argument("--is-final", action="store_true")

    # Context inputs (JSON strings)
    parser.add_argument("--own-research", default="{}")
    parser.add_argument("--visible-statements", default="")
    parser.add_argument("--debate-history", default="")
    parser.add_argument("--attacks-received", default="")
    parser.add_argument("--own-prep", default="{}")
    parser.add_argument("--round-statements", default="")
    parser.add_argument("--attacks-to-address", default="")

    args = parser.parse_args()

    provider = PROVIDER_MAP.get(args.provider)
    if not provider:
        print(json.dumps({"success": False, "error": f"Unknown provider: {args.provider}"}))
        sys.exit(1)

    result = asyncio.run(run_phase(
        provider=provider,
        role=args.role,
        phase=args.phase,
        topic=args.topic,
        viewpoint=args.viewpoint,
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

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
