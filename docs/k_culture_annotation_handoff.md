# K-Culture Annotation RAG Handoff

작성 시각: 2026-06-03 21:26:05 +09:00

## 현재 목표/맥락

Next.js ??? + api_server.py + ko_locale_pipeline ???? ?? ???. Streamlit ?????? ????? ? ?? ?? ?? ??? ???.

이번 작업의 핵심은 C:\Users\kwonm\Downloads\K-Culture_desc.json을 기존 관용어/표현 RAG에 섞지 않고, **한국 문화 주석/해설 후보 RAG**로 분리하는 것이었다.

## 중요한 제품 방향 결정

현재 RAG는 두 종류로 분리한다.

1. **Translation-expression RAG**
   - 데이터: ko_anchored_idiom_results_final/*_ko_anchored.json
   - 담당: ko_locale_pipeline.retriever.DenseRetriever
   - 용도: 관용어, 속담, 고정 표현, target-language equivalent 번역 참고
   - 예: 가는 말이 고와야 오는 말이 곱다 -> do unto others as you would have them do unto you

2. **Cultural annotation RAG**
   - 데이터: data/annotation_rag/kculture_rag_documents_reviewed.json
   - 담당: ko_locale_pipeline.annotation_retriever.AnnotationRetriever
   - 용도: 한국 문화 요소가 등장했을 때 주석/짧은 설명/번역문 내 자연스러운 보완이 필요한지 판단
   - 번역 표현을 강제하지 않는다.
   - 예: 초복, 삼계탕, 얼죽아, 아아, 떼창

## 생성/수정된 주요 파일

- scripts/build_k_culture_rag.py
  - K-Culture_desc.json을 annotation card로 변환한다.
  - 자동 생성 출력: data/annotation_rag/k_culture_annotation_cards.json
  - report: data/annotation_rag/_k_culture_annotation_report.json
  - 더 이상 locale별 번역 RAG에 append하지 않는다.
  - 현재 운영 기본 데이터는 인간 검수된 data/annotation_rag/kculture_rag_documents_reviewed.json이다.

- ko_locale_pipeline/annotation_retriever.py
  - 새 annotation 전용 retriever.
  - `embedding_text`를 임베딩 검색 텍스트로 사용한다.
  - `context_text`를 모델 프롬프트에 전달한다.
  - reviewed RAG 기준으로 정확 매칭 boost/trigger 추출은 사용하지 않는다.
  - 운영 검색은 embedding similarity에 의존한다. 성능이 부족하다고 확인되면 그때 trigger/boost를 별도 설계한다.

- ko_locale_pipeline/config.py
  - nnotation_dataset_path, nnotation_top_k, nnotation_score_threshold 추가.
  - 기본 annotation dataset은 data/annotation_rag/kculture_rag_documents_reviewed.json.

- ko_locale_pipeline/locales.py
  - locale별 기본 RAG를 다시 기존 ko_anchored_idiom_results_final/*_ko_anchored.json로 복구했다.
  - 즉 K-Culture는 translation RAG에 섞이지 않는다.

- ko_locale_pipeline/pipeline.py
  - DenseRetriever와 AnnotationRetriever를 둘 다 사용한다.
  - 
un_with_inspection() 결과에 nnotation_matches가 추가됐다.
  - translator에는 CulturalLexicon.build_context()와 AnnotationRetriever.build_context()를 합친 cultural_context가 들어간다.

- prompts/agent_runtime/TRANSLATOR_PROMPT.md
  - translation-expression references와 cultural annotation/note candidates를 명확히 구분하도록 수정.
  - annotation card는 target-language expression recommendation이 아니라고 명시.

- 	ests/test_k_culture_rag.py
  - annotation card 생성, annotation retriever 검색, translation RAG와 K-Culture 분리 검증.

- docs/rag_normalized_schema.md
  - K-Culture annotation RAG 구조 및 재생성 방법 문서화.

## 현재 데이터 산출물

- data/annotation_rag/kculture_rag_documents_reviewed.json
  - 총 494개 card
  - 인간 검수 기반 운영 기본 annotation RAG
  - id 형식: `KCULTURE_0001` 같은 짧은 안정 ID
  - 운영 card 필드: `id`, `embedding_text`, `context_text`, `trigger_terms`, `metadata`
  - 실제 reviewed card 필드: `id`, `embedding_text`, `context_text`, `metadata`
  - `metadata.keyword_ko`는 검색 boost가 아니라 로그/분석/표시용 메타데이터로 둔다.
  - 제거된/미사용 필드: `weak_terms`, `scenario`, `annotation_hint`, `semantic_keywords`, `cultural_explanation`, nested `source`
  - metadata에는 `culture_id`, `category`, `culture_type_ko`, `keyword_ko`만 둔다.
  - `context_text`는 답지/오답 해설 형식이 아니라 `키워드`, `핵심 요약`, `주석 설명`, `번역 가이드`로 구성한다.
  - `번역 가이드`는 모든 카드에 같은 문장을 넣지 않고 category와 항목 내용에 맞춰 다르게 생성한다.

- data/annotation_rag/k_culture_annotation_cards.json
  - K-Culture_desc.json에서 자동 생성한 보조 산출물이다.
  - 현재 모델 기본 파이프라인에서는 reviewed 파일을 사용하므로 이 파일은 기본 사용 대상이 아니다.

- data/annotation_rag/_k_culture_annotation_report.json
  - category count 포함

data/rag_augmented/* 파일은 이전 단계 산출물이고 최신 파이프라인에서 쓰지 않으므로 삭제했다.

## 현재 파이프라인 요약

`	ext
Next.js frontend
  -> api_server.py /api/translate
  -> targetCountry -> locale
  -> optional terminology/terms glossary + noun/proper-noun candidate hints
  -> KoLocalePipeline.run_with_inspection()
       1. DenseRetriever: translation-expression RAG
       2. CulturalLexicon: curated cultural terms
       3. AnnotationRetriever: K-Culture annotation candidates
       4. Translator
       5. Reviewer
       6. Inspector
  -> finalTranslation + reviewSummary + workflow 반환
`

## 샘플 점검 결과

Mock mode 기준 확인:

`	ext
입력: 초복이라 삼계탕을 먹고 몸보신했다.
translation_rag: []
annotation_matches:
- KCULTURE_0003
- KCULTURE_0472
- KCULTURE_0473
`

`	ext
입력: 얼죽아라서 아아 마신다.
translation_rag: []
annotation_matches:
- KCULTURE_0012
- KCULTURE_0013
`

`	ext
입력: 가는 말이 고와야 오는 말이 곱다더니.
translation_rag:
- US_000952
annotation_matches: 일부 irrelevant 후보가 뜰 수 있음
`

## 검증 완료

마지막 통과 명령:

`powershell
python -m unittest tests.test_k_culture_rag tests.test_agent_workflow tests.test_cultural_lexicon tests.test_retriever_anchor_priority tests.test_terminology
# Ran 20 tests OK
`

`powershell
python -c "import py_compile, pathlib; files=[pathlib.Path('api_server.py'), *pathlib.Path('ko_locale_pipeline').glob('*.py'), *pathlib.Path('scripts').glob('*.py'), *pathlib.Path('tests').glob('test_k_culture_rag.py')]; [py_compile.compile(str(p), doraise=True) for p in files]; print('compiled', len(files), 'files')"
# compiled 23 files
`

`powershell
cd frontend
npm run typecheck
# tsc --noEmit OK
`

??: Streamlit ???? ???? ?????, ?? unittest discover? ?? API/??/????? ??? ???? ????.

## 다음에 바로 할 만한 일

우선순위 순서:

1. **AnnotationRetriever 추가 평가**
   - 2026-06-04 기준 `trigger_terms` 일반어 정제와 trigger boost 약화는 반영됨.
   - 현재 trigger는 정확 매칭 보조 신호이고, 최종 점수에는 `0.25` 가중치만 더한다.
   - 실제 모델 모드에서 annotation 과다/과소 사용을 샘플링해야 한다.

2. **trigger_terms 수동 검수 shortlist**
   - 자동 정제로 `trigger_terms`는 4,592개 → 645개로 줄었다.
   - 일반 샘플(`다함께`, `춤을`, `학교`, `수업`, `음식`, `회복` 등)은 제거됨.
   - `ScenarioBody`의 대화/비교 표현은 더 이상 trigger로 승격하지 않는다.
   - `도요우노/도요노 우시노 히` 계열 표현은 출력 card 전체에서 마스킹되어 literal로 남지 않는다.
   - 예: `미국에서는 7회쯤에` 같은 비교문은 scenario에는 남아도 trigger_terms에서는 제거됨.
   - 카드 id는 긴 설명 slug를 제거하고 `k_culture_desc_0001` 같은 짧은 안정 ID로 단순화됨.

3. **Inspector에 annotation_matches 전달**
   - 현재 Inspector에는 translation RAG 기반 used_references만 전달된다.
   - 문화 주석/리스크 판단에 annotation 후보를 직접 넘기면 더 일관될 수 있다.

4. **UI에서 annotation 후보 표시**
   - 현재 workflow.annotation_matches 안에는 들어가지만, 프론트에서 별도 카드/주석 후보로 명확히 보여주는지는 아직 약하다.

5. **실제 모델 모드 평가**
   - mock embedding/translation 기준은 구조 검증용이다.
   - 실제 OpenAI embedding + translation으로 annotation 과다/과소 사용을 샘플링해야 한다.

## 재생성 명령

`powershell
python scripts\build_k_culture_rag.py --input C:\Users\kwonm\Downloads\K-Culture_desc.json
`

## 주의

- K-Culture annotation card는 번역 표현 reference가 아니다.
- data/rag_augmented/*는 현재 기본 파이프라인에서 쓰지 않는다.
- 기존 idiom/translation RAG는 ko_anchored_idiom_results_final/*_ko_anchored.json를 계속 사용한다.
