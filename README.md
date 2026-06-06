# w.LiGHTER 모델/API 파이프라인

이 저장소는 w.LiGHTER의 모델 파이프라인, API, 테스트 코드를 협업 기준으로 관리합니다.
기존 Streamlit 프로토타입은 혼선을 줄이기 위해 현재 제품 표면에서 제외했습니다.

## 주요 작업 영역

```txt
api_server.py                         # 표준 라이브러리 기반 JSON API 서버
backend/                              # API 서비스/인메모리 저장소
ko_locale_pipeline/                   # 번역, RAG, 검수, 용어 일관성 파이프라인
  - terminology.py                    # 명사/고유명사 용어 일관성 후보/검증
  - runtime.py                        # mock/live 실행 모드 판단
  - mock_adapters.py                  # 테스트용 deterministic fake 응답
scripts/                              # 웹 없이 모듈 점검/데이터 생성/라이브 스모크 실행
tests/                                # API/모델/파이프라인 테스트
data/localization_guide/              # 플랫폼 트렌드 수집 및 현지화 가이드 생성
frontend/                             # Next.js 프론트엔드. 모델 협업에는 필수 표면이 아님
```

## 웹 없이 모듈 테스트하기

프론트엔드나 API 서버를 켜지 않아도 모델 모듈을 직접 확인할 수 있습니다.
기본은 mock/offline 모드라 API 키와 비용 없이 연결 구조를 점검합니다.

```bash
python scripts/module_smoke.py --case all
python scripts/module_smoke.py --case terminology
python scripts/module_smoke.py --case translate --locale ko_en_us
```

실제 LLM 호출로 번역 품질을 확인할 때만 `--live`를 붙입니다.

```bash
python scripts/module_smoke.py --case translate --live
python scripts/run_live_model_smoke.py
```

팀원이 로컬 `.env`를 사용해 실제 모델 호출까지 검증해야 한다면 아래 문서를 먼저 확인합니다.

```txt
docs/live_model_test_guide.md
```

## Mock 테스트와 Live 테스트의 역할

mock은 번역 품질 평가용이 아니라 다음을 빠르게 확인하기 위한 장치입니다.

- import/API contract가 깨지지 않았는지
- 파이프라인 데이터 흐름이 이어지는지
- 테스트가 API 키 없이 결정적으로 실행되는지
- CI나 팀원 로컬에서 비용 없이 기본 검증이 가능한지

mock 응답은 `ko_locale_pipeline/mock_adapters.py`에 격리되어 있고,
mock/live 모드 판단은 `ko_locale_pipeline/runtime.py`에 모여 있습니다.
실제 번역/현지화 품질 평가는 live 모델 실행으로 확인해야 합니다.

live 모델 테스트는 실제 외부 API를 호출하므로 API 키, 네트워크, 비용/쿼터 영향을 받습니다.
이미지 생성 테스트는 기본 smoke에서 제외되어 있으며, 필요할 때만 `--include-images`로 별도 실행합니다.

## 전체 Python 검증

```bash
python -m unittest discover -s tests
```

집중 검증 예시:

```bash
python -m unittest tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_platform_trend_collector tests.test_model_acceptance_from_docs tests.test_model_feature_backlog tests.test_k_culture_rag
```

## API 서버 실행

```bash
python api_server.py
```

## 프론트엔드 실행

프론트엔드는 UI 확인이 필요할 때만 실행합니다.
모델/파이프라인 테스트에는 필수 아닙니다.

```bash
cd frontend
npm run dev
```

## 현지화 가이드 흐름

`/api/guide`는 세 가지 모드를 지원합니다.

1. 시놉시스와 국가가 모두 없으면 국가/장르 선택지를 반환합니다.
2. 국가와 장르만 있으면 해당 국가/장르 기반 가이드를 생성합니다.
3. 시놉시스가 있으면 플랫폼 트렌드 데이터를 바탕으로 적합 국가를 추천한 뒤 가이드를 생성합니다.

트렌드 근거 데이터는 아래에 있습니다.

```txt
data/localization_guide/platform_observation/platform_trends_current.json
data/localization_guide/platform_observation/platform_trend_localization_guide.md
data/localization_guide/platform_observation/platform_trend_guide_prompt.json
```

## 작업 메모

- 새 Streamlit 페이지/테스트는 추가하지 않습니다.
- 번역 일관성은 ontology가 아니라 `terminology.py` 기준으로 관리합니다.
- 동사/형용사 표현 차이는 강제하지 않고, 명사/고유명사 용어만 일관성 대상으로 봅니다.
- LLM 후보 추출을 붙이더라도 suggested → confirmed 승격 구조를 유지합니다.
