# w.Lighter characters + visuals unified package

이 압축파일 하나에 아래가 모두 들어 있습니다.

```text
characters/
visuals/
app.py
```

## 구조

```text
characters/
  캐릭터 설정집 원본 데이터
  시놉시스 기반 캐릭터 설정 생성
  캐릭터 목록/상세/수정/삭제

visuals/
  캐릭터 설정집 기반 표지 이미지 생성
  선택된 캐릭터 기반 관계도 JSON 요약
  HTML 관계도 생성/조회/다운로드

app.py
  Django 붙이기 전 로컬에서 빠르게 테스트하는 Streamlit 앱
```

## Django 적용

`characters/`, `visuals/` 폴더를 Django 프로젝트의 `web/` 아래에 넣습니다.

```text
web/
  accounts/
  characters/
  config/
  credits/
  guides/
  visuals/
  works/
  manage.py
```

`config/settings.py`:

```python
INSTALLED_APPS = [
    ...
    "characters",
    "visuals",
]

WLIGHTER_WORK_MODEL = "works.Work"
WLIGHTER_TEXT_MODEL = "gpt-5.4-nano"
WLIGHTER_IMAGE_MODEL = "gpt-image-2"
WLIGHTER_IMAGE_SIZE = "1024x1024"
```

`config/urls.py`:

```python
from django.urls import include, path

urlpatterns = [
    ...
    path("api/characters/", include("characters.urls")),
    path("api/visuals/", include("visuals.urls")),
]
```

## URL 유지 기준

`characters/urls.py`는 아래 3개를 모두 유지합니다.

```python
urlpatterns = [
    path("works/<int:work_id>/", views.character_collection, name="character_collection"),
    path("works/<int:work_id>/extract/", views.character_extract, name="character_extract"),
    path("<int:character_id>/", views.character_detail, name="character_detail"),
]
```

역할:

```text
GET  /api/characters/works/{work_id}/
  선택한 작품의 캐릭터 목록 조회

POST /api/characters/works/{work_id}/
  캐릭터 직접 등록

POST /api/characters/works/{work_id}/extract/
  시놉시스 기반 캐릭터 설정 생성

GET/PATCH/DELETE /api/characters/{character_id}/
  캐릭터 상세 조회/수정/삭제
```

## 관계도 생성 흐름

프론트:

```text
1. 작품 선택
2. GET /api/characters/works/{work_id}/ 호출
3. 캐릭터 목록 체크박스 표시
4. 선택된 character_ids로 관계도 생성 요청
```

관계도 생성 요청:

```json
{
  "title": "Version 1",
  "character_ids": [1, 2, 3, 4, 5, 6, 7]
}
```

백엔드:

```text
1. character_ids가 같은 작품 소속인지 검증
2. 최대 10명 제한 검증
3. 선택된 캐릭터 설정집을 LLM이 관계도용 JSON으로 요약
4. HTML 관계도 생성
5. RelationshipMap에 relation_data + html_content 저장
```

관계도 내용은 직접 수정하지 않습니다.
수정이 필요하면 캐릭터 설정집을 수정한 뒤 관계도를 다시 생성합니다.

## Streamlit 테스트

로컬 테스트는 `app.py`만 실행합니다.

```bash
streamlit run app.py
```

`.env` 예시:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.4-nano
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_SIZE=1024x1024
```

