# 번역 API 응답 — 화면설계 팀 인계 (학원학교물_1 / 미국)

> **이 문서의 JSON = 프런트가 `POST /api/translate`에서 실제로 받는 응답 그대로다.**
> `api_server`가 내부 `translate()` 결과 dict를 가공 없이 전송한다(`self._send(status, result)`).
> 원본: `outputs/screen_handoff_학원학교물_1_ko_en_us.json`

## 1. 요청 (프런트 → 백엔드)

```json
POST /api/translate
{
  "sourceText": "<한국어 원문>",
  "targetCountry": "US",        // 또는 "targetLocale": "ko_en_us"
  "workId": "...",              // 선택(용어집 hydrate용)
  "episodeId": "..."            // 선택
}
```
- `sourceText`, (`targetCountry` 또는 `targetLocale`) 필수.
- `mode`는 보내지 않는다(항상 v3 단일 파이프라인).

## 2. 응답 top-level 필드 (총 12개 — 이게 전부다)

| 필드 | 타입 | 이번 결과 | 화면 용도 |
|---|---|---|---|
| `finalTranslation` | string | 4,434자 | **화면 중심** — 독자에게 보여줄 최종 번역문 |
| `deliveryStatus` | string | `deliverable` | 렌더 분기 키. `deliverable`/`qa_warning`/`blocked_translation_safety`/`blocked_translation_integrity` |
| `userVisibleErrorCode` | string\|null | null | 사용자 노출용 오류 코드(정상 null) |
| `message` | string | "" | blocked 시 안내 문구 |
| `translationRationale` | object | 채워짐 | "왜 이렇게 번역했는지" 패널 + **챗봇 입력** (개요/문체의도/직역·의역 비율/항목) |
| `readerEndnotes` | array | **9개** | 한국 문화 표현 독자용 각주 (kculture RAG→LLM). **0~N개 가변** |
| `authorReviewCards` | array | 0개 | 작가/편집자 read-only 검수 카드. 0~N개 가변 |
| `qaIssues` | array | 0개 | 검수 이슈. 0~N개 가변 |
| `metadata` | object | 채워짐 | 카운트/진단 요약 |
| `country` / `locale` / `pipeline` | string | US / ko_en_us / v3_literary_package | 메타 |

> **`internal`(그래프 트레이스 등 디버그)은 기본 응답에 없다.** 필요 시 요청에 `"includeInternal": true`를 넣으면 포함된다(개발/디버그용). 화면에선 쓰지 않는다.

## 3. finalTranslation (미리보기)

> "Hey, Jinwoo Kim! The crosswalk light's changing. Run!"
> Lee Minjae shouted, pulling the zipper of his puffer jacket all the way up to his chin. …(총 4,434자)

## 4. translationRationale (번역 의도 — 챗봇/패널용)

```json
{
  "title": "왜 이렇게 번역했는지",
  "overview": "원문의 의미를 보존하되 관용어와 장르 문체는 목표 언어에서 자연스럽게 읽히도록 조정했습니다.",
  "styleIntent": "대사와 서술의 속도를 살리고, 과도한 직역보다 웹소설 독자의 몰입감을 우선합니다.",
  "strategyRatio": { "literal": 55, "adaptive": 45 },
  "items": [ { "sourceSpan": "", "targetSpan": "", "category": "style", "strategy": "balanced", "explanation": "..." } ]
}
```
→ 직역 55% : 의역 45% 비율 시각화 + 설명 패널로 활용 가능. **챗봇에 이 객체를 그대로 넘기면 "왜 이렇게 번역했나" 답변 가능.**

## 5. readerEndnotes (한국 문화 각주 — 이번 핵심)

이번 실행에서 kculture RAG가 한국 문화 표현 9개를 찾아 LLM이 **장면 맥락에 녹인 영어 각주**를 작성했다. 항목 형태:

```json
{
  "noteId": 1,
  "sourceSpan": "학원 문화",
  "targetSpan": "this grueling after-school academy culture",
  "category": "custom",
  "note": "In Korea, an \"academy\" (hakwon) is a private after-school cram school. Students often go there late into the evening... an entire shadow education system, not just a tutoring class.",
  "retrievalRefs": [],
  "confidence": "high",
  "targetSpanFound": false
}
```
- `note`는 **목표 독자 언어(영어)** 로 작성된다. 화면엔 각주/툴팁/하단 노트로 렌더.
- `finalTranslation`에 합쳐지지 않는다(별도 필드). 다운로드/뷰어 레이어가 각주로 표시.
- `targetSpanFound=true`일 때만 `targetSpan` 하이라이트를 신뢰(정렬 계약). 이번엔 false라 인라인 하이라이트는 강제 X, 각주 표시만.

## 6. metadata (진단 요약 — 실제 값)

```json
{ "mode": "v3_literary_package", "deliveryStatus": "deliverable",
  "idiom_note_count": 0, "qa_issue_count": 0, "translation_rationale_item_count": 1,
  "work_memory_glossary_count": 0, "work_memory_source": "none" }
```

## 7. blocked 상태 규칙 (화면 분기)

`deliveryStatus`가 `blocked_translation_safety`/`blocked_translation_integrity`이면:
- `finalTranslation=""`, `readerEndnotes=[]`, `authorReviewCards=[]`, `qaIssues=[]`, `translationRationale={}`.
- 번역문 숨기고 `message`/`userVisibleErrorCode`로 안내만.

## 8. 화면설계 체크리스트

- [ ] `deliveryStatus`로 먼저 렌더 분기.
- [ ] `finalTranslation` 본문 + `translationRationale` "번역 의도" 패널.
- [ ] `readerEndnotes`는 **0~N개 가변** 영역(각주/노트). 이번 데이터처럼 여러 개 뜰 수 있음.
- [ ] `authorReviewCards`·`qaIssues`도 0~N 가변 리스트.
- [ ] 챗봇에는 `sourceText` + `finalTranslation` + `translationRationale` + `readerEndnotes`를 넘기면 됨.
- [ ] `internal`은 받지 않음(디버그 전용, `includeInternal=true`로만).

## 9. 정식 계약 참조
- `docs/translation_api_contract.md`, `docs/django_front_translation_handoff.md`
