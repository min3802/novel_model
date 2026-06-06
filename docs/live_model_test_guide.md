# Live 모델 테스트 가이드

작성일: 2026-06-06

## 목적

이 문서는 팀원이 로컬 `.env` 설정을 사용해서 실제 모델 호출까지 검증하는 방법을 정리합니다.

mock/unit 테스트는 코드 연결과 데이터 흐름을 확인하기 위한 테스트입니다.  
실제 번역 품질, 챗봇 응답, 현지화 가이드 품질은 live 테스트로 별도 확인해야 합니다.

## 테스트 구분

| 구분 | 목적 | API 키 | 비용 | 대표 명령 |
| --- | --- | --- | --- | --- |
| mock/unit 테스트 | 코드 연결, import, 데이터 흐름 확인 | 불필요 | 없음 | `python -m unittest ...` |
| module smoke mock | 웹/API 서버 없이 모듈 연결 확인 | 불필요 | 없음 | `python scripts/module_smoke.py --case all` |
| live 모델 테스트 | 실제 모델 응답 품질 확인 | 필요 | 발생 가능 | `python scripts/run_live_model_smoke.py` |
| live 이미지 테스트 | 실제 이미지 생성까지 확인 | 필요 | 발생 가능 | `python scripts/run_live_model_smoke.py --include-images` |

## 사전 조건

로컬에 `.env` 파일이 있어야 합니다.

```txt
.env
```

`.env`에는 실제 모델 호출에 필요한 API 키와 설정이 들어 있어야 합니다.  
`.env`는 git에 올리지 않습니다.

주의:

- live 테스트는 외부 API를 호출합니다.
- 모델 사용량에 따라 비용이 발생할 수 있습니다.
- 네트워크 연결이 필요합니다.
- 이미지 생성 테스트는 기본 live smoke에서 제외되어 있습니다.

## 1. 기본 mock 확인

먼저 비용 없는 mock 테스트로 코드 연결이 깨지지 않았는지 확인합니다.

```powershell
python scripts\module_smoke.py --case all
python -m unittest tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_model_feature_backlog
```

기대 결과:

```txt
OK
```

또는 `module_smoke.py`에서 JSON 결과가 출력되어야 합니다.

## 2. 실제 모델 smoke 테스트

실제 모델 호출을 포함한 기본 smoke 테스트입니다.

```powershell
python scripts\run_live_model_smoke.py
```

이 명령은 기본적으로 이미지 생성을 제외하고 실행합니다.

확인 대상:

- 번역 모델 호출
- 챗봇/응답 생성
- 검수/가이드 계열 응답
- API contract 수준의 실제 모델 연결

기본 산출물:

```txt
docs/live_model_smoke_results.json
docs/live_model_smoke_report.md
```

## 3. 특정 모듈만 live로 확인

전체 smoke가 아니라 특정 모듈만 확인하고 싶으면 `module_smoke.py`에 `--live`를 붙입니다.

```powershell
python scripts\module_smoke.py --case translate --live
python scripts\module_smoke.py --case guide --live
```

주요 옵션:

```powershell
python scripts\module_smoke.py --case translate --locale ko_en_us --live
python scripts\module_smoke.py --case terminology
```

참고:

- `terminology`는 기본적으로 비용 없는 로컬 검증입니다.
- `translate --live`, `guide --live`는 실제 모델 호출 가능성이 있습니다.

## 4. 이미지 생성 포함 live 테스트

이미지 생성은 비용이 더 클 수 있으므로 기본 smoke에서는 제외합니다.  
실제 이미지 모델까지 검증해야 할 때만 아래 명령을 사용합니다.

```powershell
python scripts\run_live_model_smoke.py --include-images
```

별도 산출물 이름을 지정하려면:

```powershell
python scripts\run_live_model_smoke.py --include-images --json-out docs\live_model_smoke_with_images_results.json --md-out docs\live_model_smoke_with_images_report.md
```

주의:

- 이 테스트는 실제 이미지 생성 API 비용이 발생할 수 있습니다.
- 이미지 정책/안전 필터에 따라 일부 케이스는 refusal이 정상 결과일 수 있습니다.

## 5. 결과를 어떻게 판단할 것인가

live 테스트에서 봐야 할 것은 단순히 명령이 성공했는지가 아닙니다.

확인 기준:

- 모델 호출이 실제로 성공했는가
- 응답 JSON 구조가 깨지지 않았는가
- 번역 결과가 최소한 사용 가능한 품질인가
- 용어 일관성 정책이 반영되는가
- 현지화 가이드가 근거 없는 스토리 추천으로 흐르지 않는가
- refusal 또는 skip이 의도된 케이스인지 구분되는가

## 6. 실패 시 확인할 것

### API 키 문제

증상:

```txt
authentication error
invalid api key
missing api key
```

확인:

```txt
.env 파일 존재 여부
API 키 값
환경 변수 이름
```

### 네트워크 문제

증상:

```txt
connection error
timeout
dns
```

확인:

```txt
네트워크 연결
프록시/VPN
방화벽
```

### 비용/쿼터 문제

증상:

```txt
quota exceeded
billing
rate limit
```

확인:

```txt
계정 결제 상태
사용량 제한
요청 빈도
```

### 이미지 테스트 실패

이미지 테스트는 비용과 정책 필터 영향이 있으므로, 기본 live smoke와 분리해서 봅니다.

```powershell
python scripts\run_live_model_smoke.py
```

가 먼저 통과하는지 확인한 뒤 이미지 포함 테스트를 별도로 실행합니다.

## 권장 실행 순서

팀원에게 공유할 때는 아래 순서를 권장합니다.

```powershell
# 1. 비용 없는 기본 검증
python scripts\module_smoke.py --case all
python -m unittest tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_model_feature_backlog

# 2. 실제 모델 기본 smoke
python scripts\run_live_model_smoke.py

# 3. 필요한 경우에만 이미지 포함
python scripts\run_live_model_smoke.py --include-images
```

## 핵심 정리

```txt
git에 올라간 코드만으로 mock/unit 테스트는 바로 가능하다.
실제 모델 품질 확인은 로컬 .env를 사용하는 live 테스트로 별도 실행해야 한다.
이미지 생성 테스트는 비용이 발생할 수 있으므로 명시적으로 --include-images를 붙였을 때만 실행한다.
```
