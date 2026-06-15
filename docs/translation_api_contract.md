# 번역 API 계약서

이 문서는 현재 repository의 기존 React/frontend 구현이나 기존 backend 구현에 직접 붙이는 방법을 설명하는 문서가 아니다. 새 Django backend와 새 frontend가 같은 응답 구조를 기준으로 번역 기능을 연결하기 위한 API contract 문서다.

현재 repository의 코드는 동작과 필드 의미를 확인하기 위한 legacy/reference 자료로만 사용한다. 새 Django 구현에서는 기존 파일을 그대로 복사하지 말고, 이 문서의 request/response contract와 safety contract를 기준으로 serializer, service orchestration, frontend rendering을 다시 설계한다.

## 1. 목적

이 계약서는 한국 웹소설 번역/현지화 서비스의 번역 요청과 응답 구조를 안정적으로 고정하기 위한 문서다.

목표는 다음과 같다.

- 새 Django backend가 `POST /api/translations/` endpoint에서 어떤 request를 받고 어떤 response를 반환해야 하는지 정의한다.
- 새 frontend가 `deliveryStatus`, `finalTranslation`, `ragEvidence`, `translationDecisions`, `authorReviewCards`를 어떻게 해석해야 하는지 정의한다.
- `blocked_translation_safety` 상태에서 안전하지 않은 번역문이 화면에 렌더되지 않도록 계약을 명확히 한다.
- `authorReviewCards`는 우선 read-only 검수 정보로만 다루고, patch, WorkMemory, card action은 후속 기능으로 분리한다.

## 2. 번역 플로우

기본 플로우는 다음 순서를 따른다.

1. 사용자가 원문 `sourceText`를 입력한다.
2. 사용자가 목표 언어/지역 `targetLocale`을 선택한다.
3. backend가 기본 translation pipeline을 실행한다.
4. backend가 내부적으로 `v2_dual_draft_review` pipeline을 선택한다.
5. backend가 `finalTranslation`을 생성한다.
6. backend가 필요 시 `ragEvidence`, `translationDecisions`, `authorReviewCards`를 함께 반환한다.
7. frontend는 `deliveryStatus`를 먼저 확인하고, 상태에 따라 번역문과 검수 정보를 렌더링한다.

일반 사용자는 `mode`를 선택하지 않는다. public frontend도 `mode`를 보내지 않는다. backend 기본 pipeline은 내부적으로 `v2_dual_draft_review`를 사용한다.

## 3. Request contract

예상 endpoint:

```text
POST /api/translations/
```

요청 body는 JSON이다.

### 요청 필드

| 필드 | 타입 | 필수 여부 | 설명 |
| --- | --- | --- | --- |
| `workId` | string | 권장 | 작품 식별자다. 아직 작품 저장소와 연결되지 않은 초기 구현에서는 nullable 또는 생략 가능하게 둘 수 있다. |
| `episodeId` | string | 권장 | 회차 식별자다. 아직 회차 저장소와 연결되지 않은 초기 구현에서는 nullable 또는 생략 가능하게 둘 수 있다. |
| `sourceText` | string | 필수 | 번역할 원문 텍스트다. 빈 문자열이면 validation error로 처리한다. |
| `sourceLocale` | string | 권장 | 원문 locale이다. 예: `ko`. |
| `targetLocale` | string | 필수 | 목표 locale이다. 예: `ko_ja`, `ko_en`. |

`mode`는 public API request field가 아니다. 일반 frontend는 `mode`를 보내지 않는다.

### 요청 예시

```json
{
  "workId": "work_001",
  "episodeId": "ep_001",
  "sourceText": "긴 한국어 원문...",
  "sourceLocale": "ko",
  "targetLocale": "ko_ja"
}
```

## 4. Backend internal pipeline mode

`mode`는 사용자 노출용 옵션이 아니라 backend 내부 pipeline selector다.

반드시 지켜야 할 원칙:

- `mode`는 public API request field가 아니다.
- 일반 frontend는 `mode`를 보내지 않는다.
- 사용자는 `mode`를 선택하지 않는다.
- 새 Django backend는 기본값으로 `v2_dual_draft_review`를 사용한다.
- `direct_only`, `v2_direct_qa`, `qa_only`, `legacy_full` 등은 개발/테스트/관리자/internal override 용도로만 사용한다.
- 새 Django 구현에서도 public serializer와 internal pipeline selector를 분리하는 것을 권장한다.
- public response에도 `mode`를 필수 top-level field로 추가하지 않는다.
- 필요하다면 후속 debug/log/internal metadata에서 `executedMode` 같은 별도 이름을 고려할 수 있지만, 기본 frontend contract에는 포함하지 않는다.

## 5. Response contract

응답 body는 JSON이다. 새 Django backend는 최소한 아래 top-level fields를 유지해야 한다.

| 필드 | 타입 | 필수 여부 | 현재 구현 여부 | 설명 |
| --- | --- | --- | --- | --- |
| `finalTranslation` | string | 필수 | 현재 구현 | 최종 번역문이다. 단, `deliveryStatus="blocked_translation_safety"`이면 렌더링하지 않는다. |
| `deliveryStatus` | string | 필수 | 현재 구현 | 번역 결과 전달 상태다. |
| `userVisibleErrorCode` | string 또는 null | 필수 | 현재 구현 | 사용자에게 노출 가능한 오류 코드다. |
| `message` | string | 권장 | planned | 사용자 안내 문구다. 현재 구현에 없을 수 있으므로 frontend는 없어도 동작해야 한다. |
| `meaningDraft` | object | 필수 | 현재 구현 | 의미 기준 초안/의미 baseline 정보다. |
| `ragEvidence` | array | 필수 | 현재 구현 | 번역 후 검토용 evidence 목록이다. 번역 강제 지시가 아니다. |
| `translationDecisions` | array | 필수 | 현재 구현 | evidence를 기반으로 만든 검토 decision 목록이다. |
| `authorReviewCards` | array | 필수 | 현재 구현 | 작가/편집자에게 read-only로 보여줄 검수 카드 목록이다. |

frontend는 unknown field에 tolerant하게 동작해야 한다. backend는 internal/debug field를 과도하게 노출하지 않는다.

## 6. `deliveryStatus` 규칙

허용 enum value는 다음과 같다.

### `deliverable`

번역문을 기본 화면에 렌더링할 수 있는 상태다.

- `finalTranslation`을 표시한다.
- `ragEvidence`, `translationDecisions`, `authorReviewCards`가 비어 있을 수 있다.
- `authorReviewCards`가 있더라도 초기에는 read-only 참고 정보로 표시한다.

### `qa_warning`

번역문은 표시할 수 있지만 검토가 권장되는 상태다.

- `finalTranslation`을 표시할 수 있다.
- `authorReviewCards`가 있으면 P0/P1 중심으로 표시한다.
- frontend는 사용자에게 “검토 권장” 성격의 UI를 보여줄 수 있다.
- 이 상태가 자동 patch나 자동 수정 적용을 의미하지 않는다.

### `blocked_translation_safety`

번역 안전성 계약을 통과하지 못한 상태다.

반드시 지켜야 할 규칙:

- frontend는 `finalTranslation`을 렌더하지 않는다.
- backend는 `finalTranslation`을 빈 문자열로 반환하는 것을 권장한다.
- backend는 blocked 상태에서 `ragEvidence=[]`, `translationDecisions=[]`, `authorReviewCards=[]`를 반환한다.
- frontend는 blocked 상태에서 카드, evidence, patch preview를 만들거나 표시하지 않는다.
- 사용자는 안전 실패 안내 문구만 확인해야 한다.

## 7. `meaningDraft` contract

`meaningDraft`는 현재 구현된 compatibility field다. 장기적으로는 `SemanticLedger`가 별도 구조로 도입될 수 있지만, 이번 API contract에서는 `meaningDraft` top-level field를 유지한다.

현재 구현 필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `text` | string | 의미 baseline 또는 seed translation 기반 텍스트다. |
| `model` | string | 생성에 사용된 모델 또는 mock 모델 이름이다. |
| `purpose` | string | 보통 `semantic_baseline`이다. |
| `temperatureProfile` 또는 `temperature_profile` | string | 구현 계층에 따라 casing이 다를 수 있다. API serializer에서는 frontend contract에 맞춰 하나로 정리한다. 권장값은 `temperatureProfile`이다. |

권장:

- 새 Django API에서는 camelCase인 `temperatureProfile`로 직렬화한다.
- 내부 Python dataclass는 snake_case를 써도 되지만 API response contract는 frontend가 쓰는 casing으로 고정한다.

## 8. `ragEvidence` contract

`ragEvidence`는 번역 지시가 아니라 번역 후 검토 evidence다.

대표 필드:

| 필드 | 타입 | 현재 구현 여부 | 설명 |
| --- | --- | --- | --- |
| `id` | string | 현재 구현 | evidence 식별자다. |
| `sourceSpan` 또는 `source_span` | string | 현재 구현 | 원문에서 문제가 된 표현이다. API에서는 `sourceSpan` 권장. |
| `anchor` | string | 현재 구현 | 검색/매칭 기준 표현이다. |
| `evidenceType` 또는 `evidence_type` | string | 현재 구현 | `idiom`, `annotation`, `term`, `pragmatic` 등이다. API에서는 `evidenceType` 권장. |
| `literalMeaning` 또는 `literal_meaning` | string | 현재 구현 | 문자적 의미 또는 한국어 의미 설명이다. |
| `pragmaticFunction` 또는 `pragmatic_function` | string | 현재 구현 | 화용/문맥 기능이다. |
| `literalRisk` 또는 `literal_risk` | string | 현재 구현 | 직역 위험 설명이다. |
| `candidateTranslations` 또는 `candidate_translations` | array | 현재 구현 | 참고 번역 후보다. 강제 번역 지시가 아니다. |
| `confidence` | string | 현재 구현 | `low`, `medium`, `high`. |
| `userVisible` 또는 `user_visible` | boolean | 현재 구현 | 사용자에게 노출 가능한 evidence인지 여부다. |

주의:

- `ragEvidence`를 번역 prompt에 강제 주입하지 않는다.
- `candidateTranslations`는 자동 patch나 강제 번역어가 아니다.
- WorkMemory 저장 근거로 바로 쓰지 않는다.

## 9. `translationDecisions` contract

`translationDecisions`는 evidence를 바탕으로 backend가 생성한 검토 판단 목록이다. `authorReviewCards`보다 더 많은 항목을 담을 수 있다.

현재 구현 필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | decision 식별자다. |
| `sourceSpan` 또는 `source_span` | string | 검토 대상 원문 표현이다. |
| `sourceStart` 또는 `source_start` | number 또는 null | `sourceText`에서 exact match된 시작 offset이다. |
| `sourceEnd` 또는 `source_end` | number 또는 null | `sourceText`에서 exact match된 종료 offset이다. |
| `targetSpan` 또는 `target_span` | string | `finalTranslation`에서 exact match된 target 표현이다. |
| `targetStart` 또는 `target_start` | number 또는 null | target exact match 시작 offset이다. |
| `targetEnd` 또는 `target_end` | number 또는 null | target exact match 종료 offset이다. |
| `alignmentStatus` 또는 `alignment_status` | string | alignment 신뢰 상태다. |
| `meaningDraftSpan` 또는 `meaning_draft_span` | string | 기존 호환 필드다. |
| `vibeTranslationSpan` 또는 `vibe_translation_span` | string | 기존 호환 필드다. |
| `decisionType` 또는 `decision_type` | string | `preserved`, `risk_unresolved` 등이다. |
| `reason` | string | 판단 이유다. |
| `evidenceIds` 또는 `evidence_ids` | array | 연결된 evidence id 목록이다. |
| `authorNote` 또는 `author_note` | string | 작가에게 보여줄 질문/설명 후보 문구다. |
| `confidence` | string | `low`, `medium`, `high`. |
| `needsAuthorReview` 또는 `needs_author_review` | boolean | card 생성 후보인지 여부다. |
| `riskLevel` 또는 `risk_level` | string | 위험 수준이다. |
| `priority` | string | `P0`, `P1`, `P2`, `P3`. |
| `cardStatus` 또는 `card_status` | string | 초기값은 `pending`이다. |
| `unresolvedRisk` 또는 `unresolved_risk` | boolean | 미해결 위험 여부다. |
| `suggestedActions` 또는 `suggested_actions` | array | read-only 제안 action 문구다. 실제 action 실행이 아니다. |

권장 API casing:

- 새 Django response에서는 camelCase를 권장한다.
- legacy Python reference는 snake_case일 수 있다.

## 10. `authorReviewCards` contract

`authorReviewCards`는 frontend에서 read-only로 먼저 표시할 검수 카드 목록이다.

현재 구현 필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | card 식별자다. |
| `decisionId` 또는 `decision_id` | string | 연결된 decision id다. |
| `sourceSpan` 또는 `source_span` | string | 표시할 원문 표현이다. |
| `targetSpan` 또는 `target_span` | string | exact target match가 있을 때 표시할 target 표현이다. |
| `currentTranslation` 또는 `current_translation` | string | 현재 번역문 또는 관련 번역 context다. |
| `decisionLabel` 또는 `decision_label` | string | 카드 라벨이다. |
| `explanation` | string | 검토 이유 설명이다. |
| `authorQuestion` 또는 `author_question` | string | 작가/편집자에게 던지는 질문이다. |
| `options` | array | 미래 action 후보를 표현할 수 있지만, 현재는 read-only 표시용이다. |
| `recommendedOptionId` 또는 `recommended_option_id` | string 또는 null | 추천 선택지 id다. 자동 적용하지 않는다. |
| `evidenceSummary` 또는 `evidence_summary` | string | evidence 요약이다. |
| `patchSuggestion` 또는 `patch_suggestion` | object 또는 null | 현재는 `null`이어야 한다. |
| `priority` | string | `P0`, `P1`, `P2`, `P3`. |
| `status` | string | 초기값은 `pending`이다. |
| `suggestedActions` 또는 `suggested_actions` | array | read-only 제안이다. |
| `createdFromEvidenceIds` 또는 `created_from_evidence_ids` | array | card 생성 근거 evidence id 목록이다. |

### card 표시 규칙

- read-only 표시부터 시작한다.
- 기본 visible card는 P0/P1 중심으로 제한한다.
- result당 최대 5개 visible card를 기본값으로 둔다.
- `P2`/`P3` decision은 `translationDecisions`에는 남을 수 있지만 기본 card 노출 대상은 아니다.
- `needsAuthorReview=false`이면 card를 만들지 않는다.
- `confidence="low"`이면 card를 만들지 않는다.
- 같은 `sourceSpan + decisionType` 조합은 중복 card를 만들지 않는다.
- card action, patch, WorkMemory 저장은 아직 구현하지 않는다.

## 11. alignment 규칙

허용 `alignmentStatus` 값:

- `exact`
- `heuristic`
- `source_only`
- `target_unresolved`
- `unresolved`

현재 구현 기준:

- `sourceText`와 `finalTranslation`에서 모두 exact match되면 `alignmentStatus="exact"`다.
- source는 찾았지만 target을 찾지 못하면 `alignmentStatus="target_unresolved"`다.
- source 기준점이 없으면 target만 찾혀도 `alignmentStatus="unresolved"`로 처리한다.
- 이번 단계에서는 `heuristic`을 사용하지 않는다.

frontend 규칙:

- `alignmentStatus="exact"`일 때만 `targetSpan`, `targetStart`, `targetEnd` 기반 하이라이트를 신뢰한다.
- `target_unresolved` 또는 `unresolved`이면 UI는 하이라이트를 강제하지 않는다.
- `source_only` 또는 `heuristic`은 future extension으로 취급하고, 현재 UI에서는 보수적으로 표시한다.
- alignment가 불확실한 card에서 patch preview를 만들지 않는다.

## 12. 새 Django backend 책임

새 Django backend는 다음 책임을 가진다.

1. API serializer와 request validation을 구현한다.
   - `sourceText` 빈 문자열 방지
   - `targetLocale` 유효성 검증
   - public request에서 `mode`를 받지 않도록 serializer를 분리
2. translation service orchestration을 담당한다.
   - pipeline 실행
   - public 요청은 기본적으로 `v2_dual_draft_review`로 routing
   - 개발/테스트/관리자/internal override에서만 `mode` 기반 service routing 허용
   - mock/live 환경 분리
3. safety contract를 강제한다.
   - `blocked_translation_safety` 상태에서 `finalTranslation` 렌더링 금지 계약을 지킨다.
   - blocked 상태에서 `ragEvidence`, `translationDecisions`, `authorReviewCards`를 empty array로 직렬화한다.
4. response contract를 직렬화한다.
   - frontend contract에 맞춰 camelCase를 권장한다.
   - legacy snake_case 내부 구조를 그대로 노출하지 않도록 serializer에서 정리한다.
5. blocked status handling을 일관되게 처리한다.
   - `userVisibleErrorCode`
   - `message`
   - empty arrays
6. unknown/internal field를 frontend에 과도하게 노출하지 않는다.
   - debug prompt
   - internal retry context
   - raw model response
   - internal safety trace

## 13. 새 frontend 책임

새 frontend는 다음 책임을 가진다.

1. `deliveryStatus`를 먼저 확인하고 렌더링을 분기한다.
2. `blocked_translation_safety`이면 `finalTranslation`을 숨긴다.
3. `blocked_translation_safety`이면 `ragEvidence`, `translationDecisions`, `authorReviewCards`가 비어 있다고 가정하고, 검수 카드 UI를 표시하지 않는다.
4. `authorReviewCards`는 read-only로 표시한다.
5. `alignmentStatus="exact"`일 때만 target highlight를 신뢰한다.
6. unknown fields에 tolerant하게 parsing한다.
7. card action, patch, WorkMemory 기능은 후속 feature로 분리한다.
8. 일반 frontend는 `mode`를 request에 포함하지 않는다.

## 14. Legacy reference files

아래 파일들은 현재 동작과 테스트를 이해하기 위한 reference다. 새 Django backend에 그대로 복붙하지 않는다.

backend/reference:

- `backend/services/translation_service.py`
- `app/translation/v2_dual_draft_review.py`
- `app/translation/translation_pipeline.py`
- `app/translation/v2_pipeline.py`
- `tests/test_translation_v2_pipeline.py`
- `tests/test_translation_service.py`

frontend/reference:

- `frontend/features/translate/TranslateWorkspace.tsx`
- `frontend/features/translate/TranslateConnector.tsx`
- `frontend/features/translate/translationDisplay.ts`

reference 사용 원칙:

- 필드 의미와 safety contract를 확인하는 용도로만 사용한다.
- Django serializer, view, service layer는 새 구조에 맞춰 다시 작성한다.
- frontend 화면 설계는 새 UX 기준으로 다시 설계하되, 이 문서의 response contract를 유지한다.

## 15. 아직 구현하지 않는 것

다음 항목은 이번 contract의 범위 밖이다.

- UI card action
- `patch_only`
- WorkMemory
- SemanticLedger
- live alignment
- automatic patch apply
- author choice persistence
- author approval workflow
- card status mutation API

이 기능들은 후속 설계에서 별도 endpoint와 저장 계약을 만든 뒤 구현한다.

## 16. 구현 상태 구분

현재 구현된 것으로 볼 수 있는 항목:

- `v2_dual_draft_review` response shell
- `meaningDraft`
- `ragEvidence`
- `translationDecisions`
- `authorReviewCards`
- `deliveryStatus`
- `userVisibleErrorCode`
- `blocked_translation_safety` empty-array contract
- minimal exact alignment
- P0/P1 중심 visible card filtering
- backend default pipeline으로 `v2_dual_draft_review` 사용

planned 또는 후속 구현 항목:

- top-level `message`
- Django serializer 기준 camelCase 정규화
- WorkMemory 저장
- patch preview/action
- SemanticLedger
- card action persistence
- live alignment 또는 heuristic alignment
- public API와 분리된 admin/internal `mode` override endpoint 또는 option

## 17. 샘플 response

샘플 response는 별도 파일에 둔다.

- `docs/sample_v2_dual_draft_review_response.json`

이 샘플은 serializer contract 참고용이다. 실제 model output 품질 평가용 데이터가 아니며, `requirements.txt`, `outputs/*`, eval scripts와 무관하다.
