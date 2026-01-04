---
name: debate
description: 3인 공격적 토론 - 주제에 대해 3개의 LLM이 3라운드 토론 후 합의점 도출
allowed-tools: ["Task", "WebSearch", "AskUserQuestion"]
---

# Aggressive Debate Skill

3인 토론자가 주제에 대해 3라운드 공격적 토론을 진행하고 최종 합의점을 도출합니다.

## Usage

```
/debate <topic>
/debate "AI가 인간의 창의성을 대체할 수 있는가?"
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| topic | Yes | 토론 주제 (질문 또는 명제 형태) |

## Process Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    DEBATE FLOW (3 Rounds)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                │
│  │Debater A│    │Debater B│    │Debater C│                │
│  │(관점 α) │    │(관점 β) │    │(관점 γ) │                │
│  └────┬────┘    └────┬────┘    └────┬────┘                │
│       │              │              │                       │
│  Phase 1: Research (Parallel)                               │
│       ├──────────────┼──────────────┤                       │
│       ▼              ▼              ▼                       │
│  [WebSearch + Knowledge Gathering]                          │
│                                                             │
│  Phase 2: Preparation                                       │
│       ├──────────────┼──────────────┤                       │
│       ▼              ▼              ▼                       │
│  [Analyze opponents' scripts → Attack/Support points]       │
│                                                             │
│  Phase 3: Debate Rounds                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Round 1: A → B → C  (A starts: attack/support only) │   │
│  │ Round 2: B → C → A  (rotate, with defense)          │   │
│  │ Round 3: C → A → B  (final round, aware of end)     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Phase 4: Conclusion                                        │
│       ├──────────────┼──────────────┤                       │
│       ▼              ▼              ▼                       │
│  [Consensus Summary] + [Unresolved → AskUserQuestion]       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Execution Instructions

### Step 1: Initialize Debate Orchestrator

Launch the debate-orchestrator agent with the topic:

```
Task(
  subagent_type: "philosopher:debate-orchestrator",
  prompt: """
  주제: {topic}

  토론을 시작합니다. 다음 단계를 순차적으로 진행하세요:
  1. 주제 분석 및 3개 관점 자동 할당
  2. Phase 1-4 실행
  3. 최종 결과 반환
  """
)
```

### Step 2: Orchestrator Handles All Phases

Orchestrator는 내부적으로:
1. 3개의 debater 에이전트를 생성 (각각 다른 관점)
2. Research → Preparation → Debate → Conclusion 진행
3. 각 라운드 결과를 누적 관리
4. 최종 합의/미합의 구분

### Step 3: Return Results

**합의된 부분**: 구조화된 요약으로 사용자에게 반환

**미합의 부분**: AskUserQuestion으로 사용자 판단 요청
```
AskUserQuestion(
  questions: [
    {
      question: "토론자들이 합의하지 못한 쟁점입니다. 어떤 관점이 더 타당하다고 생각하시나요?",
      header: "미합의 쟁점",
      options: [각 토론자의 입장],
      multiSelect: false
    }
  ]
)
```

## Output Format

```markdown
# 토론 결과: {topic}

## 참여자
- **토론자 A** ({관점 α}): {역할 설명}
- **토론자 B** ({관점 β}): {역할 설명}
- **토론자 C** ({관점 γ}): {역할 설명}

## 토론 하이라이트

### Round 1
{주요 공격/옹호 내용}

### Round 2
{방어 및 반격 내용}

### Round 3 (Final)
{최종 입장 정리}

## 합의된 사항
1. {합의점 1}
2. {합의점 2}
...

## 미합의 사항
{AskUserQuestion 결과 또는 남은 쟁점}

## 참고 자료
{토론 중 인용된 웹 검색 결과}
```

## Notes

- 각 토론자는 주제 분석 후 자동으로 적절한 관점이 할당됩니다
- 3라운드 토론은 모든 참여자가 "마지막 라운드"임을 인지한 상태로 진행됩니다
- 토론 중 새로운 정보가 필요하면 추가 WebSearch가 수행됩니다
