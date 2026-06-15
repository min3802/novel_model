# Django / Frontend 번역 API handoff

이 문서는 새 Django backend와 새 frontend 담당자가 번역 API를 연결할 때 반드시 지켜야 할 핵심 contract만 짧게 정리한 인수인계 문서다. 상세 계약은 `docs/translation_api_contract.md`와 `docs/sample_v2_dual_draft_review_response.json`을 기준으로 확인한다.

## 1. 요약

- public endpoint는 `POST /api/translations/`를 사용한다.
- public request에는 `mode`를 넣지 않는다.
- 일반 사용자는 `mode`를 선택하지 않는다.
- backend 기본 pipeline은 내부적으로 `v2_dual_draft_review`를 사용한다.
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

## 3. Backend internal pipeline mode

backend 내부 기본값:

```txt
default pipeline = v2_dual_draft_review
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

response top-level 핵심 필드는 다음을 유지한다.

```txt
finalTranslation
deliveryStatus
userVisibleErrorCode
message
meaningDraft
ragEvidence
translationDecisions
authorReviewCards
```

frontend는 unknown field에 tolerant하게 동작한다. backend는 debug/internal field를 public response에 과도하게 노출하지 않는다.

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
docs/sample_v2_dual_draft_review_response.json
```

