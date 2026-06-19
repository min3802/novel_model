# 용어집(Glossary) 단일 테이블 리팩터링

> 작성일: 2026-06-19
> 목적: 복잡한 4-테이블 용어집 구조를 **1개 테이블**로 단순화하고, 언어 코드를 2자리 국가 코드(JP/US/CN/TH)로 통일.

---

## 1. 배경 / 결정 사항

기존 코드는 용어집을 **4개 테이블**(`glossary_entries`, `glossary_aliases`, `glossary_forbidden_terms`, `glossary_candidates`)로 나눠 관리했고, 검수(후보 승인) 워크플로우와 priority/alias/forbidden 같은 개념이 번역 엔진 곳곳에 얽혀 있었다.

이를 다음 기준으로 단순화했다.

| 항목 | 결정 |
|---|---|
| 테이블 수 | **1개** (`glossary`) |
| 강제 여부(priority) | **컬럼 제거** — 용어집에 들어가면 무조건 적용되는 규칙 |
| 다른 이름(aliases) | **컬럼 제거** — 별칭은 각각 **별도 행**으로 저장 |
| 금지 번역(forbidden) | **컬럼 제거** |
| 용어 종류(category) | **person / place / organization 3종만** (그 외 거부) |
| 언어 코드 | **2자리 국가 코드**(JP/US/CN/TH)로 저장 |
| 후보 자동 저장 | **제거** — 번역이 용어집에 자동으로 쓰지 않음 (사람이 직접/챗봇으로 추가) |

---

## 2. 최종 테이블 구조

```sql
CREATE TABLE glossary (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  work_id    BIGINT NOT NULL,            -- works.work_id (FK)
  country    VARCHAR(2) NOT NULL,        -- JP / US / CN / TH
  source     VARCHAR(255) NOT NULL,      -- 원문 단어 (예: 강현우)
  target     VARCHAR(255) NOT NULL,      -- 번역 단어 (예: カン・ヒョヌ)
  category   VARCHAR(16) NOT NULL,       -- person / place / organization
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_glossary (work_id, country, source, category)
);
```

- **UNIQUE 키** `(work_id, country, source, category)`: 같은 작품·언어·원문·종류 조합은 한 행만 존재 → 같은 단어를 다시 저장하면 새 행이 아니라 **기존 행의 target만 수정**.
- ERD에는 이 테이블 하나만 추가하고, `work_id`가 `works` 테이블을 가리키는 **1:N 관계**만 그리면 된다.

### 별칭(alias) 처리 예시

"카이든 에른스트"가 "북부대공", "검은 늑대"로도 불린다면 → 각각 한 행씩:

| work_id | country | source | target | category |
|---|---|---|---|---|
| 12 | JP | 카이든 에른스트 | カイデン・エルンスト | person |
| 12 | JP | 북부대공 | カイデン・エルンスト | person |
| 12 | JP | 검은 늑대 | カイデン・エルンスト | person |

---

## 3. 언어 코드 변환 (표 ↔ 엔진 경계)

- **표/API**: 2자리 국가 코드(`JP`, `US`, `CN`, `TH`)를 사용.
- **번역 엔진 내부**: 기존 로케일(`ko_ja`, `ko_en_us`, `ko_zh_cn`, `ko_th_th`)을 그대로 사용 — 일본어 글자/조사 처리 등 품질 로직이 이 코드에 의존하므로 **건드리지 않음**.
- **변환 위치**: 용어집을 엔진에 넘길 때 기존 `locale_utils.country_to_locale()`로 한 번만 변환.

```
사용자/DB:  JP  ──country_to_locale()──▶  ko_ja  :번역 엔진
```

매핑(`app/translation/locale_utils.py`에 이미 존재):

| country | locale |
|---|---|
| JP | ko_ja |
| US | ko_en_us |
| CN | ko_zh_cn |
| TH | ko_th_th |

---

## 4. 용어 수정/추가 흐름 (예: 챗봇이 고유명사 번역을 고칠 때)

1. 사용자가 챗봇에 "리아는 リーア로 바꿔줘"라고 요청.
2. `(work_id, country, source='리아', category='person')` 행을 찾아 **`target`만 `リーア`로 수정** (`upsert_entry`).
   - 그 단어가 아직 없으면 새 행으로 추가됨.
3. 다음 번역부터 자동으로 `リーア` 적용.
4. (선택) 이미 출력된 번역문은 자동으로 안 바뀌므로, 본문에서도 해당 단어를 치환해 줘야 사용자가 당장 보는 결과가 고쳐진다.

> 핵심: "한 행 수정"은 DB의 `UPDATE` 한 번이며, 기능은 코드에 이미 있다.

---

## 5. 코드 변경 내역

| 파일 | 변경 |
|---|---|
| `app/translation/glossary_store.py` | 단일 테이블 레코드/리포지토리로 재작성. 후보·alias·forbidden·priority·status 제거. category 3종으로 축소. country↔locale 변환 추가. |
| `app/translation/mysql_glossary_store.py` | 단일 `glossary` 테이블 기준 SQL로 재작성. |
| `backend/services/glossary_service.py` | 후보/캡처 함수 제거. `list_glossary`, `upsert_entry`, `get_entry`, `delete_entry`, `hydrate_work_memory`(country 기준)만 유지. |
| `backend/services/glossary_api_service.py` | 후보 핸들러 제거. 항목 추가/수정/삭제/목록 핸들러를 country + 3카테고리 기준으로 단순화. |
| `backend/services/translation_service.py` | 후보 자동 캡처 로직 제거. 용어집 로드를 country 기준으로 변경. |
| `api_server.py` | 후보 승인/거절/목록 엔드포인트 및 정규식 제거. 삭제 핸들러 이름 변경. |
| `app/translation/__init__.py` | 삭제된 심볼 export 정리. |
| `tests/test_translation_v3_literary_package.py` | 삭제된 후보 캡처 테스트 정리, 저장소 테스트를 새 시그니처로 갱신. |

### 변경하지 않은 것
- 번역 엔진 코어(`v3_literary_package.py`, `v3_graph_orchestrator.py`)는 그대로. 엔진 내부의 `GlossaryEntry`는 유지하되, 저장소가 항상 `priority="hard"`, `aliases=[]`, `forbidden=[]`로 채워 넘긴다(모든 행 = 강제 규칙).

---

## 6. 영향 / 주의사항

1. **사라진 API 엔드포인트** (프론트가 호출 중이면 404):
   - `GET  /api/works/{id}/glossary/candidates`
   - `POST /api/works/{id}/glossary/candidates/{cid}/approve`
   - `POST /api/works/{id}/glossary/candidates/{cid}/reject`
   - 유지되는 엔드포인트: 용어 목록 조회 / 추가·수정 / 삭제 / 저장소 상태.
2. **MySQL 테이블은 직접 생성 필요**: 코드는 스키마를 자동 생성하지 않음. 위 `CREATE TABLE` SQL을 한 번 실행.
   - 기본 백엔드는 메모리 저장소라 테이블 없이도 개발/테스트는 동작.
   - MySQL 사용 시 환경변수 `GLOSSARY_STORE_BACKEND=mysql` + `MYSQL_*` 설정.

---

## 7. 검증 결과

- 단일 테이블 흐름 스모크 테스트 통과: JP 저장→ko_ja 변환, 소문자 country 정규화, 같은 행 수정, 잘못된 카테고리·대명사 거부.
- 전체 테스트 스위트: 리팩터링으로 **새로 깨진 테스트 0개**.
  - 남아 있는 실패 10개(이미지 추출·서버백엔드 콘텐츠·agent 프롬프트·translation versions·terminology consistency)는 **리팩터링 이전부터 존재하던 것**이며 glossary와 무관.
