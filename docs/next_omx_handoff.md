# Next OMX Handoff

작성일: 2026-06-04  
목적: 터미널/세션을 닫은 뒤에도 다음 OMX/Codex 세션이 현재 작업 맥락을 바로 이어받기 위한 인계 문서.

## 다음 세션에서 먼저 읽을 파일

다음에 OMX를 새로 켜면 아래 순서로 읽으면 된다.

1. `docs/next_omx_handoff.md`
2. `docs/k_culture_annotation_handoff.md`
3. `docs/model_code_test_guide.md`
4. `data/localization_guide/platform_observation/platform_observation_poc.json`
5. 필요 시 `scripts/platform_observation_probe.py`

권장 시작 프롬프트:

```text
docs/next_omx_handoff.md 읽고, 여기에 적힌 다음 작업부터 이어서 진행해줘. Streamlit은 제외하고 모델/API/Next.js 쪽만 봐줘.
```

---

## 중요한 전제

- 앞으로 **Streamlit은 사용하지 않는다.**
- 구현/수정은 **모델, API 서버, Next.js 쪽 중심**으로 진행한다.
- K-Culture RAG는 `trigger_terms`나 exact keyword boost에 의존하지 않고, **임베딩 모델 성능 중심**으로 간다.
- 임베딩 성능이 부족하다는 테스트 결과가 나오기 전까지는 trigger/exact boost를 다시 넣지 않는다.
- 현지화 가이드는 아직 완성 기능이 아니라 **데이터 수집 가능성 검증 단계**다.

---

# 1. 모델 구현 현재 상태

## 1.1 K-Culture RAG

현재 기본 RAG 데이터는 아래 파일이다.

```txt
data/annotation_rag/kculture_rag_documents_reviewed.json
```

이 파일은 인간 검수된 기준 데이터로 사용하기로 결정했다.

현재 스키마:

```json
{
  "id": "...",
  "embedding_text": "...",
  "context_text": "...",
  "metadata": {
    "category": "...",
    "keyword_ko": "...",
    "culture_type_ko": "..."
  }
}
```

현재 적용된 방향:

- `embedding_text`를 검색 대상 텍스트로 사용
- `context_text`를 모델 컨텍스트로 전달
- `metadata`는 보조 정보로 사용
- `trigger_terms` 기반 검색 제거
- exact match boost 제거
- weak terms 제거
- 긴 scenario / annotation_hint 기반 구버전 구조는 더 이상 기본값이 아님

관련 파일:

```txt
ko_locale_pipeline/config.py
ko_locale_pipeline/annotation_retriever.py
tests/test_k_culture_rag.py
docs/k_culture_annotation_handoff.md
```

마지막으로 확인된 테스트:

```txt
35 tests OK
```

## 1.2 다음에 모델 쪽에서 할 일

### 1순위: 실제 임베딩 모델 검색 품질 테스트

다른 팀원이 임베딩 모델 테스트를 진행한다고 했다. 결과를 받으면 아래 쿼리류를 기준으로 확인한다.

예시 테스트 쿼리:

- `삼계탕`
- `복날`
- `학원`
- `막걸리 차 바퀴`
- `제사`
- `회식`
- `군대`
- `존댓말 반말`
- `수능`
- `명절`

확인할 것:

- 관련 카드가 top-k 안에 들어오는가
- 엉뚱한 일반 문화 카드가 너무 많이 섞이지 않는가
- 번역 가이드에 실제로 도움이 되는 context_text가 들어오는가

주의:

```txt
검색 품질이 부족하다는 증거가 나오기 전까지 trigger_terms나 exact boost를 다시 넣지 말 것.
```

### 2순위: 라이브 모델 테스트 시나리오 만들기

필요한 테스트 문서 형태:

```txt
입력 원문
기대되는 RAG 카드
기대 번역 방향
실패 기준
모델 출력 기록
판정
```

### 3순위: 번역 일관성 기능

아직 중요한 미완성 기능이다.

필요 기능:

- 고유명사 glossary
- 캐릭터명/지명/스킬명 번역 일관성
- 이전 회차 번역 기억
- 회차별 translation memory
- 용어 변경 이력
- 모델 출력 후 일관성 검사

추천 구현 방향:

```txt
작품 단위 glossary
+ 회차 단위 translation memory
+ 이전 회차 요약/용어 이력
+ 번역 후 consistency check
```

---

# 2. 현지화 가이드 현재 상태

## 2.1 현재 결론

현지화 가이드는 아직 모델 기능으로 완성되지 않았다.  
현재는 **플랫폼 실제 랭킹/장르/태그 데이터를 수집할 수 있는지 POC 확인 중**이다.

Tavily 관련 기존 코드:

```txt
data/localization_guide/tavily_localization_agent.py
data/localization_guide/localization_orchestrator.py
```

하지만 현재 환경에는:

```txt
TAVILY_API_KEY=missing
```

즉 Tavily 기반 수집은 현재 불가능하다.

## 2.2 이번에 생성한 POC

생성 파일:

```txt
scripts/platform_observation_probe.py
data/localization_guide/platform_observation/platform_observation_poc.json
```

이 POC는 Tavily 없이 직접 웹 접근으로 플랫폼별 수집 가능성을 확인한다.

확인 대상:

- Tapas
- Royal Road
- Wattpad

## 2.3 플랫폼별 판단

### Royal Road

상태: **가능성 높음**

수집 가능한 정보:

- 랭킹 페이지 타입
- 제목
- 태그
- 팔로워 수
- 조회수
- 챕터 수
- 업데이트 날짜
- 설명문

판단:

```txt
현지화 가이드용 플랫폼 관측 데이터로 가장 먼저 구현하기 좋다.
```

다음 작업:

```txt
Royal Road ranking/listing 수집기를 먼저 정식 구현한다.
```

### Tapas

상태: **부분 가능**

확인된 것:

- `https://tapas.io/collection/novels` 접근 가능
- 정적 HTML에서 129개 결과 확인
- 장르/카테고리 분포 일부 확인 가능
- 내부 sort 값은 `SUBSCRIBE`

주의:

```txt
Tapas의 Popular/collection 결과를 조회수 랭킹이라고 단정하면 안 된다.
```

다음 작업:

```txt
Tapas의 JS/API 호출 구조를 분석해서 title/views/likes/tags를 안정적으로 가져올 수 있는지 확인한다.
```

### Wattpad

상태: **직접 수집 신뢰도 낮음**

정적 페이지 접근은 되지만, 모델용 랭킹/태그 데이터로 바로 쓰기 어렵다.

다음 선택지:

- Tavily/API 키 확보 후 검색 기반 수집
- 수동 샘플링
- 다른 공개 소스 사용
- Wattpad을 낮은 우선순위로 미룸

---

# 3. 다음 세션에서 바로 할 작업

## A안: 모델 기능부터 이어가기

추천 프롬프트:

```text
docs/next_omx_handoff.md 읽고 모델 쪽 다음 작업부터 해줘. Streamlit은 제외하고, RAG 검색 품질 테스트 문서와 번역 일관성 기능 설계부터 진행해줘.
```

작업 순서:

1. `docs/k_culture_annotation_handoff.md` 확인
2. `ko_locale_pipeline/annotation_retriever.py` 확인
3. 실제 임베딩 테스트 결과가 있으면 반영
4. 없으면 mock이 아니라 테스트 시나리오 문서부터 작성
5. 번역 일관성 기능 설계/구현 후보 정리

## B안: 현지화 가이드부터 이어가기

추천 프롬프트:

```text
docs/next_omx_handoff.md 읽고 현지화 가이드 데이터 수집 쪽부터 이어서 해줘. Royal Road 수집기를 먼저 정식화하고, Tapas는 JS/API 구조를 추가 분석해줘.
```

작업 순서:

1. `data/localization_guide/platform_observation/platform_observation_poc.json` 확인
2. `scripts/platform_observation_probe.py` 확인
3. Royal Road 수집기 정식 구현
4. 수집 결과를 RAG 문서 스키마로 정규화
5. Tapas API/JS 구조 추가 분석
6. Wattpad은 보류 또는 Tavily 키 확보 후 진행

---

# 4. 현재 판단

## 모델

K-Culture RAG는 테스트 가능한 수준까지 정리되었다.  
다음 핵심은 **실제 임베딩 품질 확인**과 **번역 일관성 기능**이다.

## 현지화 가이드

현지화 가이드는 가능성이 있다.  
다만 모든 플랫폼을 같은 방식으로 수집할 수는 없다.

현재 현실적인 전략:

```txt
Royal Road: 직접 수집 기반으로 우선 구현
Tapas: 추가 API/JS 분석 후 판단
Wattpad: Tavily/API/수동 샘플링 없으면 낮은 우선순위
```

## 다음에 가장 추천하는 시작점

```txt
Royal Road 플랫폼 관측 데이터 수집기 정식 구현
```

이유:

- 직접 수집 가능성이 가장 높음
- 랭킹/태그/조회수/팔로워 데이터가 비교적 명확함
- 현지화 가이드의 “실제 플랫폼 트렌드 근거”를 만들기 가장 좋음

---

---

# 5. 2026-06-04 platform trend collection update

Decision: the localization guide should use current trending/popular exposure, not best-rated history.

## Active source criteria

- Royal Road
  - `https://www.royalroad.com/fictions/trending`
  - `https://www.royalroad.com/fictions/weekly-popular`
- Tapas
  - `https://tapas.io/menu/3/subtab/24`
  - Treat as Tapas Novel Popular menu exposure.
  - Uses public `story-api.tapas.io/cosmos/api/v1/landing/ranking` responses.
- Japan / Shosetsuka ni Naro
  - `https://yomou.syosetu.com/rank/list/type/weekly_r/`
  - Weekly ranking.
- Thailand
  - Deferred until candidate platform structure is clearer.

## Created/updated files

```txt
scripts/collect_platform_trends.py
tests/test_platform_trend_collector.py
data/localization_guide/platform_observation/platform_trends_current.json
```

## Collection result

`platform_trends_current.json` contains 4 collections, 100 items each.

```txt
royalroad_trending: 100
royalroad_weekly_popular: 100
tapas_popular_novels: 100
syosetu_weekly: 100
total: 400
```

The collector stores public metadata only, not story body text.

Included:

- country/platform/collection
- rank or exposure order
- title
- author
- genre
- tags
- public metrics
- public synopsis/description
- status/update date
- source URL

Excluded:

- episode/story body text
- paid or locked content
- login-only data
- image downloads

## Result summary

### Royal Road Trending

- 100 items collected.
- Major tags: Action, Adventure, Progression, Fantasy, Male Lead, LitRPG, Magic.
- Status: all ONGOING.

### Royal Road Weekly Popular

- 100 items collected.
- Major tags: Adventure, Fantasy, Action, Progression, Male Lead, LitRPG, Magic.
- ONGOING 91, COMPLETED 9.

### Tapas Popular Novels

- 100 items collected.
- Major genres:
  - Romance Fantasy 47
  - Action Fantasy 22
  - BL 18
  - Romance 6
  - LGBTQ+ 5
  - Drama 4
- ON_GOING 51, COMPLETED 49.
- Tapas API response includes `description`, `viewCount`, `subscriberCount`, `likeCount`, and `rank`.

### Syosetu Weekly

- 100 items collected.
- Major genres:
  - High Fantasy category: 37
  - Isekai Romance category: 30
  - Low Fantasy category: 16
- Major tags include R15, cruel depiction warning, isekai reincarnation, male protagonist, female protagonist, happy ending, magic, western setting, cheat.

## Draft localization guide method

Use this data to generate market signals, not individual work recommendations.

Recommended analysis axes:

1. Dominant genre mix.
2. Repeated tags/tropes.
3. Title style.
4. Synopsis hook structure.
5. Protagonist and relationship codes.
6. Ongoing/completed ratio.
7. Shared traits among high-exposure works.
8. What to preserve, emphasize, soften, or avoid when localizing Korean originals for that market.

Recommended guide template:

```txt
Country/platform current trend summary
Dominant genres and tropes
Popular synopsis patterns
Title/copywriting tendencies
Localization emphasis points
Localization caution points
Korean-original mapping examples
Evidence/source/date
```

## Verification

```txt
python -m unittest tests.test_platform_trend_collector
python -m unittest tests.test_platform_trend_collector tests.test_k_culture_rag
python -m py_compile scripts/collect_platform_trends.py tests/test_platform_trend_collector.py
```

Result:

```txt
12 tests OK
py_compile OK
```

## Next recommended work

1. Build the localization guide generator/prompt module using `summary_by_collection` and `rag_documents` from `platform_trends_current.json`.
2. Create country-specific output templates.
3. Add Thailand after platform candidates are selected.
4. Keep Selenium/Playwright as a fallback only; current Tapas API is enough for the popular-novel page.

---

# 6. 2026-06-05 localization guide generator update

Next task completed: `platform_trends_current.json` is now converted into a deterministic localization-guide draft and a model/API prompt payload.

## Created/updated files

```txt
data/localization_guide/platform_trend_guide.py
scripts/generate_platform_trend_guide.py
tests/test_platform_trend_guide.py
data/localization_guide/platform_observation/platform_trend_localization_guide.md
data/localization_guide/platform_observation/platform_trend_guide_prompt.json
```

## What the generator does

Input:

```txt
data/localization_guide/platform_observation/platform_trends_current.json
```

Outputs:

```txt
platform_trend_localization_guide.md
platform_trend_guide_prompt.json
```

The markdown report summarizes:

- method / evidence boundary
- executive summary by country
- country/platform notes
- dominant genres
- dominant tags/signals
- synopsis/title repeated terms
- adaptation guidance
- caution points
- recommended prompt/output shape

The prompt JSON includes:

- `role: localization_guide_generator`
- source snapshot timestamp
- safety/evidence policy
- country profiles
- sampled RAG evidence documents by platform collection
- required model output sections

Required model output sections:

```txt
market_trend_fit
genre_trope_alignment
title_synopsis_localization
terminology_glossary_risks
content_rating_sensitivity
adaptation_checklist
evidence_used
```

## Important design decision

This is deterministic and does not require Tavily/OpenAI keys. It only uses the already-collected public platform trend metadata.

It deliberately limits claims:

```txt
Do not claim national readership certainty; phrase as platform trend evidence.
```

Evidence allowed:

- public rank/exposure metadata
- title
- genre
- tags
- public metrics
- public synopsis/description

Evidence excluded:

- episode/story body text
- paid or locked content
- login-only data
- image downloads

## Validation

```txt
python -m unittest tests.test_platform_trend_collector tests.test_platform_trend_guide tests.test_k_culture_rag
python -m py_compile data/localization_guide/platform_trend_guide.py scripts/generate_platform_trend_guide.py tests/test_platform_trend_guide.py
python scripts/generate_platform_trend_guide.py
```

Result:

```txt
17 tests OK
py_compile OK
profiles: 2
evidence groups: 4
required sections: 7
Japan isekai signal detected: true
```

## Next recommended task

Wire this into the API/model side:

1. Add an API/server function that loads `platform_trend_guide_prompt.json`.
2. Accept Korean original metadata: target country/platform, genre, synopsis, tags, age rating, and optional glossary.
3. Retrieve relevant `rag_documents` or prompt evidence by target country/platform.
4. Ask the model to produce the seven required sections.
5. Return both the user-facing guide and evidence references.

Keep Streamlit excluded.

---

# 7. 2026-06-05 API/model localization guide routing update

User requested the five API/model-side steps, with two product flows:

1. If there is no synopsis: ask/select country + genre first, then generate a guide from the selected country/genre.
2. If there is a synopsis: use synopsis + genre to recommend the best-fit country, then generate the guide.

## Implemented files

```txt
data/localization_guide/platform_trend_advisor.py
api_server.py
tests/test_platform_trend_advisor.py
```

## API behavior

`api_server.guide(payload)` now delegates to `build_localization_advice(payload)`.

### Flow A: no synopsis and no country

Input example:

```json
{"genre": "romance fantasy"}
```

Output:

```txt
mode: needs_country_and_genre_selection
requiresSelection: true
availableOptions: countries + genres
```

This tells the UI/API layer to make the user choose country and genre first.

### Flow B: no synopsis, selected country + genre

Input example:

```json
{"targetCountry": "US", "genre": "LitRPG"}
```

Output:

```txt
mode: country_genre_guide
requiresSelection: false
targetCountry: normalized country
sections: seven required guide sections
evidenceUsed: platform trend evidence
modelPromptPayload: model-ready payload
htmlReport: user-facing report
```

### Flow C: synopsis exists

Input example:

```json
{"genre": "romance fantasy", "synopsis": "..."}
```

Output:

```txt
mode: synopsis_country_recommendation
recommendedCountries: ranked candidates
targetCountry: top recommendation unless user explicitly selected one
sections: seven required guide sections
evidenceUsed: matched platform trend evidence
modelPromptPayload: model-ready payload
htmlReport: user-facing report
```

## Seven guide sections returned

```txt
market_trend_fit
genre_trope_alignment
title_synopsis_localization
terminology_glossary_risks
content_rating_sensitivity
adaptation_checklist
evidence_used
```

## Evidence and matching

The advisor uses:

- country/platform trend records from `platform_trends_current.json`
- genre aliases, including Korean inputs like romance fantasy / LitRPG / isekai equivalents
- synopsis motif keywords, including romance, progression/system, isekai/reincarnation, action/survival, BL/Omegaverse signals
- ranked evidence rows from public metadata only

No story body text is collected or used.

## Backward compatibility

`/api/guide` still returns:

```txt
htmlReport
writingDirection
cultureNotes
platformRules
localizationTips
tags
```

so older UI/tests can keep reading familiar fields, while the new API also returns:

```txt
mode
requiresSelection
recommendedCountries
sections
evidenceUsed
modelPromptPayload
```

## Validation

Passed:

```txt
python -m unittest tests.test_platform_trend_advisor
python -m unittest tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_platform_trend_collector tests.test_model_acceptance_from_docs tests.test_model_feature_backlog tests.test_k_culture_rag
python -m py_compile api_server.py data/localization_guide/platform_trend_advisor.py data/localization_guide/platform_trend_guide.py scripts/generate_platform_trend_guide.py tests/test_platform_trend_advisor.py
```

Results:

```txt
5 advisor tests OK
33 related tests OK
py_compile OK
```

The obsolete Streamlit reference-layout tests were removed after the Streamlit prototype was retired. The relevant API/model/localization tests pass.

## Next recommended task

Wire the Next.js UI to the new `/api/guide` fields:

1. If `requiresSelection=true`, show country/genre choices.
2. If `mode=synopsis_country_recommendation`, show recommended countries and selected top target.
3. Render the seven `sections` and `evidenceUsed`.
4. Keep `htmlReport` as a backward-compatible rich preview.
5. Optionally send `modelPromptPayload` to an OpenAI model endpoint when live generation is enabled.

---

# 8. 2026-06-05 Streamlit prototype removal update

Decision: Streamlit is no longer an active product surface. The old prototype created test noise and file-navigation confusion, so it was removed.

## Removed Streamlit-only files

```txt
app.py
app_v2.py
app_sections/
streamlit_app.err.log
streamlit_app.out.log
```

## Removed Streamlit-only tests

```txt
tests/test_app_split.py
tests/test_rag_review_rows.py
tests/test_reference_layout_pages.py
tests/test_workspace_persistence.py
```

## Updated docs/dependencies

```txt
README.md
requirements.txt
docs/model_code_test_guide.md
docs/k_culture_annotation_handoff.md
docs/next_omx_handoff.md
```

`requirements.txt` no longer includes Streamlit.

## Active development surfaces now

```txt
api_server.py
frontend/
ko_locale_pipeline/
data/localization_guide/
scripts/
tests/  # API/model/pipeline only
```

Do not add new Streamlit pages or Streamlit layout tests.




---

# 9. 2026-06-05 Next.js guide UI integration update

Next.js is now wired to the new `/api/guide` API/model-side localization guide response fields.

## Updated files

```txt
frontend/components/ApiPanels.tsx
frontend/app/workspace/guide/page.tsx
frontend/app/globals.css
```

## Implemented UI behavior

- Guide form now accepts target country, genre, and optional synopsis.
- No synopsis + no country:
  - UI renders `requiresSelection=true` and country choices from `availableOptions`.
- Selected country + genre:
  - UI renders `mode=country_genre_guide` output.
- Synopsis exists:
  - UI renders `mode=synopsis_country_recommendation` output.
  - Recommended country candidates are displayed with scores.
  - User can click another recommended country to regenerate for that country.
- The seven API/model guide `sections` are rendered in stable order:
  - `market_trend_fit`
  - `genre_trope_alignment`
  - `title_synopsis_localization`
  - `terminology_glossary_risks`
  - `content_rating_sensitivity`
  - `adaptation_checklist`
  - `evidence_used`
- `evidenceUsed` is rendered as evidence reference cards.
- Existing `htmlReport` is kept as a collapsible backward-compatible preview.
- Guide history remains localStorage-based for now.

## Validation

```txt
npm run typecheck
npm run build
python -m unittest tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_platform_trend_collector tests.test_model_acceptance_from_docs tests.test_model_feature_backlog tests.test_k_culture_rag
```

Result:

```txt
Next typecheck OK
Next production build OK
33 API/model/localization tests OK
```

Note: `npm run build` initially failed inside sandbox with `EPERM: operation not permitted, lstat 'C:\Users\kwonm'`; rerun with approved escalation succeeded. This was a sandbox path resolution issue, not a code/build issue.

---

# 10. 2026-06-05 requirements workbook status review

User clarified that the actual requirements source is:

```txt
C:\Users\kwonm\Downloads\requirements workbook: ???????_skn24-5team.xlsx
```

For analysis, the workbook was copied to an ASCII temporary path because Python stdin/path handling garbled the Korean filename:

```txt
.omx/requirements_skn24_5team.xlsx
.omx/final_requirements.json
```

Use the last sheet only: final requirements sheet.

The final sheet contains 35 requirements:

```txt
user/auth management: 6
payment/credit management: 4
work/product features: 25
total: 35
```

## Current implementation status summary

```txt
implemented: 3
partial: 16
not implemented: 16
```

## Implemented

```txt
REQ-WORK-001 work creation
REQ-WORK-002 work list
REQ-WORK-003 work detail
```

## Partially implemented

```txt
REQ-CRED-002 credit balance display: static header only, no ledger/API
REQ-WORK-004 work update: API/UI exists, but no auth/DB persistence
REQ-WORK-005 work delete: API/UI exists, but no auth/DB persistence
REQ-CHAP-001 episode create: direct text only; upload UI is placeholder
REQ-CHAP-002 episode list: API/UI exists
REQ-CHAP-003 episode detail: no dedicated detail endpoint/page; body appears in list payload
REQ-CHAP-006 translation execution: API/UI/pipeline exists, but no credit/auth/full episode binding
REQ-CHAP-007 inspection chatbot: API/UI exists, but persistence is limited
REQ-CHAP-008 translation version list: API exists, UI limited
REQ-CHAP-009 translation version delete: API exists, UI limited
REQ-IMG-001 cover image generation: API exists; UI alignment incomplete
REQ-IMG-004 relation map generation: API/UI exists
REQ-IMG-005 relation map list/view: localStorage only
REQ-IMG-006 relation map delete: localStorage only
REQ-GDE-001 localization guide generation: API/UI exists
REQ-GDE-002/003/005 localization guide list/detail/delete: localStorage only, not server-backed
```

Important caveat: `frontend/app/workspace/character/page.tsx` calls:

```txt
/api/generate-character-image
```

but `api_server.py` currently exposes:

```txt
/api/generate-cover-image
/api/generate-relation-image
```

So the character image workspace likely has an endpoint mismatch. Also, the final requirements mention cover image, not character image, so image requirements need product alignment.

## Not implemented

```txt
REQ-AUTH-001 login
REQ-AUTH-002 logout
REQ-USER-001 signup
REQ-USER-002 user profile view
REQ-USER-003 user profile update
REQ-USER-004 account withdrawal
REQ-CRED-001 credit charging/payment
REQ-CRED-003 credit deduction
REQ-CRED-004 payment cancellation/refund
REQ-CHAP-004 episode update
REQ-CHAP-005 episode delete
REQ-IMG-002 cover image list/view
REQ-IMG-003 cover image delete
REQ-GDE-004 localization guide download
```

Main missing axes:

```txt
auth/session/user management
payment/credit ledger
DB persistence and user ownership
episode update/delete
server-backed generated artifact storage/list/detail/delete/download
image feature alignment: cover vs character
```

---

# 11. 2026-06-05 Tailwind / shadcn UI and MCP update

User asked whether replacing current CSS with Tailwind CSS + shadcn/ui is beneficial.

Current judgement:

```txt
Yes, likely beneficial for app/workspace/dashboard/admin-style product surfaces.
Do not necessarily fully shadcn-ize the landing page; landing can keep custom brand styling.
Recommended direction: Tailwind + shadcn for internal app UI, custom brand treatment for landing/hero visuals.
```

Reasoning:

- `frontend/app/globals.css` is already large and centralized.
- Future requirements require many forms, tables, cards, dialogs, selectors, tabs, sheets, toasts, and data-management screens.
- shadcn/ui is a Tailwind-based component recipe set, not just colors.
- Tailwind is highly customizable; w.LiGHTER's purple/pink/glass brand can be preserved via theme tokens and className overrides.
- shadcn defaults can look generic SaaS/admin if used without brand customization.

## shadcn MCP registration

Registered globally for Codex:

```txt
codex.cmd mcp add shadcn -- npx -y shadcn@latest mcp
```

Verification:

```txt
codex.cmd mcp list
codex.cmd mcp get shadcn
npx -y shadcn@latest mcp --help
```

Codex config now contains:

```toml
[mcp_servers.shadcn]
command = "npx"
args = ["-y", "shadcn@latest", "mcp"]
```

Notes:

- `codex.ps1` is blocked by PowerShell execution policy, so use `codex.cmd` on Windows.
- `codex.cmd` needed sandbox escalation because Node realpath access to `C:\Users\kwonm` is blocked in sandbox.
- The MCP server is registered, but the current Codex session did not expose new MCP tools immediately. Restart the Codex session, then check whether shadcn MCP tools are available.
- `npx -y shadcn@latest mcp init --client codex` exists, but it was not run to avoid duplicate registration because `codex mcp add` already succeeded.

---

# 12. Suggested next prompt after session restart

```txt
Read docs/next_omx_handoff.md and continue. Exclude Streamlit; focus only on API/Next.js/model. First check whether shadcn MCP is exposed in the new session, then prioritize next work from the final requirements workbook. Do not touch Git yet.
```

Recommended next implementation options:

1. Fix image feature alignment first:
   - either rename/repurpose character workspace into cover image workspace, or add `/api/generate-character-image` deliberately;
   - align with final requirements `REQ-IMG-001~006`.
2. Add episode update/delete API + UI:
   - `REQ-CHAP-004`, `REQ-CHAP-005`.
3. Add localization guide download:
   - `REQ-GDE-004`.
4. Plan server-backed artifact storage for guide/image outputs:
   - replace localStorage-only history with API-backed list/detail/delete.
5. Treat auth/credit/payment as a larger separate design task.


---

# 13. 2026-06-05 image alignment and guide download update

Completed after MCP restart check. shadcn MCP is connected, but no shadcn/Tailwind UI migration was started; current priority remains feature completion.

## Image requirement alignment

Updated files:

```txt
frontend/app/workspace/character/page.tsx
frontend/components/data.ts
```

Changes:

- Reworked the former character image workspace into a cover image workflow aligned with `REQ-IMG-001`.
- The UI now calls the existing API endpoint:

```txt
/api/generate-cover-image
```

- Removed the frontend mismatch that called the non-existent endpoint:

```txt
/api/generate-character-image
```

- Navigation label now shows the workspace as cover/표지 while preserving the existing route for now:

```txt
/workspace/character
```

- The cover UI sends work title, target country, genre, protagonist/subject, traits, appearance, synopsis summaries, symbols, mood, and extra prompt to the cover-image API.
- Mock image and refusal responses are handled explicitly.
- Local image history key changed to cover-focused localStorage history:

```txt
cover_image_history
```

## Localization guide download

Updated file:

```txt
frontend/components/ApiPanels.tsx
```

Changes:

- Added client-side guide export/download for `REQ-GDE-004`.
- Current generated guide can now be downloaded as:

```txt
Markdown
JSON
```

- Markdown export includes guide title, mode, country, genre, synopsis, recommended countries, ordered seven sections, evidence references, and the evidence-boundary note.
- JSON export downloads the complete current API result object.

## Validation

Passed:

```txt
npm run typecheck
npm run build
python -m unittest tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_platform_trend_collector tests.test_model_acceptance_from_docs
```

Results:

```txt
Next typecheck OK
Next production build OK
21 API/model/localization tests OK
```

## Notes

- No Git commit was made.
- `git status`/`git diff` from this Windows path failed because Git resolved the Korean/space path incorrectly as `C:/Users/kwonm`; use an ASCII path copy or a shell/session with correct Unicode path handling if a clean diff is needed.
- Some older UI strings in `frontend/components/ApiPanels.tsx` are still mojibake from previous encoding damage. The touched guide helper labels and the new download buttons are valid, and the build passes.

## Next recommended task

Continue localization guide/product requirements:

1. Server-backed guide history/list/detail/delete to replace localStorage-only behavior for `REQ-GDE-002/003/005`.
2. Then server-backed generated artifact storage/list/delete for image outputs `REQ-IMG-002/003/005/006`.
3. Keep auth/credit/payment as a separate larger design task.

---

# 14. 2026-06-05 translation consistency glossary update

Implemented the translation consistency layer for noun/proper-noun terminology.

## Scope

Goal: keep named entities and fixed noun phrases consistent across episodes without forcing verbs, adjectives, sentence shape, or ordinary stylistic variation.

## Implemented behavior

Updated files:

```txt
ko_locale_pipeline/terminology.py
ko_locale_pipeline/consistency_checker.py
api_server.py
frontend/components/ApiPanels.tsx
tests/test_translation_consistency_glossary.py
```

### Glossary policies

Added three glossary policies:

```txt
locked      exact fixed form required when a target exists
preferred   preferred form recommended; allowed variants pass
contextual  reference-only; not enforced by consistency checker
```

### Named noun phrase extraction

Added conservative Korean noun-phrase extraction for named entities such as:

```txt
사랑 약국
동소문 시장
백월 길드
한빛 고등학교
김첨지
```

Rules:

- Longer named phrases are prioritized before shorter/common nouns.
- A common noun inside a name is locked as part of the full phrase.
- Generic phrases such as `근처 약국` are not locked as a business name.
- Common nouns such as `약국` can still exist as preferred/contextual hints with allowed variants like `pharmacy`, `drugstore`, `chemist`.

Example distinction:

```txt
사랑 약국 -> Sarang Pharmacy   locked business_name
약국 -> pharmacy / drugstore   preferred common_noun
```

### Translation prompt context

When `translate()` receives `workId`, the API now:

1. Loads work memory.
2. Extracts normal context plus named-entity glossary candidates.
3. Upserts candidates into `memory.terms`.
4. Renders glossary context into the translation prompt memory block.
5. Sorts locked/longer terms before preferred/common terms.

Prompt rules include:

```txt
- Apply longer source phrases before shorter/common nouns.
- LOCKED terms must use the exact target form when a target is present.
- PREFERRED terms should use the preferred target; allowed variants are acceptable.
- CONTEXTUAL terms are reference-only.
- Do not enforce verbs, adjectives, ordinary style, or sentence structure as glossary items.
```

### Post-translation consistency check

`check_translation_consistency()` now evaluates policy-aware glossary rows:

- `locked`: expected target must appear if source appears.
- `preferred`: expected or allowed variant passes.
- `contextual`: skipped / reference-only.

It returns:

```txt
status
checked
skipped
issues
summary
```

### Next.js UI

The translate panel now renders:

```txt
Terminology consistency: PASS/WARNING
checked glossary terms
found target/variant
warning messages
```

## Validation

Passed:

```txt
python -B -m py_compile api_server.py ko_locale_pipeline/terminology.py ko_locale_pipeline/consistency_checker.py tests/test_translation_consistency_glossary.py
python -B -m unittest tests.test_translation_consistency_glossary
python -B -m unittest tests.test_translation_consistency_glossary tests.test_terminology tests.test_model_acceptance_from_docs tests.test_k_culture_rag
npm run typecheck
npm run build
```

Results:

```txt
new glossary consistency tests: 4 OK
related Python tests: 21 OK
Next typecheck OK
Next production build OK
```

## Manual test guidance

For a proper live test, do not use `WLIGHTER_MOCK_MODE=true`.

Recommended TST-TRANS-003 flow:

1. Start API with OpenAI key and mock mode disabled.
2. Create/select a work.
3. Confirm or insert glossary row in work memory, for example:

```json
{
  "source": "김첨지",
  "recommendedTranslation": "คิม ช็อมจี",
  "policy": "locked",
  "type": "person_name",
  "status": "confirmed"
}
```

4. Translate episode 1 with `workId`.
5. Translate episode 2 with the same `workId`.
6. Check the UI `Terminology consistency` panel and response `workflow.consistency`.

For named business/place phrases:

```txt
사랑 약국 -> locked full phrase
약국 -> preferred common noun with allowed variants
```

`Sarang Drugstore` should be warned if glossary says `사랑 약국 -> Sarang Pharmacy`.

---

## 2026-06-05 Structure refactor note

Goal: make future feature ownership easier without changing runtime behavior.

### What changed

Frontend feature boundaries were introduced:

```txt
frontend/features/shared/api.ts
frontend/features/translate/TranslateConnector.tsx
frontend/features/guide/GuideConnector.tsx
frontend/features/prompt/PromptConnector.tsx
frontend/components/ApiPanels.tsx   # compatibility re-export only
```

Backend service boundaries were introduced:

```txt
backend/services/image_service.py   # cover/relation image generation endpoints
backend/services/guide_service.py   # localization guide generation endpoint
```

`api_server.py` remains the HTTP router and temporary in-memory store owner, but dead legacy static guide code and image-generation OpenAI client leftovers were removed.

### Current structure assessment

Still not ideal for large parallel work. The biggest shared-conflict files are:

```txt
api_server.py                         # router + in-memory storage + translate + cover plan
frontend/app/globals.css              # large global style surface
frontend/app/workspace/translate/page.tsx
frontend/app/workspace/character/page.tsx
frontend/app/workspace/relation/page.tsx
frontend/app/works/[id]/page.tsx
```

### Recommended next split order

1. Move API storage/state into `backend/store/` or `backend/repositories/`.
2. Move translation workflow into `backend/services/translation_service.py` with injected storage callbacks.
3. Move cover planning into `backend/services/cover_plan_service.py`.
4. Split large page components into `frontend/features/<feature>/components/*` and keep `app/**/page.tsx` as thin route shells.
5. Split `globals.css` by feature or migrate repeated blocks into component-level class groups before any visual redesign.

### Validation after refactor

Passed:

```txt
python -B -m py_compile api_server.py backend/services/image_service.py backend/services/guide_service.py
python -B -m unittest tests.test_translation_consistency_glossary tests.test_terminology tests.test_model_acceptance_from_docs tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_platform_trend_collector tests.test_k_culture_rag tests.test_retriever_anchor_priority
npm run typecheck
npm run build
```

Results:

```txt
Python selected suite: 42 tests OK
Next typecheck OK
Next production build OK
```

---

## 2026-06-05 Full feature-boundary split

Goal: complete the previously listed split order so future parallel work does not keep colliding in one router, one page file, or one global stylesheet.

### Backend ownership after split

```txt
api_server.py                         # thin stdlib HTTP router only
backend/store/memory_store.py         # process-local MVP repository/state
backend/services/translation_service.py
backend/services/cover_plan_service.py
backend/services/image_service.py
backend/services/guide_service.py
```

Notes:

- `api_server.py` no longer owns work/episode/translation/chat/cover-plan arrays directly.
- Translation, work memory extraction, and inspector chat moved to `translation_service.py`.
- Cover planning moved to `cover_plan_service.py`.
- Cover/relation image generation remains in `image_service.py`.
- Localization guide generation remains in `guide_service.py`.
- The store is still in-memory and demo-grade; replacing it with SQLite/Postgres should target `backend/store/` first.

### Frontend ownership after split

Route files are now thin shells. Feature implementation lives under `frontend/features/`:

```txt
frontend/features/home/LandingPage.tsx
frontend/features/dashboard/DashboardPage.tsx
frontend/features/works/NewWorkPage.tsx
frontend/features/works/WorkDetailPage.tsx
frontend/features/episodes/NewEpisodePage.tsx
frontend/features/translate/TranslateWorkspace.tsx
frontend/features/cover/CoverImageWorkspace.tsx
frontend/features/relation/RelationWorkspace.tsx
frontend/features/guide/GuideConnector.tsx
frontend/features/prompt/PromptConnector.tsx
frontend/features/shared/api.ts
```

Thin routes now remain under `frontend/app/**/page.tsx` so Next routing stays stable while feature owners work in their own folders.

### CSS ownership after split

`frontend/app/globals.css` is now an ordered import shell:

```txt
frontend/styles/00-foundation-shell.css
frontend/styles/10-dashboard-works.css
frontend/styles/20-visual-workspaces.css
frontend/styles/30-translation-chat.css
frontend/styles/40-landing-overrides.css
frontend/styles/50-guide-document.css
frontend/styles/60-modals-guide-advanced.css
```

The split preserves the original cascade order to reduce visual-regression risk. Future visual cleanup should gradually move styles from these ordered files into feature-specific component/CSS modules when touching a feature.

### Size impact

```txt
api_server.py: about 40KB -> about 8.9KB
frontend/app/globals.css: about 49KB -> import shell only
frontend/app/**/page.tsx: route shells only, mostly under 250 bytes
```

### Validation

Passed after the full split:

```txt
python -B -m py_compile api_server.py backend/store/memory_store.py backend/services/translation_service.py backend/services/cover_plan_service.py backend/services/guide_service.py backend/services/image_service.py
python -B -m unittest tests.test_translation_consistency_glossary tests.test_terminology tests.test_model_acceptance_from_docs tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_platform_trend_collector tests.test_k_culture_rag tests.test_retriever_anchor_priority
npm run typecheck
npm run build
```

Results:

```txt
Python selected suite: 42 tests OK
Next typecheck OK
Next production build OK
```

---

## 2026-06-05 KURE embedding migration update

Goal: switch retrieval defaults from OpenAI `text-embedding-3-large` to the selected local KURE embedding model and use the KURE-ready RAG document schema.

### What changed

Updated files:

```txt
ko_locale_pipeline/config.py
ko_locale_pipeline/locales.py
ko_locale_pipeline/retriever.py
ko_locale_pipeline/annotation_retriever.py
requirements.txt
tests/test_retriever_anchor_priority.py
tests/test_k_culture_rag.py
```

Default embedding configuration now follows `C:\Users\kwonm\Downloads\embedding_model_summary.md`:

```txt
embedding_model: nlpai-lab/KURE-v1
retrieval top_k: 5
K-Culture annotation threshold: 0.55
JP idiom threshold: 0.60
US idiom threshold: 0.60
CN idiom threshold: 0.55
TH idiom threshold: 0.55
```

Idiom RAG locale paths now point to the KURE-ready `embedding_text` / `context_text` files:

```txt
data/legacy_idiom_rag/raw_enriched/jp_idiom_embedding_anchor_meaning.json
data/legacy_idiom_rag/raw_enriched/us_idiom_embedding_anchor_meaning.json
data/legacy_idiom_rag/raw_enriched/cn_idiom_embedding_anchor_meaning.json
data/legacy_idiom_rag/raw_enriched/th_idiom_embedding_anchor_meaning.json
```

K-Culture annotation RAG continues to use:

```txt
data/annotation_rag/kculture_rag_documents_reviewed.json
```

`DenseRetriever` now prefers `embedding_text` as the indexed search text and renders `context_text` in the model prompt context. Legacy `ko_anchor_expression` / `ko_expression` datasets remain supported for tests/custom datasets, but exact lexical boost is disabled for the new `embedding_text` / `context_text` schema.

Live non-mock retrieval now uses a lazy `sentence-transformers` backend for non-OpenAI embedding model names. `requirements.txt` includes:

```txt
sentence-transformers>=3.0
```

### Validation

Passed:

```txt
python -B -m py_compile api_server.py ko_locale_pipeline/config.py ko_locale_pipeline/locales.py ko_locale_pipeline/retriever.py ko_locale_pipeline/annotation_retriever.py ko_locale_pipeline/pipeline.py tests/test_retriever_anchor_priority.py tests/test_k_culture_rag.py
python -B -m unittest tests.test_k_culture_rag tests.test_retriever_anchor_priority
python -B -m unittest tests.test_translation_consistency_glossary tests.test_terminology tests.test_model_acceptance_from_docs tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_platform_trend_collector tests.test_k_culture_rag tests.test_retriever_anchor_priority
python -c "import importlib.util; print('sentence_transformers', bool(importlib.util.find_spec('sentence_transformers')))"
```

Results:

```txt
py_compile OK
20 retriever/K-Culture tests OK
47 selected Python tests OK
sentence_transformers True
```

### Remaining note

The environment has the `sentence-transformers` package installed. If `nlpai-lab/KURE-v1` weights are not already cached, the first live non-mock retrieval may download the model from Hugging Face.

---

## 2026-06-05 priority 1-4 completion update

User asked to proceed through priority 4 from the post-KURE next-work list:

1. KURE live retrieval smoke.
2. Server-backed localization guide history/list/detail/delete.
3. Server-backed generated image artifact list/detail/delete.
4. Episode update/delete.

### KURE live smoke

Ran a non-mock temporary-dataset retrieval using:

```txt
embedding_model: nlpai-lab/KURE-v1
backend: SentenceTransformerEmbeddingBackend
```

Result:

```txt
KURE_SMOKE_1 returned first with similarity 0.9817
KURE_SMOKE_2 returned second with similarity 0.9596
```

This confirms the local `sentence-transformers` KURE backend loads and retrieves without mock mode in the current environment.

### Localization guide server backing

Already wired API/frontend behavior was verified and one missing dashboard detail was fixed:

```txt
backend/store/memory_store.py
api_server.py
frontend/features/guide/GuideConnector.tsx
```

Behavior:

- `POST /api/guide` saves a guide record.
- `GET /api/localization-guides` lists saved guide records.
- `GET /api/localization-guides/{id}` returns detail.
- `DELETE /api/localization-guides/{id}` deletes a guide.
- `dashboard_summary().guideCount` now reflects saved guide count instead of always returning 0.

### Generated image artifact server backing

Verified and completed:

```txt
backend/store/memory_store.py
api_server.py
frontend/features/cover/CoverImageWorkspace.tsx
frontend/features/relation/RelationWorkspace.tsx
```

Behavior:

- cover/relation image generation saves server-side asset records in mock/live success paths.
- `GET /api/generated-assets?kind=cover|relation&workId=...` lists records.
- `GET /api/generated-assets/{id}` now returns detail.
- `DELETE /api/generated-assets/{id}` deletes records.
- cover/relation workspaces load/delete server-backed history.

### Episode update/delete

Verified existing API/frontend implementation:

```txt
backend/store/memory_store.py
api_server.py
frontend/features/works/WorkDetailPage.tsx
```

Behavior:

- `PUT /api/works/{workId}/episodes/{episodeId}` updates title/body.
- `DELETE /api/works/{workId}/episodes/{episodeId}` deletes the episode and related translation/chat records.
- Work detail UI exposes edit/delete actions.

### Added tests

New file:

```txt
tests/test_server_backed_requirements.py
```

Coverage:

- guide save/list/detail/delete + dashboard guide count
- generated asset save/list/detail/delete
- episode create/update/detail/delete

### Validation

Passed:

```txt
python -B -m unittest tests.test_server_backed_requirements
python -B -m py_compile api_server.py backend/store/memory_store.py tests/test_server_backed_requirements.py
python -B -m unittest tests.test_server_backed_requirements tests.test_k_culture_rag tests.test_retriever_anchor_priority tests.test_translation_consistency_glossary tests.test_terminology tests.test_model_acceptance_from_docs tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_platform_trend_collector
npm run typecheck
npm run build
```

Results:

```txt
server-backed requirement tests: 3 OK
selected Python suite: 50 OK
Next typecheck OK
Next production build OK
```

After build verification, `frontend/.next/` was removed again to keep generated artifacts out of the workspace.

### Next recommended work

Proceed to priority 5:

```txt
KURE/RAG evaluation hardening, especially CN/TH relaxed-positive evaluation and threshold review.
```

Then priority 6:

```txt
Auth/user/credit/payment design before implementation.
```

