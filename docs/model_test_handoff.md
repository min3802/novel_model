# Model Test Handoff

작성 일시: 2026-06-04

## 작업 배경

요구사항 정의서와 테스트 계획서를 기준으로 w.Lighter 모델 연동 테스트와 인수 기준 테스트를 정리했다.

- 요구사항정의서: `C:\Users\kwonm\Downloads\요구사항정의서_skn24-5team.xlsx`
- 테스트 계획/결과 보고서: `C:\Users\kwonm\Downloads\테스트 계획 및 결과 보고서_v2__SKN24_5Team의 사본.docx`
- 요구사항정의서는 **`요구사항 정의서 (최종)` 시트** 기준으로 확인했다.

## 완료 내용

1. 최종 요구사항 및 테스트 문서 추출
   - `docs/final_requirements_and_test_report_extract.txt`
   - 기준 시트: `요구사항 정의서 (최종)`
   - 확인된 요구사항 ID: 37개
   - 확인된 모델 관련 테스트: `TST-RET`, `TST-TRANS`, `TST-CHAT`, `TST-IMG`, `TST-GDE`

2. 모델 라이브 스모크 테스트 스크립트 작성
   - `scripts/run_live_model_smoke.py`
   - 기본 실행은 실제 OpenAI API 호출(`WLIGHTER_MOCK_MODE=false`)로 번역/챗봇/가이드 테스트를 수행한다.
   - 이미지 생성 테스트는 비용이 발생할 수 있어 기본값에서는 제외하고 `--include-images`를 명시해야 실행된다.

3. 이미지 생성 요구사항 테스트 가능 상태 정리
   - `TST-IMG-001`: 표지 이미지 생성
   - `TST-IMG-002`: 관계도 또는 장면 이미지 생성
   - 기본 live 테스트에서는 이미지 테스트를 건너뜀
   - `--mock --include-images`로 비용 없이 이미지 테스트 가능
   - 실제 이미지 모델 검증은 `--include-images` 옵션으로 별도 실행

4. API/model 동작 보강
   - `api_server.py`
     - 이미지 생성 모델 상수 정리
     - 이미지 mock 응답 추가
     - 폭력/선정성 등 unsafe 시각 요청 refusal 처리
   - `ko_locale_pipeline/chatbot.py`
     - mock 챗봇 응답을 자연스러운 한국어로 정리
   - `ko_locale_pipeline/translator.py`
     - mock 번역 응답 보강
   - `ko_locale_pipeline/inspector.py`
     - mock 검수 응답 구조 보강

5. 문서 기반 acceptance 테스트 추가
   - `tests/test_model_acceptance_from_docs.py`

## 검증 완료 내역

### 실제 모델 스모크 테스트

```powershell
python scripts\run_live_model_smoke.py
```

결과:

```json
{"live": true, "include_images": false, "passed": 5, "executed": 5, "skipped": 2, "total": 7}
```

산출물:

- `docs/live_model_smoke_results.json`
- `docs/live_model_smoke_report.md`

### 이미지 포함 mock 스모크 테스트

```powershell
python scripts\run_live_model_smoke.py --mock --include-images --json-out docs\mock_model_smoke_results.json --md-out docs\mock_model_smoke_report.md
```

결과:

```json
{"live": false, "include_images": true, "passed": 7, "executed": 7, "skipped": 0, "total": 7}
```

산출물:

- `docs/mock_model_smoke_results.json`
- `docs/mock_model_smoke_report.md`

### 회귀 테스트

```powershell
python -m unittest tests.test_model_acceptance_from_docs tests.test_k_culture_rag tests.test_agent_workflow tests.test_cultural_lexicon tests.test_retriever_anchor_priority tests.test_terminology
```

결과:

```text
Ran 27 tests OK
```

## 남은 작업 및 권장 후속 조치

1. 실제 이미지 모델까지 포함한 live 테스트를 별도 실행:

```powershell
python scripts\run_live_model_smoke.py --include-images --json-out docs\live_model_smoke_with_images_results.json --md-out docs\live_model_smoke_with_images_report.md
```

주의: 이 명령은 실제 이미지 생성 API 비용이 발생할 수 있다.

2. 최종 테스트 계획/결과 보고서 docx에 현재 검증 결과 반영
   - 원본: `C:\Users\kwonm\Downloads\테스트 계획 및 결과 보고서_v2__SKN24_5Team의 사본.docx`
   - 현재 markdown/json 산출물을 근거로 테스트 결과 표를 채우면 된다.

3. `TST-RET-001`의 문서 QA 50개 기준 검색 성능 평가는 별도 Recall/MRR 지표로 확장 권장
   - 현재 RAG/annotation retrieval 구조는 구현되어 있으나 테스트 데이터셋의 retrievalCount 기준 평가는 별도다.
   - 필요하면 문서 QA 목록을 기반으로 `scripts/run_live_model_smoke.py` 또는 별도 `run_retrieval_eval.py`로 확장하면 된다.

## 참고 및 주의

- 원본 문서는 이미 물음표(`?`) 문자로 치환되어 저장되어 있었고, 파일 바이트도 ASCII `?`로 확인됐다.
- 따라서 단순 UTF-8/CP949 재디코딩만으로는 원문을 복원할 수 없었다.
- 이 문서는 주변 산출물, 테스트 결과, 스크립트 내용을 기준으로 의미를 복구해 UTF-8로 다시 저장했다.
- 기본 live smoke는 이미지 비용 방지를 위해 이미지 2건을 `skipped`로 처리한다.
- mock 모드에서는 전체 7건을 비용 없이 검증한다.
- 실제 번역/챗봇/가이드 5건은 `.env` API 키가 필요하다.
- 이미지 생성까지 실제로 검증하려면 비용 발생 가능성을 확인한 뒤 `--include-images`를 사용한다.
