---
name: debate-multiverse
description: 멀티 프로바이더 토론 - Claude/GPT/Gemini 3자가 각자의 관점에서 토론
allowed-tools: ["Task", "Bash", "Read", "Glob", "Grep", "WebSearch", "WebFetch", "AskUserQuestion"]
---

# Multi-Provider Debate Skill (Multiverse)

서로 다른 LLM 프로바이더(Claude, GPT, Gemini)가 각각 다른 관점을 대변하여 3자 토론을 진행합니다.

## Usage

```
/debate-multiverse <topic>
/debate-multiverse "AI가 인간의 일자리를 대체해야 하는가?"
```

### With Provider Selection

```
/debate-multiverse <topic> --providers claude,gpt,gemini
/debate-multiverse "기본소득제의 필요성" --providers gemini,claude,gpt
```

## Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| topic | Yes | - | 토론 주제 |
| --providers | No | claude,gpt,gemini | A,B,C 토론자에 할당할 프로바이더 |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  MULTIVERSE DEBATE FLOW                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │        debate-orchestrator (Claude Opus)               │ │
│  │        - 전체 흐름 조율                                 │ │
│  │        - multi_llm_debater.py 스크립트 호출            │ │
│  │        - 결과 통합 및 합의 도출                         │ │
│  └───────────────────────────────────────────────────────┘ │
│                           │                                 │
│         ┌─────────────────┼─────────────────┐               │
│         ▼                 ▼                 ▼               │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐        │
│  │  Debater A │    │  Debater B │    │  Debater C │        │
│  │  (Claude)  │    │   (GPT)    │    │  (Gemini)  │        │
│  │   Opus     │    │  gpt-5.2   │    │ gemini-3   │        │
│  │            │    │  (Codex)   │    │            │        │
│  │ viewpoint α│    │ viewpoint β│    │ viewpoint γ│        │
│  └────────────┘    └────────────┘    └────────────┘        │
│                                                             │
│  Script: scripts/multi_llm_debater.py                      │
│  SDK: u-llm-sdk (unified provider interface)               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Provider Mapping

| Provider | LLM | Model (HIGH tier) |
|----------|-----|-------------------|
| claude | Claude | Opus |
| gpt / codex | OpenAI via Codex | gpt-5.2 + HIGH reasoning |
| gemini | Google Gemini | gemini-3-pro-preview |

## Debate Phases

토론은 5개의 phase로 진행됩니다:

| Phase | 설명 | WebSearch | 실행 방식 |
|-------|------|-----------|----------|
| `initial_research` | 사전 조사 | ✅ 활성화 | **병렬** |
| `round_claim` | 라운드 첫 발언자 주장 | ❌ | 순차 |
| `round_claim_attack` | 후속 발언자 주장 + 공격 | ❌ | 순차 |
| `prep_defense` | 라운드 간 방어 준비 | ✅ 활성화 | **병렬** |
| `round_defense` | 방어 + 반격 | ❌ | 순차 |

### Context Isolation (핵심 원칙)

```
┌────────────────────────────────────────────────────────────┐
│  CONTEXT ISOLATION: 각 토론자는 자신에게 공개된 정보만 접근     │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Debater A가 받는 컨텍스트:                                 │
│  ├─ topic (주제)                                           │
│  ├─ own_research (자신의 조사 결과)                         │
│  └─ visible_statements (이전 발언자들의 공개된 발언)         │
│                                                            │
│  ⚠️ B의 조사 결과, C의 전략 등은 절대 공개되지 않음          │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## Execution Instructions

### Step 1: Parse Arguments & Initialize

```python
# 기본 프로바이더 설정
providers = {
    "A": "claude",
    "B": "gpt",
    "C": "gemini"
}

# 사용자가 --providers 지정 시 오버라이드
if user_providers:
    providers["A"], providers["B"], providers["C"] = user_providers.split(",")
```

### Step 2: Viewpoint Assignment

주제를 분석하여 3개의 상반된 관점을 자동 할당:

```thinking
주제: "{topic}"

각 프로바이더에게 가장 적합한 관점을 할당합니다:
- Claude (관점 α): 윤리적/철학적 접근
- GPT (관점 β): 실용적/기술적 접근
- Gemini (관점 γ): 균형적/비판적 접근

이는 각 LLM의 특성을 활용하여 더 풍부한 토론을 유도합니다.
```

### Step 3: Initial Research Phase (⚡ PARALLEL)

**중요: 이 phase는 반드시 병렬로 실행해야 합니다.**

각 프로바이더를 병렬로 호출하여 독립적 조사 수행:

```bash
# 병렬 실행 - 모든 토론자가 동시에 조사
python scripts/multi_llm_debater.py \
    --provider claude --role A --phase initial_research \
    --topic "{topic}" --viewpoint "{viewpoint_a}" &

python scripts/multi_llm_debater.py \
    --provider gpt --role B --phase initial_research \
    --topic "{topic}" --viewpoint "{viewpoint_b}" &

python scripts/multi_llm_debater.py \
    --provider gemini --role C --phase initial_research \
    --topic "{topic}" --viewpoint "{viewpoint_c}" &

wait  # 모든 프로세스 완료 대기
```

각 조사 결과는 해당 토론자의 private context로 저장됩니다.

### Step 4: Round 1 - Claims & Attacks (Sequential)

```bash
# A가 먼저 주장 (공격 대상 없음)
python scripts/multi_llm_debater.py \
    --provider claude --role A --phase round_claim \
    --topic "{topic}" --viewpoint "{viewpoint_a}" \
    --round 1 --own-research '{research_a_json}'

# B가 주장 + A 공격 (A의 발언만 visible)
python scripts/multi_llm_debater.py \
    --provider gpt --role B --phase round_claim_attack \
    --topic "{topic}" --viewpoint "{viewpoint_b}" \
    --round 1 --speaker-order 2 \
    --own-research '{research_b_json}' \
    --visible-statements '{statement_a_json}'

# C가 주장 + A,B 공격 (A,B 발언 모두 visible)
python scripts/multi_llm_debater.py \
    --provider gemini --role C --phase round_claim_attack \
    --topic "{topic}" --viewpoint "{viewpoint_c}" \
    --round 1 --speaker-order 3 \
    --own-research '{research_c_json}' \
    --visible-statements '{statement_a_json}\n{statement_b_json}'
```

### Step 5: Defense Preparation (⚡ PARALLEL)

**중요: 이 phase는 반드시 병렬로 실행해야 합니다.**

각 토론자가 자신에게 온 공격을 분석하고 추가 조사:

```bash
# 병렬 실행 - 모든 토론자가 동시에 방어 준비
python scripts/multi_llm_debater.py \
    --provider claude --role A --phase prep_defense \
    --topic "{topic}" --viewpoint "{viewpoint_a}" \
    --round 1 \
    --own-research '{research_a_json}' \
    --debate-history '{round1_history}' \
    --attacks-received '{attacks_on_a}' &

python scripts/multi_llm_debater.py \
    --provider gpt --role B --phase prep_defense \
    --topic "{topic}" --viewpoint "{viewpoint_b}" \
    --round 1 \
    --own-research '{research_b_json}' \
    --debate-history '{round1_history}' \
    --attacks-received '{attacks_on_b}' &

python scripts/multi_llm_debater.py \
    --provider gemini --role C --phase prep_defense \
    --topic "{topic}" --viewpoint "{viewpoint_c}" \
    --round 1 \
    --own-research '{research_c_json}' \
    --debate-history '{round1_history}' \
    --attacks-received '{attacks_on_c}' &

wait  # 모든 프로세스 완료 대기
```

### Step 6: Round 2 - Defense & Counterattack (Sequential)

```bash
# 발언 순서 회전: B → C → A
python scripts/multi_llm_debater.py \
    --provider gpt --role B --phase round_defense \
    --topic "{topic}" --viewpoint "{viewpoint_b}" \
    --round 2 \
    --own-research '{research_b_json}' \
    --own-prep '{prep_b_json}' \
    --debate-history '{full_history}' \
    --attacks-to-address '{attacks_on_b}'

# C 방어 + 반격
# A 방어 + 반격
```

### Step 7: Round 3 - Final Round (Sequential)

```bash
# 발언 순서 회전: C → A → B
# --is-final 플래그 추가로 합의점 제안 요청
python scripts/multi_llm_debater.py \
    --provider gemini --role C --phase round_defense \
    --topic "{topic}" --viewpoint "{viewpoint_c}" \
    --round 3 --is-final \
    --own-research '{research_c_json}' \
    --own-prep '{prep_c_json}' \
    --debate-history '{full_history}' \
    --attacks-to-address '{attacks_on_c}'
```

### Step 8: Conclusion

토론 결과를 분석하여 합의점과 미합의점을 도출합니다.

## Output Format

```markdown
# Multiverse 토론 결과: {topic}

## 참여자
- **토론자 A** (Claude Opus) - {관점 α}
- **토론자 B** (GPT-5.2) - {관점 β}
- **토론자 C** (Gemini-3) - {관점 γ}

## 프로바이더별 특성

### Claude의 접근 방식
{Claude가 보여준 논증 스타일과 강점}

### GPT의 접근 방식
{GPT가 보여준 논증 스타일과 강점}

### Gemini의 접근 방식
{Gemini가 보여준 논증 스타일과 강점}

## 토론 하이라이트

### Round 1: 주장
{각 프로바이더의 초기 주장과 공격}

### Round 2: 방어
{방어와 반격}

### Round 3: 최종
{최종 입장 정리 및 합의 제안}

## 합의된 사항
1. {합의점 1}
2. {합의점 2}

## 미합의 사항 및 LLM별 입장

| 쟁점 | Claude | GPT | Gemini |
|------|--------|-----|--------|
| {쟁점1} | {입장} | {입장} | {입장} |

## 메타 분석: LLM 특성 비교

### 논증 스타일
- **Claude**: {특성}
- **GPT**: {특성}
- **Gemini**: {특성}

### 강점/약점
{각 LLM이 토론에서 보여준 강점과 약점 분석}

## 참고 자료
{토론 중 인용된 웹 검색 결과}
```

## Error Handling

### Provider Not Available
```python
if provider not in available_providers():
    # 대체 프로바이더로 폴백
    fallback_order = ["claude", "gpt", "gemini"]
    provider = next(p for p in fallback_order if p in available_providers())
```

### Timeout Handling
```python
# 각 phase별 타임아웃 설정
timeout_per_phase = {
    "initial_research": 180,  # WebSearch 포함
    "round_claim": 90,
    "round_claim_attack": 90,
    "prep_defense": 180,       # WebSearch 포함
    "round_defense": 90
}
```

## Notes

- **u-llm-sdk 필수**: 이 스킬을 사용하려면 u-llm-sdk가 설치되어 있어야 합니다
- **API 키 설정**: 각 프로바이더(Claude, Codex, Gemini)의 API가 설정되어 있어야 합니다
- **비용 고려**: 3개 프로바이더를 모두 사용하면 비용이 증가합니다
- **Claude 전용 모드**: --providers claude,claude,claude로 Claude만 사용 가능
- **기존 /debate와 차이**: /debate는 Claude 내부 에이전트만 사용, /debate-multiverse는 외부 LLM 호출
- **병렬 실행 필수**: initial_research와 prep_defense는 반드시 병렬로 실행해야 컨텍스트 오염 방지

## Prerequisites

```bash
# u-llm-sdk 설치
pip install u-llm-sdk

# 프로바이더 CLI 설정 확인
claude --version
codex --version  # or: openai --version
gemini --version  # or: google-genai --version
```
