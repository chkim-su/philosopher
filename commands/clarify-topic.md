---
name: clarify-topic
description: 모호한 토론 주제를 명확하고 구체적인 질문으로 변환
---
# Clarify Topic Command

토론 주제의 품질을 분석하고 사용자와 상호작용하여 명확화합니다.
**기술적 의사결정 토론에 최적화되어 있습니다.**

## Usage

```
/clarify-topic [주제]
```

예시:
- `/clarify-topic React vs Vue`
- `/clarify-topic TDD`
- `/clarify-topic 어떤 아키텍처가 좋을까`

## Execution Protocol

### Step 1: 주제 분석

입력된 주제를 4차원으로 분석합니다:

| 차원 | 가중치 | 평가 기준 |
|-----|-------|----------|
| 명확성 (Clarity) | 25% | 핵심 개념 명시 여부 |
| 토론가능성 (Debatability) | 25% | 찬반/비교 가능 여부 |
| 구체성 (Specificity) | 20% | 키워드 수, 맥락 존재 |
| 실행가능성 (Actionability) | 30% | 의사결정 가능 여부 |

### Step 2: 기술 토론 감지

다음 패턴이 있으면 기술 토론으로 분류:
- 프레임워크/언어: React, Vue, TypeScript, Python, Rust...
- 아키텍처: microservice, monolith, serverless...
- 방법론: TDD, Agile, Scrum...
- 비교 패턴: "A vs B", "A or B", "도입 여부"

### Step 3: 품질 부족 시 명확화 질문

#### 기술 토론 - 구체성 부족

```
AskUserQuestion(
  questions: [
    {
      question: "'{topic}'에 대해 더 구체적으로 알려주세요. 어떤 프로젝트/맥락에서 토론하나요?",
      header: "프로젝트 맥락",
      options: [
        {label: "신규 프로젝트", description: "처음부터 기술 스택 선택"},
        {label: "기존 프로젝트 전환", description: "레거시에서 마이그레이션"},
        {label: "특정 기능 구현", description: "특정 기능에 대한 기술 선택"},
        {label: "팀/조직 표준화", description: "팀 전체 표준 결정"}
      ],
      multiSelect: false
    },
    {
      question: "어떤 기준으로 비교/결정하고 싶으신가요?",
      header: "평가 기준",
      options: [
        {label: "성능/확장성", description: "속도, 처리량, 스케일링"},
        {label: "개발 생산성", description: "개발 속도, 러닝커브, DX"},
        {label: "유지보수성", description: "코드 품질, 테스트 용이성"},
        {label: "비용/리소스", description: "인프라 비용, 인력 비용"}
      ],
      multiSelect: true
    }
  ]
)
```

#### 비교 대상 부족

```
AskUserQuestion(
  questions: [
    {
      question: "'{topic}'과 비교할 대안이 있나요?",
      header: "비교 대상",
      options: [
        {label: "특정 대안 있음", description: "구체적인 비교 대상이 있음"},
        {label: "최적 방법 탐색", description: "여러 옵션 중 최선을 찾고 싶음"},
        {label: "도입 vs 미도입", description: "채택 여부 자체를 결정"},
        {label: "현 상태 유지 vs 변경", description: "변경의 가치 평가"}
      ],
      multiSelect: false
    }
  ]
)
```

#### 일반 토론 - 토론가능성 부족

```
AskUserQuestion(
  questions: [
    {
      question: "'{topic}'을 토론 형태로 바꾸면 어떨까요?",
      header: "토론 형식",
      options: [
        {label: "찬반 토론", description: "~해야 하는가? 형태"},
        {label: "비교 토론", description: "A vs B 어느 것이 더 나은가?"},
        {label: "영향 분석", description: "~이 미치는 영향은?"},
        {label: "원인 분석", description: "~의 원인과 해결책은?"}
      ],
      multiSelect: false
    }
  ]
)
```

### Step 4: 주제 재구성

사용자 응답을 기반으로 주제를 재구성:

```thinking
사용자 선택:
- 프로젝트 맥락: {context}
- 평가 기준: {criteria}
- 비교 대상: {comparison}

원본 주제: {topic}

재구성 전략:
- 맥락 통합: "{topic} in {context}"
- 기준 명시: "considering {criteria}"
- 비교 형식: "{topic} vs {alternative}"
```

### Step 5: 결과 출력

명확화된 주제를 구조화하여 반환:

```
## Clarified Topic

**원본**: {original_topic}
**명확화**: {clarified_topic}

### 적용된 명확화
- 맥락: {context}
- 평가 기준: {criteria}
- 변환 유형: {transformation}

### 품질 점수
- 이전: {original_score}
- 이후: {new_score}

---
이 주제로 `/debate {clarified_topic}` 실행하시겠습니까?
```

## Examples

### 예시 1: 모호한 기술 비교

**Input**: `/clarify-topic React vs Vue`

**분석**: 구체성 부족 (어떤 맥락? 어떤 기준?)

**질문**:
1. 프로젝트 맥락: "신규 프로젝트"
2. 평가 기준: ["개발 생산성", "유지보수성"]

**Output**: "신규 대시보드 프로젝트에서 React vs Vue: 개발 생산성과 유지보수성 관점"

### 예시 2: 단순 키워드

**Input**: `/clarify-topic TDD`

**분석**: 명확성, 토론가능성 부족

**질문**:
1. 토론 형식: "도입 vs 미도입"
2. 프로젝트 맥락: "기존 프로젝트 전환"

**Output**: "레거시 프로젝트에 TDD를 도입해야 하는가? - 비용 대비 효과 분석"

### 예시 3: 너무 광범위

**Input**: `/clarify-topic 어떤 아키텍처가 좋을까`

**분석**: 구체성 부족

**질문**:
1. 비교 대상: "마이크로서비스 vs 모놀리식"
2. 평가 기준: ["확장성", "운영 복잡성"]

**Output**: "스타트업 MVP에서 마이크로서비스 vs 모놀리식: 확장성과 운영 복잡성 트레이드오프"
