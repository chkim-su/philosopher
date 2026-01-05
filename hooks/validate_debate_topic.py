#!/usr/bin/env python3
"""
Debate Topic Quality Validator with Agent Delegation

Implements Pattern 2: Hook → Agent → Skill (100% Success)
- Hook analyzes topic quality using dimension-based analysis
- If quality is insufficient, blocks and instructs Claude to call topic-clarifier agent
- topic-clarifier agent uses AskUserQuestion to clarify with user
- Claude retries with clarified topic

Optimized for TECHNICAL debates:
- Project methodology decisions
- Implementation approaches
- Technology comparisons (A vs B)
- Architecture decisions
- Research directions

Inspired by forge-editor's forge-analyzer pattern.
"""

import sys
import json
import re
from dataclasses import dataclass
from typing import List, Optional


# =============================================================================
# DIMENSION ANALYSIS (forge-analyzer pattern)
# =============================================================================

@dataclass
class DimensionScore:
    """Score for a single analysis dimension."""
    name: str
    score: float  # 0.0 ~ 1.0
    reason: str
    suggestion: Optional[str] = None


@dataclass
class TopicAnalysis:
    """Complete topic analysis result."""
    topic: str
    dimensions: List[DimensionScore]
    overall_score: float
    is_valid: bool
    is_technical: bool = False
    primary_issue: Optional[str] = None
    weakest_dimension: Optional[str] = None

    def __post_init__(self):
        if not self.is_valid and self.dimensions:
            lowest = min(self.dimensions, key=lambda d: d.score)
            self.weakest_dimension = lowest.name
            self.primary_issue = f"{lowest.name}: {lowest.reason}"


# =============================================================================
# TECHNICAL TOPIC DETECTION
# =============================================================================

TECHNICAL_KEYWORDS = [
    # Programming/Tech
    'react', 'vue', 'angular', 'typescript', 'javascript', 'python', 'rust', 'go',
    'api', 'rest', 'graphql', 'grpc', 'microservice', 'monolith', 'serverless',
    'docker', 'kubernetes', 'aws', 'gcp', 'azure', 'cloud',
    'database', 'sql', 'nosql', 'redis', 'postgresql', 'mongodb', 'mysql',
    'frontend', 'backend', 'fullstack', 'devops', 'cicd', 'ci/cd',
    'tdd', 'bdd', 'testing', 'unit test', 'integration',
    'agile', 'scrum', 'kanban', 'waterfall',
    'architecture', 'design pattern', 'solid', 'dry', 'kiss',
    'framework', 'library', 'sdk', 'cli', 'gui',
    'ai', 'ml', 'llm', 'gpt', 'claude', 'gemini', 'model',
    'algorithm', 'data structure', 'optimization', 'performance',
    # Korean equivalents
    '프로젝트', '구현', '방법론', '아키텍처', '설계', '개발', '기술',
    '프레임워크', '라이브러리', '데이터베이스', '서버', '클라이언트',
    '마이크로서비스', '모놀리식', '테스트', '배포', '인프라',
    '알고리즘', '최적화', '성능', '확장성', '유지보수',
    '연구', '분석', '전략', '접근법', '패턴',
]

COMPARISON_PATTERNS = [
    r'\bvs\.?\b',
    r'\bor\b',
    r'\bversus\b',
    r'와\s*비교',
    r'대\s',
    r'이냐\s',
    r'할까\s*말까',
    r'도입\s*(여부|할지)',
    r'사용\s*(여부|할지)',
    r'적용\s*(여부|할지)',
    r'선택',
    r'결정',
    r'어떤\s*(것|방법|접근)',
]


def is_technical_topic(topic: str) -> bool:
    """Check if topic is technical/methodology related."""
    topic_lower = topic.lower()

    # Check for technical keywords
    for kw in TECHNICAL_KEYWORDS:
        if kw.lower() in topic_lower:
            return True

    # Check for comparison patterns
    for pattern in COMPARISON_PATTERNS:
        if re.search(pattern, topic, re.IGNORECASE):
            return True

    return False


# =============================================================================
# DIMENSION ANALYZERS
# =============================================================================

def analyze_clarity(topic: str, is_technical: bool) -> DimensionScore:
    """
    Dimension 1: Clarity (명확성)
    Is the topic clear and understandable?
    """
    score = 1.0
    reasons = []
    suggestion = None

    # Technical topics can be shorter (e.g., "React vs Vue")
    # But single keywords are still too vague
    topic_len = len(topic)

    if topic_len < 4:
        # Very short - single word/acronym without context
        score = 0.2
        reasons.append("주제가 너무 짧습니다")
        suggestion = "비교 대상이나 맥락을 추가해주세요 (예: 'AI' → 'AI vs ML for this task')"
    elif topic_len < (6 if is_technical else 10):
        # Short - needs more context
        score = 0.4
        reasons.append("주제에 맥락이 부족합니다")
        suggestion = "프로젝트 맥락이나 비교 대상을 추가해주세요"

    # Vague pronouns (still problematic)
    vague_patterns = [
        (r'\b(이것|그것|저것)\b', "지시대명사가 모호합니다"),
        (r'^(이게|그게|저게)\s', "대상이 불명확합니다"),
    ]

    for pattern, reason in vague_patterns:
        if re.search(pattern, topic):
            score = min(score, 0.5)
            reasons.append(reason)
            suggestion = "구체적인 기술/방법론 이름을 명시해주세요"

    return DimensionScore(
        name="clarity",
        score=score,
        reason="; ".join(reasons) if reasons else "주제가 명확합니다",
        suggestion=suggestion
    )


def analyze_debatability(topic: str, is_technical: bool) -> DimensionScore:
    """
    Dimension 2: Debatability (토론가능성)
    Can this topic support multiple valid viewpoints?
    """
    score = 1.0
    reasons = []
    suggestion = None

    # For technical topics, comparisons are inherently debatable
    if is_technical:
        for pattern in COMPARISON_PATTERNS:
            if re.search(pattern, topic, re.IGNORECASE):
                score = min(score + 0.2, 1.0)  # Bonus for comparison format
                break

    # Pure factual questions (still problematic)
    factual_patterns = [
        (r'^언제\s', "시점 확인 질문입니다"),
        (r'^누가\s', "사실 확인 질문입니다"),
    ]

    for pattern, reason in factual_patterns:
        if re.search(pattern, topic):
            score = min(score, 0.5)
            reasons.append(reason)
            suggestion = "의사결정이나 비교 형태로 재구성해주세요"

    # One-sided (still problematic but less strict for technical)
    if not is_technical:
        obvious_patterns = [
            (r'(당연히|물론|명백히)\s', "결론이 전제되어 있습니다"),
        ]
        for pattern, reason in obvious_patterns:
            if re.search(pattern, topic):
                score = min(score, 0.7)
                reasons.append(reason)

    return DimensionScore(
        name="debatability",
        score=score,
        reason="; ".join(reasons) if reasons else "토론 가능한 주제입니다",
        suggestion=suggestion
    )


def analyze_specificity(topic: str, is_technical: bool) -> DimensionScore:
    """
    Dimension 3: Specificity (구체성)
    Is the topic specific enough for meaningful debate?
    """
    score = 1.0
    reasons = []
    suggestion = None

    # Word count - more lenient for technical topics
    words = re.findall(r'[가-힣a-zA-Z0-9]+', topic)
    min_words = 2 if is_technical else 3

    if len(words) < min_words:
        score = min(score, 0.5)
        reasons.append("키워드가 부족합니다")
        suggestion = "비교 대상이나 프로젝트 맥락을 추가해주세요"
    elif len(words) > 40:
        score = min(score, 0.7)
        reasons.append("주제가 너무 복잡합니다")
        suggestion = "핵심 의사결정 하나에 집중해주세요"

    # Technical topics with clear comparisons get bonus
    if is_technical and re.search(r'\bvs\.?\b|versus|\bor\b', topic, re.IGNORECASE):
        score = min(score + 0.1, 1.0)

    return DimensionScore(
        name="specificity",
        score=score,
        reason="; ".join(reasons) if reasons else "적절한 구체성입니다",
        suggestion=suggestion
    )


def analyze_actionability(topic: str, is_technical: bool) -> DimensionScore:
    """
    Dimension 4: Actionability (실행가능성)
    Can this debate lead to actionable conclusions?
    (Replaces "Evidence Potential" - more relevant for technical debates)
    """
    score = 1.0
    reasons = []
    suggestion = None

    # Technical topics are inherently actionable
    if is_technical:
        score = min(score + 0.2, 1.0)

    # Decision-oriented keywords boost score
    action_keywords = [
        '도입', '적용', '사용', '선택', '결정', '구현', '설계', '채택',
        'implement', 'use', 'adopt', 'choose', 'build', 'design',
        'should', 'better', 'best', 'optimal', 'recommend',
    ]
    if any(kw in topic.lower() for kw in action_keywords):
        score = min(score + 0.1, 1.0)

    # Pure hypotheticals are less actionable
    hypothetical_patterns = [
        (r'만약.*없었다면', "가정적/반사실적 주제입니다"),
    ]

    for pattern, reason in hypothetical_patterns:
        if re.search(pattern, topic):
            score = min(score, 0.6)
            reasons.append(reason)
            suggestion = "현재 의사결정에 초점을 맞춰주세요"

    return DimensionScore(
        name="actionability",
        score=score,
        reason="; ".join(reasons) if reasons else "실행 가능한 결론 도출이 가능합니다",
        suggestion=suggestion
    )


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

def analyze_topic(topic: str) -> TopicAnalysis:
    """
    Perform full dimension analysis on debate topic.
    Returns TopicAnalysis with scores and suggestions.
    """
    is_technical = is_technical_topic(topic)

    dimensions = [
        analyze_clarity(topic, is_technical),
        analyze_debatability(topic, is_technical),
        analyze_specificity(topic, is_technical),
        analyze_actionability(topic, is_technical),
    ]

    # Calculate overall score (weighted average)
    # For technical topics, actionability matters more
    if is_technical:
        weights = [0.25, 0.25, 0.2, 0.3]
    else:
        weights = [0.3, 0.3, 0.2, 0.2]

    overall_score = sum(d.score * w for d, w in zip(dimensions, weights))

    # Threshold settings
    # Technical topics: slightly more lenient overall but still need reasonable quality
    threshold = 0.55 if is_technical else 0.6
    min_dimension = 0.3  # Same minimum for both - prevents single-word topics

    is_valid = overall_score >= threshold and all(d.score >= min_dimension for d in dimensions)

    return TopicAnalysis(
        topic=topic,
        dimensions=dimensions,
        overall_score=overall_score,
        is_valid=is_valid,
        is_technical=is_technical,
    )


# =============================================================================
# HOOK ENTRY POINT - Pattern 2: Block + Agent Delegation
# =============================================================================

def validate_input():
    """
    Main hook entry point - validates debate topic quality.

    Pattern 2 Implementation:
    - If topic quality is good: allow skill execution
    - If topic quality is bad: block + instruct Claude to call topic-clarifier agent
    """
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Extract tool input
    tool_input = input_data.get("tool_input", {})

    # Check if this is a Skill invocation for debate
    skill_name = tool_input.get("skill", "")
    skill_args = tool_input.get("args", "")

    # Only validate debate skills
    if skill_name not in ["debate", "debate-multiverse", "philosopher:debate", "philosopher:debate-multiverse"]:
        # Not a debate skill - allow
        print(json.dumps({"decision": "allow", "reason": None}))
        sys.exit(0)

    # Extract topic from args
    topic = skill_args.strip() if skill_args else ""

    # Remove flags from topic
    topic = re.sub(r'\s+--\S+.*$', '', topic).strip()
    topic = topic.strip('"\'')

    if not topic:
        print(json.dumps({
            "decision": "block",
            "reason": """토론 주제가 제공되지 않았습니다.

사용법: /debate "토론 주제"

예시:
- /debate "React vs Vue for our frontend"
- /debate "마이크로서비스 도입 여부"
- /debate "TDD 적용 범위 결정"

MANDATORY: 사용자에게 토론 주제를 입력받으세요."""
        }))
        sys.exit(0)

    # Perform dimension analysis
    analysis = analyze_topic(topic)

    if analysis.is_valid:
        # Topic is good - allow with info
        topic_type = "기술/방법론" if analysis.is_technical else "일반"
        print(f"[Topic Quality] Score: {analysis.overall_score:.2f} ✓ ({topic_type})", file=sys.stderr)
        for d in analysis.dimensions:
            print(f"  - {d.name}: {d.score:.2f}", file=sys.stderr)

        print(json.dumps({"decision": "allow", "reason": None}))
    else:
        # Topic needs improvement - BLOCK + DELEGATE TO AGENT
        analysis_json = json.dumps({
            "topic": analysis.topic,
            "overall_score": analysis.overall_score,
            "is_technical": analysis.is_technical,
            "weakest_dimension": analysis.weakest_dimension,
            "dimensions": {d.name: {"score": d.score, "reason": d.reason} for d in analysis.dimensions}
        }, ensure_ascii=False)

        reason = f"""토론 주제 명확화가 필요합니다.

주제: "{analysis.topic}"
유형: {"기술/방법론 토론" if analysis.is_technical else "일반 토론"}
품질 점수: {analysis.overall_score:.2f}/1.00
주요 문제: {analysis.primary_issue}

MANDATORY: philosopher:topic-clarifier 에이전트를 호출하여 주제를 명확화하세요.

Task tool 사용법:
- subagent_type: "philosopher:topic-clarifier"
- prompt: 아래 분석 결과와 함께 주제 전달

분석 결과:
{analysis_json}

에이전트가 프로젝트 맥락, 비교 대상, 의사결정 범위 등을 질문하여 명확화합니다.
명확화된 주제로 /debate 스킬을 다시 호출하세요."""

        print(json.dumps({
            "decision": "block",
            "reason": reason
        }))


if __name__ == "__main__":
    validate_input()
