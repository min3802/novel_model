# 작업 요약 — qdrant 연동 및 RAG 파이프라인 리팩터링

대상: `ko_locale_pipeline` (w.LiGHTER 번역 RAG 파이프라인)
최종 갱신: 2026-06-08 (build_context LLM 입력 정제 반영)
백업: 각 단계 산출물은 세션 outputs 폴더에 `*_backup_*` 으로 보관됨.

---

## 0. 시작 배경 (진단)

`live_model_feature_test.ipynb` 평가 중, **RAG/qdrant 가 코드에서 전혀 사용되지 않음**을 발견.
- 두 retriever 가 `qdrant_local` 이 아니라 레거시 JSON(`data/legacy_idiom_rag/*.json`)을 읽고 있었음.
- 보고서는 ChromaDB 로 적혀 있었으나 실제 VDB 는 Qdrant 였음(보고서 미갱신).

---

## 1. 청킹 전략 선택

- 쿼리 청킹을 paragraph(줄바꿈) / sentence(Kiwi) 중 선택. `config.chunk_strategy`.
- **현재 기본값: `sentence`** (Kiwi 문장 단위). kiwipiepy 미설치 시 paragraph 폴백.
- 청킹 로직은 공통 토대 `ChunkingMixin`(retriever.py)으로 올려 두 retriever가 공유.

## 2. qdrant 연동 (핵심)

- IdiomRetriever(번역용) → locale별 idiom 컬렉션
  (ko_ja→idiom_jp, ko_en_us→idiom_us, ko_zh_cn→idiom_cn, ko_th_th→idiom_th)
- AnnotationRetriever(주석용) → kculture 컬렉션 (locale 무관)
- payload 평면 구조 통일(source_id, embedding_text, context_text, keyword_ko 등).
- locale→컬렉션 매핑·qdrant 경로는 config.py 헬퍼로 정의.
- 실데이터 end-to-end 검증 통과: "자업자득"→idiom_jp, "당근 중고거래"→kculture 정확 매칭.

## 3. qdrant 클라이언트 공유

- 모듈 레벨 캐시(`make_qdrant_client`)로 두 retriever가 같은 인스턴스 공유.
- 로컬 락 충돌 방지 + 서버(도커) 연결 중복 방지. 호출 순서 무관.
- 도커 전환 TODO 주석 명시(`path=`→`url=` + 컬렉션 재적재).

## 4. mock 구조 정리

- 중복이던 `backend_kind` 필드 제거 → `config.mock` 하나로 단순화.
- mock 기본값 통일: `is_mock_mode()` 기본값 true→false. 두 경로(PipelineConfig 직접 / backend) 모두 기본 실제 모드.
  mock 쓰려면 `WLIGHTER_MOCK_MODE=true` 명시. frontend README·docs 갱신.

## 5. 이름 / 파일 구조 정리

- `DenseRetriever` → `IdiomRetriever` (역할 명시).
- `IdiomRetriever` → `idiom_retriever.py` 로 분리, retriever.py 는 공통 토대만.
- `KoJaPipeline`/`KoLocalePipeline` → `TranslationPipeline` 으로 통일(별칭 완전 제거).
  (이름은 한일 전용처럼 보였으나 기능은 4개 국어 다국어 지원 — 검증 완료)
- 파일 `pipeline.py` → `translation_pipeline.py`.
- 역할별 폴더 재구성:
  - 최상위: translation_pipeline.py, config.py, __init__.py
  - retrieval/ : retriever(공통토대/ChunkingMixin), idiom_retriever, annotation_retriever
  - agents/ : translator, reviewer, inspector, chatbot
  - text_processing/ : cultural_lexicon, consistency_checker, terminology, korean_output
  - core/ : openai_client, prompt_loader, project_paths, runtime, mock_adapters, locales

## 6. 병렬화 + 임베딩 공유

- base의 `embed_query` 헬퍼로 쿼리를 1회만 임베딩해 두 검색에 공유(KURE 중복 2회→1회 제거).
- 각 retriever에 `search(chunks, vectors)` 추가. 무거운 임베딩 1회 후 가벼운 검색 2개 ThreadPool 병렬.

## 7. cultural_lexicon 제외

- `CulturalLexicon`(사전 매칭)은 데이터 5개·draft 상태의 초기/구버전 산물 → 파이프라인에서 제외.
  (클래스/파일/데이터는 삭제 안 함, pipeline 호출만 제거. 완전삭제는 원작성자 확인 후.)
- 문화 맥락은 AnnotationRetriever(kculture)가 단독 담당.
- 죽은 필드 `cultural_matches` 코드 전체에서 제거(AgentWorkflowResult + backend 응답).
- `cultural_context` 통로는 유지(lexicon 무관, annotation 전달용 살아있는 코드).

## 8. 설정 값 정정

- 번역/검수 모델: gpt-5.4-mini → **gpt-4.1-mini** (translation_model, review_model).
- API 키: `.env`의 OPENAI_API_KEY 사용(코드에 키 안 넣음, .gitignore 보호).
- HF_TOKEN: `.env`에 넣고 load_dotenv 로 로드 → huggingface_hub 자동 인식(코드 변경 불필요, 선택값).

## 9. ★ top_k / return_k 분리 (검색 개수 2단계) ★

**문제**: 기존엔 `top_k` 하나로 (A)문장당 검색수와 (B)최종 반환수를 둘 다 처리.
그 결과 1화(문장 수백 개)를 넣어도 **최종 3건만** 반환되어, 검출된 관용구 대부분이 버려짐.
(`_retrieve_qdrant` 가 문장별로 top_k개 검색 → 통합 → 다시 `[:top_k]` 로 잘랐기 때문)

**해결**: 두 단계를 별도 변수로 분리. config 에 4개 값으로 정리(이름도 idiom_ 접두사로 대칭):

| 변수 | 의미 | 기본값 |
|---|---|---|
| `idiom_top_k` | (A) 문장(청크) 1개당 qdrant 에서 가져올 후보 수 = 검색 깊이 | 3 |
| `idiom_return_k` | (B) 모든 문장 결과 통합 후 번역에 넘길 최종 상한 | 15 |
| `annotation_top_k` | (A) 주석: 문장당 검색 깊이 | 2 |
| `annotation_return_k` | (B) 주석: 최종 반환 상한 | 10 |

- 동작: "문장마다 top_k개 검색 → 점수 통합·중복제거 → score_threshold 통과분 중 상위 return_k개 반환".
- annotation 을 2/10으로 더 적게: kculture hit@1 ≈ 0.8 로 정확도 높아 적게 가져와도 충분(noise·비용↓).
- 두 retriever의 search/_retrieve_qdrant 가 top_k(검색)·return_k(반환)를 분리해서 받음.
- backend·스크립트의 `top_k=3` 하드코딩 제거 → 이제 검색 개수는 config 한 곳에서 관리.
- 검증: 실 qdrant 에서 top_k(검색깊이)·return_k(반환상한) 독립 동작 확인
  (예: 20문장 입력 → return_k=15 면 15건, return_k=5 면 5건; top_k 클수록 통합 후보 증가).

### threshold 통일 (0.6)

- 기존: idiom 은 locale별 차등(일/미 0.60, 중/태 0.55), annotation 은 0.55 고정 — 제각각.
- 변경: **idiom·annotation·모든 locale 0.6 으로 통일.**
  - `default_score_threshold()` 함수 + `__post_init__` 제거 → config 단일 값으로 단순화.
  - `score_threshold = 0.6` (idiom), `annotation_score_threshold = 0.6`.
- 효과: 0.6 미만(예: annotation 0.558)은 이제 걸러짐 = "확실한 것만" 수용.
  ※ 주의: 중국/태국 idiom 은 0.55→0.6 으로 올라가 검색 결과가 줄 수 있음. 결과 보고 조정.
- threshold 도 config 한 곳에서 관리(검색 개수와 동일 방식). 실제 품질 보며 튜닝할 값.

### build_context — LLM 에 넘기는 필드 정제

검색 결과(qdrant payload = "메타데이터")에서 **번역에 실질 도움되는 필드만** LLM 프롬프트로 넘긴다.
payload 자체는 qdrant 에 그대로 두고(검색에 계속 쓰임), build_context 가 고르는 것만 줄였다.

- **idiom**: `context_text`(원문표현/한국어기준/핵심의미/사용맥락/번역주의/예문) + `scene` + `tone` 만.
  - 제외: id(source_id), country, language, original_meaning(context와 중복), 검색 점수 3종.
- **annotation**: `keyword` + `context_text`(주석설명+번역가이드) 만.
  - 제외: id, category, culture_type, 검색 점수 3종.
- 이유: 식별자·분류 메타·검색 점수는 번역 판단에 무관한 노이즈/중복. "어떻게 번역하라"는 내용만 전달.

## 10. 검증 스크립트 (tests/)

- `tests/check_qdrant_e2e.py` : qdrant 연결 + KURE 임베딩 + 검색 end-to-end 4단계 점검.
- `tests/check_translation_pipeline.py` : 번역 전체 흐름(검색→번역→검수→inspect) mock=False 실행.
  - `--locale ko_ja|ko_en_us|ko_zh_cn|ko_th_th|all` (all = 4개 국어 한 번에)
  - `--text "문장"` (짧은 테스트) / `--file 경로.txt` (긴 원문; --text보다 우선)
    ※ --file 상대경로는 "실행하는 폴더(cwd)" 기준. 루트 실행 시 `--file tests/엘리트_1화.txt`.
  - `--out 경로.html` (미지정 시 tests/outputs/translation_result_<시각>.html 자동 생성)
  - 출력: 콘솔 + **HTML 파일** 저장(원문/검색표/번역/검수이유/inspect/최종번역 섹션).
    검수 이유 포함: review의 recommended_action·risk_summary·review_note,
    inspect의 severity·problematic_spans·suggestions. 전체 실행 시간 표시.
- 두 스크립트: 루트 sys.path 부트스트랩 + 루트 `.env` 로드(HF_TOKEN 포함) → 어디서 실행하든 동작.
- 파일명이 `check_` 라 unittest/pytest 자동수집에 안 걸림.
- 테스트용 원문: `tests/엘리트_1화.txt` (연속 빈줄 1줄로 정리, CRLF→LF, 5,620자).
  원본 백업: `tests/엘리트_1화_원본.txt.bak`.

---

## 파이프라인의 두 검색 (cultural_lexicon 제외 후)

| 검색 | 개수(기본) | threshold | LLM 전달 필드 |
|---|---|---|---|
| IdiomRetriever | top_k 3 / return_k 15 | 0.6 | context_text, scene, tone |
| AnnotationRetriever | top_k 2 / return_k 10 | 0.6 | keyword, context_text |

annotation 전달: search → `build_context()` 텍스트화 → `cultural_context` 문자열 →
`translator.translate(cultural_context=...)` 로 번역 프롬프트에 주입.

## 언어 선택 / 입력 검증 (backend)

- 사용자가 "대상 국가"(일본/미국/중국/태국) 선택 → `COUNTRY_TO_LOCALE` 가 locale로 변환.
- 다국어 번역 작동 확인: 4개 locale 각각 target_language 정확히 잡힘.
- 한국어 차단: `_contains_hangul()` — 완성형 한글(가~힣) 없으면 LLM 호출 없이 차단(BLOCK).

## 검증 현황

- 관련 unittest 28~30개 통과(작업마다 재확인).
- 실 qdrant: 두 retriever search(공유벡터) 정상, 동시 읽기 안전, top_k/return_k 독립 동작.
- 검색 결과 중복 제거 구현됨: 같은 문서가 여러 청크에서 걸리면 source_id 기준 최고 점수 1건만 유지.
- KURE 임베딩 쿼리당 1회 호출 확인.
- end-to-end(앵살 로컬): qdrant+KURE 검색 의미적으로 정확히 작동 확인 완료.

## 남은 작업

- **로컬에서 `check_translation_pipeline.py` 실행** → 실제 LLM 번역 흐름 최종 확인 + HTML 검토.
  (`--locale all` 4개국어 / `--file tests/엘리트_1화.txt` 긴 원문 / `--out`)
- 프론트엔드가 응답의 `cultural_matches` 를 참조했다면 그쪽도 수정(이 레포엔 프론트 없음).
- cultural_lexicon 완전 삭제 여부(원작성자 확인 후).
- **청크(문장) 추적** — 각 검색 결과가 원문의 "어느 문장(청크)에서 검색됐는지" 기록.
  현재 `_retrieve_qdrant` 는 source_id 로 중복 제거(✅ 구현됨)하며 점수·payload 만 남기고
  "어느 청크였는지"는 버린다. 추적이 있으면 (1) 검증: 원문 문장→참고 관용구 매핑 확인,
  (2) 번역: 문장별로 맞는 참고자료를 줘서 정확도↑. 두 가지 방향(가벼운 HTML 표시 / 번역 프롬프트
  문장별 연결) 중 선택해 추후 구현.
- langgraph 전환(현재 ThreadPool 로 충분, fallback·노드 확장 필요 시).
- mock 분기 완전 제거(도커 전환 + 테스트를 진짜 qdrant 로 이관 시점).
- 보고서 동기화 — ChromaDB→Qdrant, 임베딩 KURE-v1, 번역 모델 gpt-4.1-mini.

## 알려진 이슈 (이번 작업과 무관, 다른 팀 파일)

- `data/localization_guide/platform_trend_advisor.py` f-string 내 백슬래시 문법 오류
  (Python 3.10 실행 불가). guide 기능/일부 테스트 import 를 막음.
