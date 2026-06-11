# Next OMX Handoff

## 0B. 2026-06-09 latest main sync + localization-guide state

This session pulled teammate changes from GitHub `main` and preserved the in-progress localization-guide work.

Git state / sync:

- Current branch: `main`
- Current pulled HEAD: `c25cb3a Merge pull request #6 from min3802/jin`
- Git on this Windows environment is not on PATH; use:

```powershell
$repo = (Get-Location).Path -replace '\\','/'
& 'C:\Program Files\Git\cmd\git.exe' -c safe.directory=$repo <git args>
```

- Pull strategy used:
  1. `fetch origin main`
  2. compared `HEAD..origin/main` against local localization-guide changes
  3. stashed tracked local changes
  4. `pull --ff-only origin main`
  5. reapplied stash
- No merge conflicts after stash apply.
- Safety stash is still present:

```txt
stash@{0}: On main: pre-pull localization-guide tracked changes
```

Do not drop it until the next agent/user is comfortable that the reapplied working tree is correct.

Verification after pull + stash reapply:

```txt
C:\Users\kwonm\anaconda3\python.exe -m pytest tests/test_localization_mvp_pipeline.py
# 10 passed

C:\Users\kwonm\anaconda3\python.exe -m pytest
# 104 passed
```

### Localization-guide changes currently in working tree

Important changed/new surfaces:

```txt
backend/services/guide_service.py
app/guide/work_analysis.py
app/guide/cultural_localization.py
app/guide/localization_mvp_pipeline.py
app/guide/regulation_policy_analysis.py
tests/test_localization_mvp_pipeline.py
docs/live_localization_guide_us.html
docs/live_localization_guide_us.json
```

`app/guide/` is currently untracked as a directory in git status, so be careful before cleanup/reset commands.

### Product decisions from the latest discussion

The current focus is localization-guide quality, especially avoiding both extremes:

```txt
Bad old behavior:
token overlap too loose -> unrelated culture cards attached
examples: Korean military uniform patterns, student hierarchy, school uniform class markers

Bad overcorrection:
culture notes disappear entirely or one generic fallback is forced
```

Current implemented behavior:

- `?? ???` no longer implies `?? ?? ??`.
- `?? ?? ??` now only matches clear Korea anchors such as `??`, `??`, `??`.
- `??/??/??/??` are separated into `???`; loose words like `??`, `??` were removed because they overmatched `??? ??`.
- Culture RAG only receives culture-trigger elements:

```python
CULTURE_TRIGGER_ELEMENTS = {
    "???",
    "? ??",
    "??/?? ??",
    "?? ??/??",
    "??/? ??",
    "?? ?? ??",
    "??/?? ???",
}
```

- Culture RAG scoring is now stricter:
  - direct `metadata.keyword_ko` in query adds weight
  - otherwise token overlap must be stronger
- There is currently a fallback note for detailed Korean source text:

```txt
element: ??? ?? ?? ??
source: detailed_korean_source_text
```

The user challenged this fallback. They do **not** want ?always attach exactly one note.? They asked how notes are currently retrieved. The next step should likely redesign culture note retrieval toward **anchor-gated matching**, not fixed-count fallback.

Recommended next culture-note direction:

```txt
1. Use a small explicit CULTURE_ANCHORS map.
2. A culture card can match only if its keyword/alias anchor appears directly in title/synopsis/elements.
3. Token overlap is used for ranking only, not as admission.
4. Generic Korean source guidance should be optional and clearly separated from concrete culture-card notes.
```

Example anchor map shape:

```python
CULTURE_ANCHORS = {
    "???": ("???", "????", "????"),
    "? ??": ("??", "??", "??", "??"),
    "??": ("??", "??", "?3", "??"),
    "??": ("??", "???", "??"),
    "??": ("??", "49?", "??", "??"),
    "??": ("??", "????"),
}
```

Avoid loose matching from broad words such as:

```txt
??, ??, ??, ??, ??, ???, ??
```

### Other implemented quality fixes

- Policy cards are summarized before display; raw platform cards are kept under `rawPolicyCards`.
- `R15` maps to `?? ?? ??`, not `?? ??`.
- `R18` maps to `?? ?? ??`.
- `??`, `???`, `???`, `???` map to `??? ??`, separate from `?? ??`.
- New-pipeline LLM path no longer mixes legacy guide context:

```python
generate_llm_guide(payload, result)
```

- HTML copy removed developer-facing phrases like:

```txt
Localization Guide MVP
reportMode:
deterministic pipeline
```

### Current sample result

Regenerated files:

```txt
docs/live_localization_guide_us.html
docs/live_localization_guide_us.json
```

Current sample culture note behavior:

```txt
cultureNotes:
- ??? ?? ?? ??
```

Current sample policy cards:

```txt
- ??/?? ?? ?? ??
- ??????????? ?? ?? ?? ??
- ??/?? ?? ??? ??
```

### Suggested next task

Refactor `app/guide/cultural_localization.py` so culture notes are not count-driven fallback. Implement anchor-gated note retrieval:

1. Add explicit `CULTURE_ANCHORS`.
2. Match concrete culture cards only when anchor appears.
3. Keep token overlap as rank/tiebreaker.
4. Move `??? ?? ?? ??` to a separate field such as `generalLocalizationNotes` or add it only when user-facing report needs a non-card guidance section.
5. Add tests:
   - romance/author/contract synopsis does not get unrelated RAG cards
   - explicit `???/??/????` gets military/culture guidance
   - `?? ???` alone does not create Korean-setting culture notes
   - detailed Korean source may produce general wording guidance, but not as a fake culture-card match

---


## 0. 2026-06-09 session sync note

This session re-checked the handoff and working tree, then corrected the gap where yesterday's `synopsis` decision existed mostly in theory but was not strongly reflected in code, tests, or saved artifacts.

Environment notes:

- Current handoff: `docs/next_omx_handoff.md`
- Runbook: `docs/model_test_runbook.md`
- Current omx CLI: `oh-my-codex v0.18.10`
- Runtime surface: Windows native Codex App; tmux/HUD unavailable. `omx question` and tmux team UI are not directly available here.
- Git needs the repo ownership workaround: `git -c safe.directory="C:/Users/kwonm/Kwon3802/바탕 화면/model" ...`.
- PowerShell `Get-Content` may display Korean as mojibake. Trust Python UTF-8 reads for payload/summary validation.

Product contract aligned in this session:

- When `synopsis` is present, the guide should produce more specific work-level material/relationship/sensitivity checks.
- Elements read from `synopsis` must be marked as inferred/check candidates, not confirmed tags.
- When `synopsis` is absent, the guide must say that it is limited to genre + target-country checks and must not confirm work-specific sensitive elements or core motifs.
- Platform atmosphere and policy/regulation checks remain separate.

Code surfaces updated:

- `app/guide/platform_trend_advisor.py`: added synopsis motif detection and synopsis-present/synopsis-absent section copy.
- `app/guide/context_pack_analysis.py`: added `synopsis_present`, `synopsis_inferred_elements`, and `synopsis_inferred_signal_count`; synopsis-derived items are separated from direct input.
- `app/guide/llm_guide_writer.py`: added LLM instructions for the synopsis-present vs synopsis-absent contract.
- `tests/test_title_genre_synopsis_flow.py`: added regression coverage proving synopsis presence changes mode, input summary, and guide copy.

Current saved baseline:

- `docs/live_policy_localization_payload.json`: regenerated as `useLlm=false`, `targetCountry=Japan`, `title + genre + synopsis` sparse payload.
- `docs/live_policy_localization_response.json`: regenerated from the same deterministic payload.
- `docs/live_policy_localization_smoke_summary.json`: now records `mode=synopsis_country_recommendation`, `synopsisPresent=true`, `policyCardCount=7`.
- `docs/live_policy_intermediate_html_report.html`, `docs/live_policy_intermediate_policy_cards.html`, `docs/live_policy_final_localization_report.html`: regenerated from the same response.

Verification:

```txt
C:\Users\kwonm\anaconda3\python.exe -m unittest tests.test_title_genre_synopsis_flow
# 4 tests OK

C:\Users\kwonm\anaconda3\python.exe -m unittest tests.test_regulation_policy_analysis tests.test_context_pack_analysis tests.test_guide_context_pack_briefing tests.test_title_genre_synopsis_flow
# 12 tests OK

C:\Users\kwonm\anaconda3\python.exe -m py_compile backend\services\guide_service.py app\guide\context_pack_analysis.py app\guide\platform_trend_advisor.py app\guide\llm_guide_writer.py scripts\export_live_policy_localization_html.py
# OK
```

Caution:

- This regenerated baseline is deterministic (`useLlm=false`). Run the live OpenAI-backed case separately via `.env` and the runbook if live output is needed.
- `scripts/export_live_policy_localization_html.py` still contains pre-existing mojibake/garbled UI copy. The issue is not that Korean copy exists, but that some generated-report wording is encoded incorrectly and duplicated outside the main guide copy path. This session prioritized the synopsis contract and JSON/response baseline; exporter copy recovery/centralization should be a separate cleanup pass.

---

## 0A. Important architecture note: rich synopsis packets need internal multi-agent stages

Decision captured from the 2026-06-09 discussion: if guide input evolves from simple `title + genre + synopsis` into a rich synopsis packet (`title`, `genres`, `keywords`, `oneLinePitch`, long synopsis/work intro, characters), the product should not treat it as one flat synopsis string.

Recommended internal agent/stage structure:

```txt
Guide Supervisor
├─ Work Understanding Agent
├─ Market Mapping Agent
├─ Policy Check Agent
└─ Guide Writer Agent
```

Execution shape:

```txt
Rich Synopsis Packet
  -> Guide Supervisor normalizes input and preserves backward compatibility
  -> Work Understanding Agent extracts declared vs inferred work signals
  -> Market Mapping Agent and Policy Check Agent run independently/parallel after work understanding
  -> Guide Supervisor merges without mixing platform atmosphere and policy checks
  -> Guide Writer Agent produces writer-facing report copy with claim boundaries
```

Key contract:

- Agents are divided by judgment responsibility, not by raw input field.
- `title` can be treated as compressed public hook / compressed synopsis signal.
- `genres` and `keywords` are declared signals.
- `oneLinePitch`, long synopsis, and characters expand or correct title/keyword interpretation.
- Market mapping and policy checking should remain separate and can run in parallel after work understanding.
- Supervisor is needed for conflict resolution, backward compatibility, and final claim boundary enforcement.
- Avoid over-splitting into Title/Genre/Keyword/Synopsis/Character agents; that is too field-centric.
Last updated: 2026-06-08

목적: 다음 세션이 **지금까지 완성된 일본 현지화 리포트 흐름**을 바로 이어받고, 필요하면 **input contract를 country + genre + synopsis 중심으로 재정렬**할 수 있게 만드는 인계 문서.

---

## 1. 현재 제품 방향

이 기능은 “추천 점수”나 “시장 적합 판정”이 아니라 **작가가 일본 플랫폼에 내보내기 전에 무엇을 먼저 확인해야 하는지 보여주는 체크 리포트**다.

사용자 화면의 핵심 질문은 아래다.

```txt
내 작품을 일본 플랫폼에 올릴 때 지금 뭘 먼저 확인하면 되지?
```

따라서 화면은 분석 문구보다 **결론 → 이유 → 확인 항목 → 상세 근거** 순서로 읽혀야 한다.

### 쓰는 표현

```txt
이번 결과 요약
입력 작품을 이렇게 읽었어요
일본 플랫폼에서는 어떤 이름으로 보일 수 있을까요?
일본 순위권 작품에서 자주 보인 키워드
게시 전 체크포인트
규정 후보 자세히 보기
```

### 피하는 표현

```txt
추천 / 시장 적합 / 성공 가능성 / 안전 / 허용 / 위반 확정
```

### 핵심 분리

```txt
플랫폼 분위기 = 순위권 태그/장르 흐름에서 무엇이 보였는지
규정/규제 = 게시 전 무엇을 확인해야 하는지
```

둘은 같은 리포트 안에 둘 수 있지만, **점수나 단일 결론으로 합치면 안 된다.**

---

## 2. 현재 실제 구현 표면

핵심 파일:

```txt
api_server.py
backend/services/guide_service.py
app/guide/context_pack_analysis.py
app/guide/regulation_policy_analysis.py
frontend/features/guide/GuideConnector.tsx
frontend/styles/60-modals-guide-advanced.css
scripts/export_live_policy_localization_html.py
scripts/generate_regulation_policy_sample.py
tests/test_context_pack_analysis.py
tests/test_guide_context_pack_briefing.py
tests/test_market_observation_pipeline.py
tests/test_platform_observation_ui_artifacts.py
tests/test_regulation_policy_analysis.py
```

현재 API:

```txt
POST /api/guide
```

현재 응답에 붙는 주요 확장 필드:

```txt
contextPackBriefing
contextPackEvidence
policyAttentionCards
policyLimitations
```

---

## 3. 현재 live 산출물

마지막 live smoke는 실제로 다시 돌려서 저장했다.

생성/갱신된 파일:

```txt
docs/live_policy_localization_payload.json
docs/live_policy_localization_response.json
docs/live_policy_intermediate_html_report.html
docs/live_policy_intermediate_policy_cards.html
docs/live_policy_final_localization_report.html
docs/live_policy_localization_smoke_summary.json
docs/model_test_case_outputs_live_guide.json
docs/model_test_case_outputs_live_guide.md
```

최종 HTML 제목:

```txt
일본 플랫폼 체크 리포트
```

상단 개발 메타는 숨겨 두고, 하단에 `자세한 생성 정보` 접기로 둔다.

---

## 4. 현재 writer-facing UI 구조

`frontend/features/guide/GuideConnector.tsx` 기준 현재 화면 순서:

```txt
1. 일본 플랫폼 체크 리포트
2. 이번 결과 요약
3. 입력 작품을 이렇게 읽었어요
4. 일본 플랫폼에서는 어떤 이름으로 보일 수 있을까요?
5. 일본 순위권 작품에서 자주 보인 키워드
6. 게시 전 체크포인트
7. 규정 후보 자세히 보기
8. 기존 API htmlReport 원문 보기(접기)
```

### 화면 의도

- `이번 결과 요약`: 사용자가 제일 먼저 봐야 할 것
- `입력 작품을 이렇게 읽었어요`: 입력값이 어떻게 해석됐는지
- `일본 플랫폼에서는 어떤 이름으로 보일 수 있을까요?`: 태그 표현 변환
- `게시 전 체크포인트`: 작가가 바로 확인할 것
- `규정 후보 자세히 보기`: 근거 확인용 상세 규정

### UI에서 숨기거나 약화한 것

```txt
분해 관찰 / 직접 겹침 / 조건부 비교 / 매칭 상태 / 관찰 레코드 / signal_type / context pack
```

### 테스트/HTML 실행 런북

현재 모델 테스트와 최종 HTML 재생성 절차는 아래 문서를 기준으로 한다.

```txt
docs/model_test_runbook.md
```

핵심 포인트:

- `scripts/model_test_case_runner.py`는 `.env`를 자동으로 읽는다.
- live OpenAI-backed 케이스는 `--mock` 없이 실행한다.
- 현재 guide/HTML baseline은 `title + genre + synopsis`만 들어간 sparse payload로 유지한다.
- Windows 기본 `python`에 `dotenv`가 없으면 `C:\\Users\\kwonm\\anaconda3\\python.exe`를 사용한다.

---

## 5. 매우 중요한 input contract 메모

지금까지의 live smoke payload에는 테스트/검증 편의를 위해 보조 필드가 들어갔지만, **다음 세션에서의 제품 계약은 다음 가정으로 다뤄야 한다.**

```txt
현재 구현은 titleElements / comparableSignals를 아직 보조 입력으로 받고 있다.
제품 계약상 이 둘을 유지할지 제거할지는 다음 세션에서 다시 결정해야 한다.
```

즉:

- `titleElements`
- `comparableSignals`

이 둘은 현재 **제품의 보조 입력/추출값**으로 취급되고 있으며, 사용자 입력 계약과 분리해서 봐야 한다.

### 이 가정이 맞다면

작가용 결과는 아래처럼 **시놉시스/장르에서 유도된 해석**으로 나와야 한다.

```txt
이번 결과 요약
입력 작품을 이렇게 읽었어요
일본 플랫폼에서는 어떤 이름으로 보일 수 있을까요?
게시 전 체크포인트
```

### 주의

사용자가 입력하지 않은 요소를 마치 확정값처럼 보여주면 안 된다.

```txt
Bad: 제목에 악역영애가 있으니 이 작품은 이런 태그입니다
Good: 시놉시스에서 보이는 복수/잔혹/연령 요소를 기준으로, 일본 플랫폼에서 확인할 항목을 정리했습니다
```

`synopsis`에서 민감 요소를 추론한다면 반드시 `inferred` 또는 `조심스러운 추정`으로 분리해라.

---

## 6. 현재 규정/정책 파이프라인

규정 레이어는 별도로 유지한다.

핵심 파일:

```txt
app/guide/regulation_policy_analysis.py
```

현재 방향:

```txt
platform atmosphere = ranking/tag observations
regulation/policy = check-before-publish candidates
```

좋은 분리:

```txt
R15/잔혹/성적 표현은 순위권 태그 흐름에서 보였는지와 별개로,
게시 전 체크포인트로 따로 보여준다.
```

### policy_attention_cards

`policyAttentionCards`는 법적 최종 판정이 아니라 **UI용 확인 후보**다.

권장 카드 구조 예:

```json
{
  "card_title": "R15/R18 표시가 필요한가요?",
  "status_label": "게시 전 확인",
  "matched_elements": ["R15", "성적 묘사"],
  "matched_rule_ids": ["JP_ALPHAPOLIS_0010"],
  "platform_display_name": "アルファポリス(알파폴리스)",
  "display_sentence": "제목과 입력 요소에 R15·성적·잔혹 묘사가 걸려 있어, 일본 플랫폼에 올리기 전 연령 등급 표시를 먼저 확인하는 게 좋습니다."
}
```

### 규정 섹션 UI 원칙

```txt
체크포인트를 먼저 보여주고
상세 규정은 접어 둔다
```

---

## 7. 최신 검증 상태

마지막 live 검증은 아래 순서로 돌렸다.

```txt
1. python -m unittest tests.test_title_genre_synopsis_flow
2. docs/live_policy_localization_payload.json 갱신
3. docs/live_policy_localization_response.json 갱신
4. scripts/export_live_policy_localization_html.py 실행
5. HTML 구조/문구 확인
```

결과:

```txt
title+genre+synopsis tests: 3 OK
current guide baseline: sparse payload
live /api/guide: 200
policyCardCount: 0
model_test_case_runner live guide case: OK
final HTML regenerated: OK
```

검증 후 정리:

```txt
docs/live_policy_localization_response.json refreshed
docs/live_policy_final_localization_report.html refreshed
docs/live_policy_localization_smoke_summary.json refreshed
docs/model_test_case_outputs_live_guide.json refreshed
docs/model_test_case_outputs_live_guide.md refreshed
```

---

## 8. 인코딩 메모

파일 인코딩은 UTF-8을 기준으로 다룬다.

PowerShell 콘솔에서 한글이 깨져 보일 수 있으니, 파일 내용 확인은 가능하면 Python UTF-8 read로 확인한다.

```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "from pathlib import Path; print(Path('path/to/file').read_text(encoding='utf-8'))"
```

콘솔 표시 문제만 보고 파일을 수정하지 말 것.

---

## 9. 다음 세션에서 바로 할 일

다음 세션 첫 작업은 아래 순서로 하면 된다.

```txt
1. docs/next_omx_handoff.md 읽기
2. docs/model_test_runbook.md 확인
3. .env에 OPENAI_API_KEY / WLIGHTER_MOCK_MODE가 맞는지 확인
4. 필요하면 scripts/model_test_case_runner.py로 live case 실행
5. docs/live_policy_localization_response.json 확인
6. scripts/export_live_policy_localization_html.py로 최종 HTML 갱신
7. payload/response/HTML가 깨진 문자열 없이 저장됐는지 확인
```

### 다음에 바로 실행할 프롬프트

```txt
docs/model_test_runbook.md와 docs/next_omx_handoff.md를 읽고, .env를 사용한 model test workflow와 current sparse guide HTML baseline을 이어서 검증해줘. title + genre + synopsis 기준으로 live case를 돌린 뒤, 필요한 경우 docs/live_policy_localization_response.json과 최종 HTML을 다시 export해줘. Windows 기본 python에 dotenv가 없으면 conda python을 사용해줘.
```

---

## 10. 메모

- 규정/정책은 최신성이 중요하므로 공식 출처 확인이 필요하다.
- synopsis에서 민감 요소를 추론한다면 `inferred`로 분리하고, 확정값처럼 보이지 않게 한다.
- 이번 handoff는 예전 context-pack 중심 문서를 대체하는 최신 기준 문서다.






