# 모델 코드 기능 설명 및 Live 테스트 가이드

작성 일시: 2026-06-04  
대상 프로젝트: w.Lighter Streamlit/API MVP  
목적: 모델 관련 코드가 어떤 기능을 담당하는지 설명하고, 실제 OpenAI API를 사용한 live 모델 테스트 방법을 정리한다.

---

## 1. 전체 구조 요약

현재 모델 테스트 대상은 크게 5개 기능이다.

| 테스트 ID | 기능 | 주요 코드 |
| --- | --- | --- |
| `TST-TRANS-001` | 한국어 원문을 일본어로 번역하고 구조화된 workflow 반환 | `api_server.py`, `ko_locale_pipeline/pipeline.py`, `translator.py`, `reviewer.py`, `inspector.py` |
| `TST-TRANS-002` | 중국 문화권 민감 표현 검수 및 완화 제안 | `inspector.py`, `translator.py`, `api_server.py` |
| `TST-TRANS-003` | 반복 등장 인물/고유명사 일관성 확인 | `pipeline.py`, `retriever.py`, `translator.py` |
| `TST-CHAT-001` | 번역 결과에 대한 챗봇형 수정 제안 | `api_server.py`, `chatbot.py` |
| `TST-GDE-001` | 국가/장르 기반 현지화 가이드 생성 | `api_server.py` |
| `TST-IMG-001` | 표지 이미지 생성 요청 | `api_server.py` |
| `TST-IMG-002` | 인물 관계도 이미지 생성 요청 | `api_server.py` |

테스트는 두 종류로 나뉜다.

1. **mock 테스트**
   - 실제 OpenAI API 호출 없음
   - 비용 없음
   - 구조, 응답 필드, 안전장치, acceptance 기준 확인용

2. **live 테스트**
   - 실제 OpenAI API 호출
   - 번역/챗봇/가이드/이미지 모델의 실제 동작 확인
   - API 키와 비용 발생 가능성 필요

---

## 2. 코드별 기능 설명

### 2.1 `api_server.py`

역할: 프론트엔드 또는 테스트 스크립트가 호출하는 **중앙 API 레이어**다.  
모델 파이프라인을 직접 실행하고, JSON API 형태로 결과를 반환한다.

주요 기능:

- 작품/회차 관리용 임시 API
  - `works_list`
  - `work_create`
  - `work_update`
  - `work_delete`
  - `episodes_list`
  - `episode_create`

- 모델 설정 및 mock/live 전환
  - `_config(locale)`
  - `_is_mock_mode()`
  - 환경 변수 `WLIGHTER_MOCK_MODE`가 `true`면 mock, `false`면 live로 동작한다. (미설정 시 기본값은 `false`=live)

- 번역 API
  - `translate(payload)`
  - 입력:
    - `sourceText`
    - `targetCountry`
    - 선택: `workId`
  - 처리:
    1. 대상 국가를 locale로 변환
    2. 한국어 원문인지 확인
    3. `KoLocalePipeline.run_with_inspection()` 실행
    4. 최종 번역, 검수 요약, retrieval 결과, workflow 반환
  - 관련 테스트:
    - `TST-TRANS-001`
    - `TST-TRANS-002`
    - `TST-TRANS-003`

- 챗봇 검수 API
  - `inspect_chat(payload)`
  - 입력:
    - `targetCountry`
    - `question`
    - `sourceText`
    - `currentTranslation`
    - 선택: 이전 workflow
  - 처리:
    1. 현재 번역/검수 문맥 정리
    2. `ChatbotAgent.reply()` 호출
    3. 수정 제안과 사용자 확인 필요 여부 반환
  - 관련 테스트:
    - `TST-CHAT-001`

- 현지화 가이드 API
  - `guide(payload)`
  - 입력:
    - `targetCountry`
    - `genre`
    - `synopsis`
  - 처리:
    - 국가별 플랫폼, 문화 주의사항, 작성 방향, 태그, HTML 리포트 생성
  - 관련 테스트:
    - `TST-GDE-001`

- 이미지 생성 API
  - `cover_image(payload)`
  - `relation_image(payload)`
  - `generate_image(prompt)`
  - 처리:
    1. mock 모드면 `mock_image` 반환
    2. live 모드면 OpenAI Images API 호출
    3. 노출/성적 요청 등 unsafe 요청은 `refusal` 반환
  - 관련 테스트:
    - `TST-IMG-001`
    - `TST-IMG-002`

- HTTP 엔드포인트
  - `POST /api/translate`
  - `GET /api/works/{workId}/episodes/{episodeId}/translations`
  - `GET /api/translations/{translationId}`
  - `DELETE /api/translations/{translationId}`
  - `POST /api/translations/{translationId}/chat`
  - `GET /api/translations/{translationId}/chat`
  - `POST /api/translations/{translationId}/apply-chat-suggestion`
  - `POST /api/inspect-chat`
  - `POST /api/guide`
  - `POST /api/works/{workId}/cover-plan`
  - `POST /api/generate-cover-image`
  - `POST /api/generate-relation-image`

주의:

- 현재 서버 저장소는 인메모리 방식이라 재시작하면 작품/회차 데이터가 초기화된다.
- `OPENAI_IMAGE_MODEL` 기본값은 코드상 `gpt-image-2`다. 실제 live 이미지 테스트 전에는 `.env`에서 공식 지원 모델명으로 명시하는 것을 권장한다.

예:

```env
OPENAI_IMAGE_MODEL=gpt-image-1.5
```

---

### 2.2 `ko_locale_pipeline/config.py`

역할: 모델 파이프라인의 설정값을 관리한다.

주요 설정:

- `locale`
  - `ko_ja`, `ko_en_us`, `ko_zh_cn`, `ko_th_th` 등 대상 문화권
- `embedding_model`
  - ???: `nlpai-lab/KURE-v1`
  - non-mock retrieval uses the local `sentence-transformers` backend unless the model name starts with `text-embedding-`.
  - The previous OpenAI embedding cache under `data/embedding_cache/` is generated data and can be regenerated.
- `translation_model`
  - 기본값: `gpt-5.4-mini`
- `review_model`
  - 기본값: `gpt-5.4-mini`
- `top_k`
  - RAG 검색 결과 개수
- `mock`
  - `True`면 API 호출 없이 deterministic mock 응답 사용

관련 함수:

- `resolved_resources()`
- `resolved_rag_dataset_path()`
- `resolved_annotation_dataset_path()`
- `resolved_cultural_terms_path()`
- `resolved_embedding_cache_dir()`

---

### 2.3 `ko_locale_pipeline/openai_client.py`

역할: OpenAI API 클라이언트를 생성한다.

주요 기능:

- `load_api_key()`
  - 환경 변수 `OPENAI_API_KEY`를 읽는다.

- `get_openai_client()`
  - API 키가 없으면 예외 발생
  - mock 모드가 아닌 live 테스트에서 필요하다.

live 테스트 전 필수 조건:

```env
OPENAI_API_KEY=sk-...
```

---

### 2.4 `ko_locale_pipeline/pipeline.py`

역할: 번역 모델 테스트의 **전체 실행 흐름**을 묶는 오케스트레이터다.

핵심 클래스:

- `KoLocalePipeline`
- `KoJaPipeline`

주요 함수:

- `run(source_text)`
  - 기본 번역 파이프라인 실행

- `run_with_inspection(...)`
  - 테스트에서 주로 사용하는 전체 workflow 실행
  - 처리 순서:
    1. RAG 검색
    2. 문화 주석/annotation 검색
    3. 문화권 lexicon 매칭
    4. 번역 초안 생성
    5. 번역 리뷰
    6. 독립 검수
    7. 최종 번역 선택

반환되는 주요 workflow 필드:

- `source_text`
- `retrievals`
- `annotation_matches`
- `cultural_matches`
- `draft`
- `inspection`
- `reviewed_translation`

---

### 2.5 `ko_locale_pipeline/retriever.py`

역할: RAG 검색을 수행한다.

주요 기능:

- RAG 데이터셋 로드
- embedding 생성
- embedding cache 사용
- 입력 원문과 관련 있는 문화/표현 카드 검색

핵심 클래스:

- `DenseRetriever`
- `MockEmbeddingBackend`
- `OpenAIEmbeddingBackend`

mock/live 차이:

- mock 모드:
  - `MockEmbeddingBackend`로 비용 없이 검색 구조 확인
- live 모드:
  - OpenAI embedding 모델로 실제 embedding 생성 가능

관련 테스트:

- `tests.test_k_culture_rag`
- `tests.test_retriever_anchor_priority`
- `TST-TRANS-*`

---

### 2.6 `ko_locale_pipeline/annotation_retriever.py`

역할: 한국 문화 주석 카드 기반 검색을 담당한다.

주요 목적:

- 한국어 원문 속 문화 고유 표현을 찾는다.
- 번역 모델에게 어떤 문화적 설명이 필요한지 제공한다.

사용 데이터:

- `data/annotation_rag/k_culture_annotation_cards.json`

관련 문서:

- `docs/k_culture_annotation_handoff.md`
- `docs/rag_normalized_schema.md`

---

### 2.7 `ko_locale_pipeline/cultural_lexicon.py`

역할: 문화권별 민감 표현, 고유 표현, 현지화 주의사항을 lexicon 형태로 매칭한다.

주요 목적:

- 단순 RAG뿐 아니라 규칙 기반 문화 키워드도 함께 탐지한다.
- 번역/검수 모델에 추가 context를 제공한다.

관련 테스트:

- `tests.test_cultural_lexicon`

---

### 2.8 `ko_locale_pipeline/translator.py`

역할: 실제 번역 초안을 생성한다.

핵심 클래스:

- `Translator`
- `TranslationDraft`

mock 모드:

- `_mock_translation(source_text)`에서 테스트 문장별 고정 응답 반환
- 예:
  - 일본어 소나기 문장
  - 중국어 폭력 표현 완화 문장
  - 태국어 김첨지 고유명사 반복 문장

live 모드:

- OpenAI Responses API 호출
- JSON schema 기반 structured output 요청
- 반환 필드:
  - `translation`
  - `strategy`
  - `rationale`
  - `reference_ids`
  - `translation_decisions`

관련 테스트:

- `TST-TRANS-001`
- `TST-TRANS-002`
- `TST-TRANS-003`

---

### 2.9 `ko_locale_pipeline/reviewer.py`

역할: 번역 초안을 검토하고 수정 제안을 만든다.

핵심 클래스:

- `Reviewer`
- `ReviewResult`

주요 기능:

- 번역 초안 검토
- RAG 근거와 문화권별 규칙 반영 여부 확인
- 필요하면 수정 번역 반환

반환 필드 예:

- `overall_quality`
- `issues`
- `revised_translation`
- `review_note`

---

### 2.10 `ko_locale_pipeline/inspector.py`

역할: 번역 결과를 독립적으로 검수한다.

핵심 클래스:

- `InspectionAgent`
- `InspectionResult`
- `ContextAnalysis`
- `ProblematicSpan`
- `InspectionSuggestion`

주요 기능:

- 문맥 분석
- 문화권별 위험 요소 탐지
- 문제 span 표시
- 수정 제안 반환
- 최종 action 제안

주요 action:

- `NOTE`
- `ADAPT`
- `REVISE`
- `BLOCK`

mock 예시:

- 중국어 대상이고 원문에 `뺨`, `후려갈겼다`가 있으면 폭력 수위 완화 제안을 반환한다.

관련 테스트:

- `TST-TRANS-002`

---

### 2.11 `ko_locale_pipeline/chatbot.py`

역할: 번역 결과에 대한 사용자의 후속 질문에 답하고 수정안을 제안한다.

핵심 클래스:

- `ChatbotAgent`
- `ChatbotReply`
- `ChatMessage`

주요 기능:

- 번역 표현 설명
- 자연스러운 대체 번역 제안
- 사용자가 애매하게 질문하면 추가 정보 요청
- 번역과 무관한 질문은 거절
- 수정 확정이 필요한 경우 `needs_user_confirmation=True` 반환

테스트 예:

- 일본어 `愛してる`가 너무 직접적인 경우 `好きです` 제안

관련 테스트:

- `TST-CHAT-001`

---

### 2.12 `ko_locale_pipeline/terminology.py`

Role: lightweight noun/proper-noun terminology hints and consistency rows.

Main scope:

- Suggest noun/proper-noun candidates from source text.
- Render confirmed `terminology`/`terms` rows into the translator prompt.
- Avoid enforcing verbs, adjectives, and normal sentence-level wording variation.

Use path:

- `api_server.translate()` accepts explicit terminology rows and also returns suggested terminology candidates.

---

### 2.13 `ko_locale_pipeline/terminology.py`

역할: 작품 메모리 저장, 병합, 요약을 담당한다.

주요 기능:

- `terminology_rows_for_locale`
- `render_terminology_context`
- `merge_terminology`
- `render_terminology_context`

테스트 목적:

- 반복 등장 인물, 설정, 관계 정보를 다음 회차 번역에 반영할 수 있는 구조를 확인한다.

관련 테스트:

- `tests.test_terminology`
- `tests.test_agent_workflow`

---

### 2.14 `ko_locale_pipeline/consistency_checker.py`

역할: 번역 후 고유명사/용어 일관성을 검사한다.

주요 기능:

- 작품 메모리의 `glossary`, `terms` 항목을 확인한다.
- 원문에 등장한 source가 번역문에서 expected target으로 유지되는지 검사한다.
- 누락 시 `glossary_mismatch` 이슈를 반환한다.
- `api_server.translate()` 결과의 `workflow.consistency`에 검사 결과가 포함된다.

현재 MVP 기준:

- 확정 glossary의 불일치는 `HIGH`
- 권장/제안 glossary의 불일치는 `MEDIUM`

관련 테스트:

- `tests.test_model_feature_backlog`

---

### 2.15 `scripts/run_live_model_smoke.py`

역할: 모델 관련 기능을 한 번에 검증하는 스모크 테스트 스크립트다.

실행 대상:

- 번역 3건
- 챗봇 1건
- 가이드 1건
- 이미지 2건

주요 함수:

- `_translation_case`
- `_chat_case`
- `_guide_case`
- `_cover_image_case`
- `_relation_image_case`
- `run(live, include_images)`
- `write_markdown`

출력:

- JSON 결과 파일
- Markdown 리포트
- 콘솔 요약 JSON

기본 동작:

- `--mock` 없으면 live 모드
- `--include-images` 없으면 이미지 테스트 skip

---

### 2.15 `tests/test_model_acceptance_from_docs.py`

역할: 문서 기반 acceptance 기준을 코드 테스트로 고정한다.

검증 항목:

- 한국어 원문 번역 결과가 구조화되어 있는지
- 비한국어 원문을 차단하는지
- 챗봇이 일본어 표현을 자연스럽게 제안하는지
- 애매한 질문/무관한 질문을 처리하는지
- 이미지 mock 생성과 unsafe refusal이 동작하는지
- 현지화 가이드에 필수 섹션이 있는지

---

## 3. Live 모델 테스트 전 준비

### 3.1 `.env` 확인

프로젝트 루트에 `.env`가 있어야 한다.

필수:

```env
OPENAI_API_KEY=sk-...
WLIGHTER_MOCK_MODE=false
```

이미지 테스트까지 할 경우 권장:

```env
OPENAI_IMAGE_MODEL=gpt-image-1.5
```

비용 절약 우선이면:

```env
OPENAI_IMAGE_MODEL=gpt-image-1-mini
```

주의:

- `.env`는 `.gitignore`에 포함되어 있으므로 커밋하지 않는다.
- 이미지 생성은 실제 비용이 발생할 수 있다.

---

## 4. 테스트 실행 순서

### 4.1 1단계: mock 전체 테스트

목적:

- 비용 없이 전체 모델 테스트 경로가 정상인지 확인한다.
- 이미지 테스트까지 포함해 7개 항목을 모두 실행한다.

명령:

```powershell
python scripts\run_live_model_smoke.py --mock --include-images --json-out docs\mock_model_smoke_results.json --md-out docs\mock_model_smoke_report.md
```

성공 기준:

```json
{"live": false, "include_images": true, "passed": 7, "executed": 7, "skipped": 0, "total": 7}
```

생성 파일:

- `docs/mock_model_smoke_results.json`
- `docs/mock_model_smoke_report.md`

---

### 4.2 2단계: 회귀 테스트

목적:

- 모델 기능뿐 아니라 RAG, lexicon, agent workflow, work memory가 깨지지 않았는지 확인한다.

명령:

```powershell
python -m unittest tests.test_model_acceptance_from_docs tests.test_k_culture_rag tests.test_agent_workflow tests.test_cultural_lexicon tests.test_retriever_anchor_priority tests.test_terminology
```

신규 기능 저장/일관성/표지 기획까지 포함하려면:

```powershell
python -m unittest tests.test_model_feature_backlog tests.test_model_acceptance_from_docs tests.test_k_culture_rag tests.test_agent_workflow tests.test_cultural_lexicon tests.test_retriever_anchor_priority tests.test_terminology
```

성공 기준:

```text
Ran 27 tests
OK
```

현재 확인된 결과:

```text
Ran 27 tests in 14.142s
OK
```

---

### 4.3 3단계: live 테스트 — 이미지 제외

목적:

- 실제 OpenAI API로 번역, 챗봇, 가이드 모델 경로를 확인한다.
- 이미지 비용을 피하기 위해 이미지 2건은 skip한다.

명령:

```powershell
python scripts\run_live_model_smoke.py
```

성공 기준:

```json
{"live": true, "include_images": false, "passed": 5, "executed": 5, "skipped": 2, "total": 7}
```

정상 skip:

- `TST-IMG-001`
- `TST-IMG-002`

생성 파일:

- `docs/live_model_smoke_results.json`
- `docs/live_model_smoke_report.md`

주의:

- 이 명령은 기본 출력 파일을 덮어쓴다.
- 재검증용으로 따로 저장하려면 아래처럼 파일명을 바꾼다.

```powershell
python scripts\run_live_model_smoke.py --json-out docs\live_model_smoke_review_results.json --md-out docs\live_model_smoke_review_report.md
```

---

### 4.4 4단계: live 테스트 — 이미지 포함

목적:

- 실제 이미지 생성 모델까지 포함해 최종 7개 항목을 검증한다.

명령:

```powershell
python scripts\run_live_model_smoke.py --include-images --json-out docs\live_model_smoke_with_images_results.json --md-out docs\live_model_smoke_with_images_report.md
```

성공 기준:

```json
{"live": true, "include_images": true, "passed": 7, "executed": 7, "skipped": 0, "total": 7}
```

생성 파일:

- `docs/live_model_smoke_with_images_results.json`
- `docs/live_model_smoke_with_images_report.md`

주의:

- 실제 이미지 생성 API 비용이 발생할 수 있다.
- `OPENAI_IMAGE_MODEL` 값이 실제 지원되는 모델인지 확인해야 한다.
- 이미지 모델 사용 권한 또는 organization verification이 필요할 수 있다.

---

## 5. 결과 파일 읽는 방법

### 5.1 JSON 결과

예:

```json
[
  {
    "id": "TST-TRANS-001",
    "category": "translation",
    "status": "pass",
    "elapsed_sec": 27.47,
    "output": {
      "locale": "ko_ja",
      "retrievalCount": 3,
      "finalTranslation": "...",
      "inspection": {}
    }
  }
]
```

확인 포인트:

- `status`
  - `pass`: 성공
  - `fail`: 응답은 왔지만 기준 미달
  - `error`: 실행 중 예외
  - `skipped`: 의도적으로 건너뜀

- `elapsed_sec`
  - 모델 호출 시간

- `output`
  - 각 테스트별 실제 반환값

---

### 5.2 Markdown 리포트

예:

```markdown
| Test ID | Category | Status | Seconds | Summary |
| --- | --- | --- | ---: | --- |
| TST-TRANS-001 | translation | pass | 27.47 | ... |
```

용도:

- 제출용 요약
- 테스트 결과 보고서에 붙여넣기
- 실패 항목 빠른 확인

---

## 6. 실패 시 점검 순서

### 6.1 `OPENAI_API_KEY is required unless mock=True`

원인:

- live 모드인데 `.env`에 `OPENAI_API_KEY`가 없거나 로드되지 않음

해결:

```env
OPENAI_API_KEY=sk-...
```

그 다음 다시 실행:

```powershell
python scripts\run_live_model_smoke.py
```

---

### 6.2 이미지 테스트만 실패

가능 원인:

- `OPENAI_IMAGE_MODEL` 모델명이 잘못됨
- 이미지 모델 권한 없음
- organization verification 미완료
- 이미지 생성 비용/한도 문제

해결:

1. `.env` 확인

```env
OPENAI_IMAGE_MODEL=gpt-image-1.5
```

2. 이미지 제외 live 테스트가 먼저 통과하는지 확인

```powershell
python scripts\run_live_model_smoke.py
```

3. 그 다음 이미지 포함 실행

```powershell
python scripts\run_live_model_smoke.py --include-images --json-out docs\live_model_smoke_with_images_results.json --md-out docs\live_model_smoke_with_images_report.md
```

---

### 6.3 `fail`이 나오지만 `error`는 아닌 경우

의미:

- API 호출은 성공했지만 테스트 기준을 만족하지 못했다.

점검:

- JSON 결과의 `output` 확인
- 번역 결과가 비어 있는지 확인
- `inspection.recommended_action`이 기대값인지 확인
- 챗봇 응답에 `answer`, `proposedTranslation`, `needsUserConfirmation`이 있는지 확인

---

### 6.4 `error`가 나오는 경우

의미:

- 실행 중 예외 발생

점검:

- JSON 결과의 `error` 필드 확인
- API 키, 모델명, 네트워크, 라이브러리 버전 확인
- mock 테스트가 통과하는지 먼저 확인

---

## 7. 현재 검증된 상태

최근 확인된 검증 결과:

### mock 모델 스모크

명령:

```powershell
python scripts\run_live_model_smoke.py --mock --include-images --json-out docs\mock_model_smoke_results.json --md-out docs\mock_model_smoke_report.md
```

결과:

```json
{"live": false, "include_images": true, "passed": 7, "executed": 7, "skipped": 0, "total": 7}
```

### 회귀 테스트

명령:

```powershell
python -m unittest tests.test_model_acceptance_from_docs tests.test_k_culture_rag tests.test_agent_workflow tests.test_cultural_lexicon tests.test_retriever_anchor_priority tests.test_terminology
```

결과:

```text
Ran 27 tests in 14.142s
OK
```

판단:

- 비용 없는 mock 기준으로는 전체 모델 테스트 경로가 정상 동작한다.
- live 이미지 제외 테스트도 기존 산출물 기준으로 5개 실행, 5개 통과, 이미지 2개 skip 상태가 기록되어 있다.
- 최종 live 이미지 포함 검증은 비용 발생 가능성이 있으므로 별도 실행해야 한다.

---

## 8. 권장 최종 제출 흐름

1. mock 전체 테스트 실행
2. 회귀 테스트 실행
3. live 이미지 제외 테스트 실행
4. 결과 Markdown을 테스트 계획/결과 보고서에 반영
5. 이미지 생성까지 증빙이 필요하면 live 이미지 포함 테스트를 1회 실행
6. 생성된 JSON/Markdown 파일을 증빙으로 첨부

최종 제출에 주로 사용할 파일:

- `docs/model_code_test_guide.md`
- `docs/model_test_handoff.md`
- `docs/live_model_smoke_report.md`
- `docs/live_model_smoke_results.json`
- 이미지 포함 검증 시:
  - `docs/live_model_smoke_with_images_report.md`
  - `docs/live_model_smoke_with_images_results.json`
# 2026-06-11 model routing update

Translation model selection is now profile-based instead of hardcoded to `gpt-4.1-mini`.

## qualityMode defaults

- default `qualityMode`: `standard`
- `fast` -> `gpt-5.4-nano`
- `standard` -> `gpt-5-mini`
- `quality` -> `gpt-5.4-mini`
- `baseline` -> `gpt-4.1-mini`

## override policy

- Request payload may pass `qualityMode`.
- Request payload may pass `translationModel` or `model`.
- Direct model overrides are allowlisted only:
  - `gpt-5.4-nano`
  - `gpt-5.4-mini`
  - `gpt-5-mini`
  - `gpt-4.1-mini`
- Unsupported override values raise a validation error. They do not silently fall back to `gpt-4.1-mini`.

## metadata expectations

Every translation workflow must record the selected model routing metadata, including:

- `mode`
- `quality_mode`
- `model_profile`
- `translation_model`
- `review_model`
- `model_override_used`

`gpt-4.1-mini` remains available only for baseline/debug/fallback use and is no longer the default operating model.

# 2026-06-12 locale adherence smoke guidance

## recommended smoke matrix

- default model under evaluation: `gpt-5-mini`
- comparison model: `gpt-5.4-mini`
- locales:
  - `ko_en_us`
  - `ko_zh_cn`
  - `ko_ja`
  - `ko_th_th`
- lengths:
  - `short`
  - `medium`
  - `long`

## expected checks

Each run should capture:

- `final_translation`
- `locale_adherence_status`
- `overall_translation_safety_status`
- `korean_char_ratio`
- `target_script_ratio`
- `source_copy_suspected`
- `source_copy_status`
- `residual_hangul_status`
- `residual_hangul_ratio`
- `residual_hangul_spans`
- `proper_noun_transliteration_status`
- `proper_noun_transliteration_issues`
- `source_prefix_match_200`
- `translation_model`
- `locale`
- `target_language_name`

## pass/fail interpretation

- `locale_adherence`: target-language maintenance check
- `source_copy`: copied-source or severe source-language leakage check
- `residual_hangul`: leftover Hangul check
- `proper_noun_transliteration`: possible Hangul proper-noun transliteration issue bucket
- `pass`: target-script ratio is healthy and there is no strong source-copy signal
- `warn`: mixed-script output, leftover Hangul, or transliteration issues that do not look like full source copy
- `fail`: copied-source suspicion, obviously wrong target-script balance, or leftover Korean sentence-level text
- `direct_only`: should follow the same safety gate and blocked-delivery policy as `v2_direct_qa`
- `retry_success`: `null` when retry was not attempted, `true` when retry succeeded, and `false` when retry failed
- `내부 디버그` QA rows are kept for diagnostics but excluded from user-visible QA counts

## response contract

- `deliveryStatus = "deliverable"` means the translation may be rendered as a normal success result.
- `deliveryStatus = "blocked_translation_safety"` means the translation must be shown as an error state, not a success result.
- `userVisibleErrorCode = "translation_safety_failed"` identifies the blocked safety case.
- `finalTranslation` must be non-empty when `deliveryStatus = "deliverable"`.
- `finalTranslation = ""` is reserved for blocked safety responses.
- Internal ratios such as `korean_char_ratio` and `target_script_ratio` remain metadata-only.
- `retryAttempted`, `retryCount`, `retrySuccess`, `initialLocaleAdherenceStatus`, `finalLocaleAdherenceStatus`, `initialSourceCopyStatus`, and `finalSourceCopyStatus` may be surfaced as debug metadata but should not be shown as user-facing error text.

## UI/client policy

- `deliverable` responses render the translation panel normally.
- `blocked_translation_safety` responses render a blocked/error card instead of an empty translation panel.
- Frontend helpers should branch on `deliveryStatus` and `userVisibleErrorCode`; blocked results must not be shown as ordinary success output.
- Recommended blocked-state copy:
  - title: `번역 검증 실패`
  - body: `대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요.`
  - action: `다시 시도`
- `residual_hangul_status = warn` remains a QA warning and does not block delivery.
- `proper_noun_transliteration_status = warn` or `unchecked` remains a QA warning and does not block delivery.
- `내부 디버그` rows are diagnostic-only and do not count toward user-visible QA cards.

## follow-up policy

- `source_copy_status = fail` and `locale_adherence_status = fail` are retry/hold candidates for a single same-model strict retry.
- Retry should use a stricter locale instruction block, not a different model.
- `residual_hangul_status = warn` should not trigger a retry by itself.
- `proper_noun_transliteration_status = warn|unchecked` should be tracked as a QA issue, not a retry trigger.
- `source_copy_suspected = true` should also trigger retry/hold logic.
- A fail should be treated as an internal quality/control event, not as a silent model fallback event.
- If retry still fails, set `delivery_status = blocked_translation_safety` and do not surface the translation as a normal successful result.
- Automatic cross-model fallback is still undecided.
- Preferred future flow:
  1. first translation
  2. locale-adherence guard
  3. one stricter retry on the same model
  4. if still failing, hold the result as internal error/QA state
