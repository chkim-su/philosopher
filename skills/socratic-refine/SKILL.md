---
name: socratic
description: 소크라테스식 자문자답 - ultrathink 심층 분석 후 brainstorm 에이전트와 Q&A로 정제
allowed-tools: ["Task"]
---

# Socratic Self-Refining Skill

소크라테스식 자문자답을 통해 문제를 심층 분석하고 정제된 결론을 도출합니다.

## Usage

```
/socratic <question_or_problem>
/socratic "인공지능의 윤리적 한계는 어디까지인가?"
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| question | Yes | 심층 분석할 질문 또는 문제 |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 SOCRATIC SYSTEM ARCHITECTURE                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              SOCRATIC-ORCHESTRATOR                     │ │
│  │         (컨텍스트 영속성 & 루프 제어)                    │ │
│  │                                                        │ │
│  │  ┌─────────────────────────────────────────────────┐  │ │
│  │  │                    STATE                         │  │ │
│  │  │  - qa_history: QAEntry[]                        │  │ │
│  │  │  - current_answer: Answer                       │  │ │
│  │  │  - satisfaction_state: Evaluation               │  │ │
│  │  │  - score_history: number[]                      │  │ │
│  │  └─────────────────────────────────────────────────┘  │ │
│  │                         │                              │ │
│  │           ┌─────────────┴─────────────┐               │ │
│  │           ▼                           ▼               │ │
│  │  ┌─────────────────┐       ┌─────────────────┐       │ │
│  │  │ SOCRATIC-THINKER│◄─────►│SOCRATIC-QUESTION│       │ │
│  │  │   (ultrathink)  │ Q&A   │   (brainstorm)  │       │ │
│  │  │                 │ Loop  │                 │       │ │
│  │  │ • 깊은 분석     │       │ • 5차원 평가    │       │ │
│  │  │ • 보완 답변     │       │ • 후속 질문     │       │ │
│  │  └─────────────────┘       └─────────────────┘       │ │
│  │                                                        │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Process Overview

```
┌─────────────────────────────────────────────────────────────┐
│                 SOCRATIC SELF-REFINING FLOW                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 1: Orchestrator 실행                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Task(socratic-orchestrator)                         │  │
│  │  - 상태 초기화                                        │  │
│  │  - Q&A 루프 관리                                      │  │
│  │  - 컨텍스트 브릿징                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                 │
│                           ▼                                 │
│  Step 2: Initial Analysis (Orchestrator 내부)              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Thinker: ultrathink 모드                             │  │
│  │  - 문제의 본질 파악                                   │  │
│  │  - 다각도 분석                                        │  │
│  │  - 잠재적 맹점 식별                                   │  │
│  │  - 초기 가설 수립                                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                 │
│                           ▼                                 │
│  Step 3: Q&A Loop (Orchestrator가 조율)                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  while (!satisfied && round <= 10):                  │  │
│  │                                                       │  │
│  │    Questioner: 답변 평가 (5차원)                      │  │
│  │         │                                             │  │
│  │         ├─ satisfied? → 종료                          │  │
│  │         ├─ stagnation? → 조기 종료                    │  │
│  │         └─ 부족? → 후속 질문 생성                     │  │
│  │                    │                                  │  │
│  │                    ▼                                  │  │
│  │    Thinker: 보완 답변 (ultrathink)                    │  │
│  │         │                                             │  │
│  │         └─ qa_history에 축적 (컨텍스트 영속)          │  │
│  │                                                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                 │
│                           ▼                                 │
│  Step 4: Output Routing                                    │
│  ┌─────────────────┐   ┌─────────────────┐                 │
│  │ Standalone Mode │   │  Invoked Mode   │                 │
│  │ → Report to     │   │  → Return to    │                 │
│  │   User          │   │   Calling Agent │                 │
│  └─────────────────┘   └─────────────────┘                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Execution Instructions

### Single Entry Point

`/socratic` 스킬은 단일 진입점으로 오케스트레이터를 호출합니다:

```
Task(
  subagent_type: "philosopher:socratic-orchestrator",
  prompt: """
  문제: {question}

  소크라테스식 자문자답을 수행합니다.
  1. ultrathink로 심층 분석
  2. Q&A 루프로 정제
  3. 품질 만족 시 종료
  4. 최종 결과 반환
  """
)
```

오케스트레이터가 내부적으로:
1. `socratic-thinker` 호출 (초기 분석)
2. `socratic-questioner` 호출 (평가)
3. Q&A 루프 반복 (컨텍스트 전달하며)
4. 종료 조건 충족 시 결과 반환

## Quality-Based Termination

Questioner는 다음 기준으로 만족 여부를 판단합니다:

| 차원 | 설명 | 가중치 |
|------|------|--------|
| **깊이 (Depth)** | 근본 원리까지 도달 | 20% |
| **일관성 (Coherence)** | 논리적 모순 없음 | 20% |
| **완전성 (Completeness)** | 주요 측면 포괄 | 20% |
| **실용성 (Practicality)** | 적용 가능한 통찰 | 20% |
| **겸손 (Humility)** | 한계 인정 | 20% |

```
satisfaction_score = (depth + coherence + completeness + practicality + humility) / 5

if satisfaction_score >= 0.8:
  terminate with success
elif round >= 10:
  terminate with max_rounds
elif stagnation detected (2연속 개선 < 0.05):
  terminate with stagnation
else:
  generate follow_up_question targeting weakest_dimension
```

## Output Format

### 단독 실행 시

```markdown
# 소크라테스식 분석 결과

## 원본 질문
{original_question}

## 심층 분석 과정

### 초기 고찰 (ultrathink)
{initial_deep_analysis}

### Q&A 정제 과정
| # | 질문 | 핵심 답변 | 품질 |
|---|------|----------|------|
| 1 | {q1} | {a1_summary} | 0.72 |
| 2 | {q2} | {a2_summary} | 0.78 |
| 3 | {q3} | {a3_summary} | 0.84 |

## 최종 결론

### 핵심 통찰
{refined_answer}

### 한계 및 미해결 문제
{limitations}

### 추가 탐구 방향
{further_exploration}

---
*신뢰도: 0.84 | 정제 라운드: 3 | 종료: 품질 만족*
```

### 호출 모드 시 (반환 형식)

```json
{
  "original_question": "{question}",
  "refinement_rounds": 3,
  "termination_reason": "quality_satisfied",
  "final_answer": {
    "core_insight": "핵심 통찰",
    "supporting_points": ["포인트1", "포인트2"],
    "limitations": ["한계1"],
    "confidence": 0.84
  },
  "qa_history": [
    {"round": 1, "question": "q1", "answer_summary": "a1", "score": 0.72},
    {"round": 2, "question": "q2", "answer_summary": "a2", "score": 0.78},
    {"round": 3, "question": "q3", "answer_summary": "a3", "score": 0.84}
  ]
}
```

## Integration Example

다른 에이전트에서 socratic 스킬 호출:

```
# 토론 전 깊은 분석이 필요할 때
socratic_result = Task(
  subagent_type: "philosopher:socratic-orchestrator",
  prompt: "문제: {topic}를 소크라테스식으로 분석해주세요"
)

# 결과를 토론에 활용
use(socratic_result.final_answer)
```

## Notes

- **컨텍스트 영속성**: Orchestrator가 qa_history를 축적하여 각 에이전트에 전달
- **독립 에이전트 격리**: Thinker와 Questioner는 각각 별도 Task로 호출되며, Orchestrator가 브릿징
- **품질 기반 종료**: 고정 라운드 수가 아닌 만족도 기준
- **무한 루프 방지**: 최대 10라운드 + 정체 감지
- **일반적으로 2-5회의 Q&A로 충분한 정제가 이루어집니다**
