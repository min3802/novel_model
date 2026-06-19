# Django / Frontend 번역 API handoff


## 1. 요약

- public endpoint는 `POST /api/translations/`를 사용한다.
- public request에는 `mode`를 넣지 않는다.
- 일반 사용자는 `mode`를 선택하지 않는다.
- backend default pipeline internally uses `v3_literary_package` graph.
- `qualityMode` is the only public profile knob for quality/cost tuning; raw model names should not be shown in Django/Frontend UI.
- frontend는 `deliveryStatus`를 먼저 보고 렌더링을 분기한다.
- `authorReviewCards`는 초기에는 read-only로만 표시한다.
- patch 적용, WorkMemory 저장, RAG candidate 자동 저장은 하지 않는다.

## 2. Request contract

예상 public endpoint:

```txt
POST /api/translations/
```

public frontend가 보내는 request 예시는 다음 형태를 따른다.

```json
{
  "workId": "work_001",
  "episodeId": "ep_001",
  "sourceText": "긴 한국어 원문...",
  "sourceLocale": "ko",
  "targetLocale": "ko_ja"
}
```

중요 규칙:

- `sourceText`는 필수다.
- `targetLocale`은 필수다.
- `mode`는 public API field가 아니다.
- 일반 frontend는 `mode`를 보내지 않는다.
- `qualityMode` is optional; the backend default is `standard`.
- If Django/API sends it explicitly, use one of `fast`, `standard`, `quality`, or `baseline`.

## 3. Backend internal pipeline mode

backend 내부 기본값:

```txt
default pipeline = v3_literary_package graph
Django/API may omit `mode`; if it sends an explicit selector, send `v3_literary_package`.
```

`mode`의 성격:

- `mode`는 public API field가 아니다.
- `mode`는 internal/test/admin pipeline selector로만 유지한다.
- 새 Django 구현에서는 public serializer와 internal pipeline selector를 분리한다.

내부 override 후보:

```txt
direct_only
v2_direct_qa
v2_dual_draft_review
qa_only
legacy_full
```

## 4. Response contract

2026-06 리팩터로 응답을 v3 단일 파이프라인 기준의 "얇은 응답"으로 정리했다.
response top-level 핵심 필드는 다음과 같다.

```txt
country
locale
pipeline
finalTranslation
deliveryStatus
userVisibleErrorCode
message
translationRationale      # 왜 이렇게 번역했는지(개요/문체의도/직역·의역 비율/항목) — 챗봇·설명 패널용
readerEndnotes            # 한국 문화 표현에 대한 독자용 각주(kculture RAG → LLM 작성). 0~N개 가변
authorReviewCards         # 작가/편집자 read-only 검수 카드. 0~N개 가변
qaIssues                  # 검수 이슈. 0~N개 가변
metadata                  # 카운트/진단 요약
```

`internal`(그래프 트레이스, idiomNotes, annotationTrace 등 개발/검증용)은 **기본 응답에서 제외**된다.
필요할 때만 요청에 `"includeInternal": true`(또는 `"debugCaptureModelOutputs": true`)를 넣어 받는다. 화면에는 쓰지 않는다.

이전 응답에 있던 `meaningDraft`, `ragEvidence`, `translationDecisions`, `riskItems`,
`patchSuggestions`, `qaReport`, `reviewSummary`, `retrievalCount`, `workflow`(전체 중복) 등
**v3에서 항상 비어 있던 v2 호환 껍데기 필드는 제거됐다.** 검수 근거는 이제
`qaIssues`·`authorReviewCards`·`translationRationale`·`readerEndnotes`·`internal`에 들어 있다.

frontend는 unknown field에 tolerant하게 동작한다. backend는 debug/internal field를 public response에 과도하게 노출하지 않는다.

### readerEndnotes 항목 형태

```txt
noteId, sourceSpan(한국어 원문 표현), targetSpan(번역문 내 대응 표현, 없으면 ""),
category(예: korean_cultural_reference/food/custom), note(목표 독자 언어로 쓴 장면 맥락형 각주),
sourceChunkId, retrievalRefs, confidence(low|medium|high), targetSpanFound(bool)
```

`readerEndnotes`는 `finalTranslation`에 합쳐지지 않는다. 화면/다운로드 레이어가 각주로 렌더한다.
`blocked_translation_safety`/`blocked_translation_integrity`에서는 `readerEndnotes=[]`,
`authorReviewCards=[]`, `qaIssues=[]`, `finalTranslation=""`로 비워진다.

## 5. `deliveryStatus` 처리 규칙

```txt
deliverable
→ finalTranslation 표시

qa_warning
→ finalTranslation 표시
→ authorReviewCards 표시

blocked_translation_safety
→ finalTranslation 표시 금지
→ message 또는 userVisibleErrorCode 표시
→ ragEvidence=[]
→ translationDecisions=[]
→ authorReviewCards=[]
```

## 6. blocked safety contract

`blocked_translation_safety`이면 반드시 다음 값을 지킨다.

```txt
finalTranslation=""
ragEvidence=[]
translationDecisions=[]
authorReviewCards=[]
```

blocked 상태에서 frontend는 번역문, RAG evidence, decision, review card, patch preview를 표시하지 않는다.

## 7. Frontend 초기 연결 규칙

- `finalTranslation`이 표시의 중심이다.
- `deliveryStatus`를 먼저 확인한다.
- `blocked_translation_safety`이면 `finalTranslation`을 숨긴다.
- `authorReviewCards`는 read-only로 표시한다.
- card action은 아직 구현하지 않는다.
- patch 적용은 금지한다.
- WorkMemory 저장은 금지한다.
- RAG candidate 자동 저장은 금지한다.
- `alignmentStatus="exact"`일 때만 `targetSpan` 하이라이트를 신뢰한다.
- `target_unresolved` 또는 `unresolved`이면 하이라이트를 강제하지 않는다.

## 8. RAG의 역할

RAG는 번역 프롬프트를 강하게 조종하는 용도가 아니다.

RAG는 번역 후 다음 필드를 통해 검수 근거를 제공하는 evidence layer다.

```txt
ragEvidence
translationDecisions
authorReviewCards
```

`candidateTranslations`나 review-only terminology candidate를 locked glossary처럼 자동 저장하거나 강제 번역 지시로 사용하지 않는다.

## 9. 현재 금지 / 후순위 항목

다음 기능은 현재 API 연결 범위에서 구현하지 않는다.

- UI card action
- `patch_only`
- WorkMemory 저장
- SemanticLedger 본격 구현
- live alignment
- automatic patch apply
- author choice persistence
- RAG candidate 자동 저장
- review-only terminology를 locked glossary로 승격

## 10. Reference

현재 repository의 reference 파일이다. 새 Django backend에 그대로 복붙하지 말고 contract 확인용으로만 사용한다.

```txt
backend/services/translation_service.py
app/translation/v2_dual_draft_review.py
app/translation/translation_pipeline.py
app/translation/v2_pipeline.py
tests/test_translation_v2_pipeline.py
tests/test_translation_service.py
frontend/features/translate/TranslateWorkspace.tsx
frontend/features/translate/TranslateConnector.tsx
frontend/features/translate/translationDisplay.ts
docs/translation_api_contract.md
```

## Stable work identity for approved glossary hydration

For Django integration, the stable identity for a novel/work is the Django work
DB id. Django must pass one of these fields on every translation request:

- `workId`: preferred when the Django numeric work id is already available.
- `canonicalWorkKey`: optional canonical string key for non-Django batch/test
  callers that need a stable find-or-create identity before a numeric work id
  exists.

The model server hydrates approved glossary from `glossary_entries` by
`workId + targetLocale`. This means `translatorBrief.glossary`,
`editorEvidence.approvedGlossary`, and `rationaleEvidence.approvedGlossary`
must all come from the same approved glossary rows. Pending
`glossary_candidates` are review queue data only and must not be injected into
the translator prompt as locked glossary.

Batch/test callers may omit both fields only as a fallback; that path creates a
new work per run and therefore cannot validate long-term glossary stability.
For batch eval, prefer `--work-id <django-work-id>` or
`--work-key <stable-key>` plus `--seed-approved-glossary` when smoke-testing
approved glossary behavior.
