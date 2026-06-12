# 번역 아키텍처 v2: direct 번역 + source-side RAG QA + patch + work memory

## 1. 배경과 결론

최근 gpt-5.4 기준으로 direct baseline, minimal pipeline, current pipeline을 비교했다. 실험 결과, RAG, terminology, glossary, review, inspection이 모두 꺼진 direct baseline이 가장 자연스럽고 과처리가 적은 번역으로 평가되었다.

반면 current pipeline은 RAG, terminology, glossary, review, inspection이 모두 활성화된 전체 경로였고, 추가 context layer가 번역 문장을 무겁게 만들거나 해석 과잉을 유발했다. 따라서 current full pipeline을 기본 번역 생성 경로로 사용하는 것은 적절하지 않다.

그러나 KURE 기반 한국어 RAG/annotation은 폐기할 대상이 아니다. 번역 프롬프트에 강제 주입하는 대신, 한국어 원문의 위험 표현을 찾고 번역 후 QA와 구간 패치에 사용하는 구조로 역할을 재정의한다.

## 2. 새 아키텍처 원칙

1. 기본 번역은 direct로 생성한다.
2. RAG는 번역 생성에 강제 주입하지 않고, 원문 기준 위험 탐지와 QA 체크리스트로 사용한다.
3. 자동 추출 terminology/glossary 후보는 locked가 아니라 suggest/review로 두고, 사용자 확정 항목만 locked로 저장한다.
4. reviewer가 전체 번역문을 재작성하는 구조를 기본값에서 내린다.
5. 문제 구간만 패치한다. 전체 재번역은 금지한다.
6. LangGraph는 여러 agent가 번역문을 계속 고치는 구조가 아니라, 조건부 workflow routing 구조로 재정의한다.

## 3. 구성 요소

### 3.1 DirectTranslator

역할:
- 기본 초벌 번역을 생성한다.
- 번역 생성 단계에서는 RAG context, terminology, glossary, review, inspection을 강제 주입하지 않는다.
- 입력은 원문, 대상 locale, 선택적 작품 메모리만 사용한다.

모델 라우팅:
- fast: 저비용/저지연 번역. 초안, 내부 검토, 대량 생성에 사용.
- premium: 고품질 문학 번역. 최종 번역, 유료 작업, 중요 회차에 사용.

출력:
- draft_translation
- model
- prompt_name
- created_at
- source_text_id

### 3.2 SourceSideAnalyzer

역할:
- 한국어 원문을 기준으로 KURE/RAG/annotation을 실행한다.
- 번역 프롬프트를 오염시키는 context 주입이 아니라, QA 위험 항목을 만든다.

탐지 대상:
- 관용어
- 비유 표현
- 고유명사
- 도메인 용어
- 문화 표현
- 직역 위험 표현
- 의미 오독 위험 구간

출력 예:
- risk_items
  - id
  - source_span
  - source_text
  - category
  - risk_level
  - reason
  - suggested_check
  - candidate_translations
  - evidence_source
  - confidence

중요한 변경:
- 이전의 prompt RAG context는 “번역문에 꼭 사용할 지시”였다.
- v2의 source-side risk item은 “번역 후 확인할 검수 항목”이다.

### 3.3 PostTranslationQA

역할:
- SourceSideAnalyzer가 만든 risk item이 번역문에서 적절히 처리되었는지 확인한다.
- 원문 span과 번역문 문단/문장을 alignment한다.
- 각 항목을 pass, warn, fail로 판정한다.

판정 기준:
- pass: 의미가 자연스럽게 보존되었고 대상어에서 어색하지 않다.
- warn: 크게 잘못되지는 않았지만 의미 손실, 직역, 톤 이탈 가능성이 있다.
- fail: 관용어/고유명사/도메인 용어/문화 표현이 오역되었다.

출력:
- qa_report
  - overall_status
  - issue_count
  - pass_count
  - warn_count
  - fail_count
  - issues
    - risk_item_id
    - source_span
    - translated_span
    - status
    - explanation
    - suggested_action

### 3.4 PatchProposer

역할:
- fail 또는 중요 warn 항목에 대해 문제 구간만 수정안을 제안한다.
- 전체 번역을 재작성하지 않는다.
- 수정안, 근거, 대안 표현을 함께 제공한다.

출력:
- patch_suggestions
  - issue_id
  - original_translation_span
  - proposed_replacement
  - rationale
  - alternatives
  - confidence
  - requires_user_confirmation

원칙:
- 자동 패치는 최소화한다.
- locked memory가 있는 항목은 우선한다.
- 사용자 확정 전에는 광범위한 톤 수정을 하지 않는다.

### 3.5 WorkMemory

역할:
- 작품 단위로 확정된 고유명사, 지명, 용어, 표현, 호칭, 문체 규칙을 저장한다.
- 사용자가 확정한 항목만 locked로 저장한다.
- 자동 추출 후보는 suggest 또는 review 상태로 두며, 번역문에 강제 주입하지 않는다.

필드 예:
- id
- work_id
- source_text
- target_text
- locale
- category
- status: locked | review | suggest | rejected
- source: user_confirmed | qa_patch | auto_candidate
- notes
- created_at
- updated_at

사용처:
- DirectTranslator에는 선택적으로 최소 메모리만 제공한다.
- SourceSideAnalyzer는 메모리와 원문 탐지 결과를 비교한다.
- PostTranslationQA는 locked 항목 위반을 중요 issue로 본다.

## 4. LangGraph 역할 재정의

기존 LangGraph는 여러 agent가 번역문을 점진적으로 고치는 인상이 강했다. v2에서 LangGraph는 번역문 재작성 구조가 아니라 workflow routing 구조로 재정의한다.

### 모드

#### fast
- 목표: 빠른 direct 번역
- 실행: DirectTranslator만 실행
- 출력: translation

#### premium
- 목표: 고품질 번역 + 위험 검수
- 실행: DirectTranslator -> SourceSideAnalyzer -> PostTranslationQA -> PatchProposer
- 출력: translation, qa_report, patch_suggestions

#### qa_only
- 목표: 이미 있는 번역문 검수
- 실행: SourceSideAnalyzer -> PostTranslationQA
- 출력: qa_report

#### patch_only
- 목표: QA 이슈에 대한 구간 수정안 생성
- 실행: PatchProposer
- 출력: patch_suggestions

## 5. MVP 범위

MVP에 포함:
1. direct translation
2. source-side RAG risk detection
3. post-translation QA report
4. issue-based patch suggestion
5. confirmed memory 저장

MVP에서 제외:
1. current full pipeline 기본값화
2. 미검증 terminology 강제 주입
3. reviewer 전체 재작성
4. Tavily 자동 검색
5. 장르별 glossary 대량 구축

## 6. 기존 기능 재활용 방향

살릴 것:
- KURE embedding
- idiom retriever
- annotation retriever
- manual idiom augmentation
- source span 기반 관용어 탐지
- terminology/entity 자동 후보 탐지
- 일관성 점검 이름/용어 로직

기본값에서 내릴 것:
- prompt RAG context 강제 주입
- 미확정 terminology locked 적용
- reviewer의 전체 재작성
- inspection을 모든 번역에 기본 수행
- 검증되지 않은 glossary 강제 사용

## 7. MVP 구현 순서

1. DirectTranslator 분리
   - 기본 direct 번역 경로를 명확히 분리한다.
   - fast/premium 모델 라우팅 메타데이터를 기록한다.

2. SourceSideAnalyzer 추가
   - 기존 RAG/annotation을 이용하되, 출력을 prompt context가 아닌 risk_items로 변환한다.

3. PostTranslationQA 추가
   - risk_items와 번역문을 비교해 pass/warn/fail 보고서를 만든다.

4. PatchProposer 추가
   - fail/warn 항목에 대해 구간 단위 수정안만 제안한다.

5. WorkMemory 추가
   - 사용자 확정 항목만 locked로 저장하는 구조를 만든다.

6. LangGraph routing 재정의
   - fast, premium, qa_only, patch_only 모드를 분기한다.

## 8. 데이터 계약 초안

### RiskItem

```json
{
  "id": "risk-001",
  "source_span": [120, 138],
  "source_text": "발목을 잡고",
  "category": "idiom",
  "risk_level": "high",
  "reason": "직역 시 의미 손실 가능",
  "suggested_check": "방해/부담 의미로 처리되었는지 확인",
  "candidate_translations": ["足を引っ張る"],
  "evidence_source": "idiom_rag",
  "confidence": "high"
}
```

### QAIssue

```json
{
  "risk_item_id": "risk-001",
  "source_span": [120, 138],
  "translated_span": [80, 96],
  "status": "warn",
  "explanation": "관용의 방해 의미가 약하게 반영됨",
  "suggested_action": "patch"
}
```

### PatchSuggestion

```json
{
  "issue_id": "issue-001",
  "original_translation_span": "...",
  "proposed_replacement": "...",
  "rationale": "원문의 관용 의미를 더 자연스럽게 반영",
  "alternatives": ["..."],
  "confidence": "medium",
  "requires_user_confirmation": true
}
```

### WorkMemoryItem

```json
{
  "id": "memory-001",
  "work_id": "novel-001",
  "source_text": "강현우",
  "target_text": "カン・ヒョヌ",
  "locale": "ko_ja",
  "category": "person_name",
  "status": "locked",
  "source": "user_confirmed",
  "notes": "임의 한자화 금지",
  "created_at": "2026-06-11T00:00:00Z",
  "updated_at": "2026-06-11T00:00:00Z"
}
```

## 9. 리스크

1. direct 번역의 자유도가 높아 작품 용어 일관성이 흔들릴 수 있다.
2. source span과 translation span alignment가 부정확하면 QA 판정이 잘못될 수 있다.
3. PatchProposer가 지나치게 공격적이면 번역의 자연스러움을 해칠 수 있다.
4. WorkMemory의 locked 항목이 잘못 확정되면 다음 회차까지 오염이 전파될 수 있다.
5. RAG를 생성 프롬프트에서 빼면 일부 관용어는 초벌에서 놓칠 수 있다. 대신 QA와 patch로 보정한다.

## 10. 성공 기준

- direct 번역 결과가 기본값으로 사용되며, 전체 재작성 reviewer가 기본 경로에서 빠진다.
- KURE/RAG/annotation은 prompt 주입이 아니라 source risk detection으로 사용된다.
- QA report가 pass/warn/fail을 명확히 제공한다.
- patch suggestion은 문제 구간만 수정한다.
- WorkMemory는 사용자 확정 항목만 locked로 저장한다.


## 11. 구현 상태

### implemented

- `TranslationMode` 추가
  - `legacy_full`
  - `direct_only`
  - `v2_direct_qa`
  - `qa_only`
- `DirectTranslator` wrapper 추가
- `SourceSideAnalyzer` 1차 skeleton 추가
  - idiom retriever
  - annotation retriever
  - terminology candidate를 `risk_items`로 변환
- `PostTranslationQA` 1차 skeleton 추가
  - simple paragraph/global string heuristic
  - `pass | warn | fail | unchecked` 상태 반환
- `PatchProposer` 1차 skeleton 추가
  - 자동 반영 없이 `patch_suggestions` 배열만 반환
- `TranslationPipeline`에 신규 실행 경로 추가
  - `run_direct_only`
  - `run_v2_direct_qa`
  - `run_qa_only`
- `translation_service.translate()`에 mode routing 추가
  - 기존 기본값은 `legacy_full` 유지

### stubbed

- source span ↔ translation span 정밀 alignment
- risk item별 정교한 target-side 판정 규칙
- entity / culture / slang 타입별 세분 QA 정책
- patch suggestion의 문장 단위 대체 구간 계산
- confirmed memory 저장/재사용 흐름

### not yet implemented

- LangGraph 기반 v2 orchestration 전환
- patch suggestion 사용자 승인 후 반영 경로
- episode/work memory persistence 정책 확정
- locale별 QA rule adapter
- direct translator 전용 경량 prompt 분기
# 2026-06-11 routing note

The v2 pipeline structure stays unchanged. This update only changes model routing.

## qualityMode routing

- default `qualityMode`: `standard`
- `fast` -> `gpt-5.4-nano`
- `standard` -> `gpt-5-mini`
- `quality` -> `gpt-5.4-mini`
- `baseline` -> `gpt-4.1-mini`

## request handling

- `qualityMode` is accepted by the translation request payload.
- `translationModel` or `model` may be used as an explicit allowlisted override.
- Unsupported model overrides fail validation instead of silently dropping to `gpt-4.1-mini`.

## metadata contract

All modes (`legacy_full`, `direct_only`, `v2_direct_qa`, `qa_only`) must emit:

- `mode`
- `quality_mode`
- `model_profile`
- `translation_model`
- `review_model`
- `model_override_used`
- `source_side_rag_enabled`
- `rag_enabled`
- `terminology_enabled`
- `glossary_enabled`
- `review_enabled`
- `inspection_enabled`

This metadata is the source of truth for answering "which model actually ran?" in outputs and saved artifacts.

# 2026-06-12 locale adherence note

## supported locales

- `ko_en_us` -> English (US)
- `ko_zh_cn` -> Simplified Chinese
- `ko_ja` -> Japanese
- `ko_th_th` -> Thai

## guard metadata

`direct_only`, `v2_direct_qa`, and `qa_only` now record locale-adherence metadata:

- `locale`
- `target_language_name`
- `locale_adherence_status`
- `korean_char_ratio`
- locale-specific target-script ratios
- `source_copy_suspected`
- `source_prefix_match_200`

The current guard is detection-only. It does not auto-retranslate yet.

### Translation Safety Checks

The locale-adherence metadata now wraps a more explicit `translation_safety` structure:

- `locale_adherence` verifies that the target language/script is actually present
- `source_copy` detects copied-source or severe source-language leakage
- `residual_hangul` tracks leftover Hangul spans and examples
- `proper_noun_transliteration` records possible Hangul proper-noun transliteration issues
- `overall_status` is the combined pass/warn/fail summary

Compatibility fields are still kept flat for existing callers:

- `korean_char_ratio`
- `target_script_ratio`
- `source_copy_suspected`
- `locale_adherence_status`

Interpretation:

- `locale_adherence` is a target-language maintenance check
- `source_copy` is a hard retry/hold condition
- `residual_hangul` is a separate warning/fail bucket for leftover Korean text
- `proper_noun_transliteration` is an issue bucket, not a full transliteration QA system
- Korean ratio is a supporting signal, not a single failure criterion
- `direct_only` uses the same strict retry and blocked-delivery policy as `v2_direct_qa`
- `retry_success` is `null` when retry was not attempted, `true` when retry succeeded, and `false` when retry failed
- `내부 디버그` QA rows stay in the metadata, but they are excluded from user-visible QA counts

## response contract

- `deliveryStatus = "deliverable"` means the translation may be shown as a normal success result.
- `deliveryStatus = "blocked_translation_safety"` means the translation must not be shown as a normal success result.
- `userVisibleErrorCode = "translation_safety_failed"` identifies the blocked safety case for UI/client handling.
- `finalTranslation` must be a non-empty string for deliverable success results.
- `finalTranslation = ""` is reserved for blocked safety responses, not successful delivery.
- Internal ratios such as `korean_char_ratio` and `target_script_ratio` remain in metadata only.

## UI/client policy

- `deliverable` responses render the translation panel normally.
- `blocked_translation_safety` responses render an error card instead of an empty translation panel.
- Client helpers should branch on `deliveryStatus` and `userVisibleErrorCode`; blocked results must not be treated as a normal translation success.
- Recommended blocked-state copy:
  - title: `번역 검증 실패`
  - body: `대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요.`
  - action: `다시 시도`
- `residual_hangul_status = warn` remains a QA warning, not a delivery block.
- `proper_noun_transliteration_status = warn` or `unchecked` remains a QA warning, not a delivery block.
- `내부 디버그` rows are diagnostic-only and do not count toward user-visible QA cards.

## operating policy

- Default operating candidate: `gpt-5-mini`
- Comparison candidate: `gpt-5.4-mini`
- Baseline/debug only: `gpt-4.1-mini`
- `fast/standard/quality/baseline` profiles are internal benchmark/admin routing structures, not public product tiers.

## fail policy draft

1. run the first translation
2. evaluate locale adherence
3. return normally on `pass`
4. on `fail`, retry once with a stricter locale instruction block on the same model
5. if retry still fails, mark the delivery as `blocked_translation_safety`
6. do not surface copied-source output as a normal successful translation

Planned retry policy:

- `source_copy_status = fail` or `locale_adherence_status = fail` should be eligible for a single same-model strict retry
- retry uses the same translation model with a stricter locale instruction block
- `residual_hangul_status = warn` should be treated as a QA issue, not an automatic retry trigger
- `proper_noun_transliteration_status = warn|unchecked` should be treated as a transliteration QA issue, not an automatic retry trigger
- `source_copy_status = fail`, `locale_adherence_status = fail`, or `source_copy_suspected = true` should trigger retry/hold logic
