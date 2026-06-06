{common_korean_rule}

Context analysis rules:
- Before judging risk, identify speaker, listener, and relationship from the Korean source.
- Do not invert speaker/listener roles.
- If the source says "상사가 소리쳤다", the speaker is the boss/superior. Do not describe the issue as speech "to the boss" unless the listener is explicitly the boss.
- If the listener is not explicit, write "불명확" or "부하/상대방으로 추정" instead of overclaiming.
- `risk_summary` and `suggestions[].reason` must be grounded in `context_analysis`.
- Avoid Korean explanations like "상사에게 ..." unless the source clearly says the boss is the listener.

Intervention policy:
- Decide whether the issue should be automatically applied or left to the user.
- `AUTO_APPLIED` = 선조치 후보고. Use only for severe, clear, non-literary risk where keeping the draft is likely unsafe or unacceptable.
- `USER_DECISION` = 선보고 후조치. Use for ambiguous, literary, character-driven, historical, tonal, or context-dependent issues. Do not over-soften the translation.
- `INFO_ONLY` = 참고 정보. Use when there is no concrete issue or only a mild note.
- For literary scenes, character flaws, period-specific harshness, violence used as narrative function, or intentionally rude dialogue, prefer `USER_DECISION` over `AUTO_APPLIED` unless there is a clear legal/platform-critical issue.
- If `intervention_policy` is `USER_DECISION` or `INFO_ONLY`, `revised_translation` should preserve the current reviewed translation with at most minimal non-destructive edits.
- If `intervention_policy` is `AUTO_APPLIED`, `revised_translation` may contain the safer corrected translation, and `review_note` must explain that it was pre-applied.

Base review rules:
{base_prompt}

Active locale constraints:
{locale_constraints}

Source {source_language} text:
{source_text}

Draft {target_language} translation:
{draft_translation}

Current reviewed translation candidate:
{reviewed_translation}

Translation rationale:
{translation_rationale}

Used RAG references:
{references_json}

Translation memory / consistency constraints:
{memory_json}

Task:
- Inspect the current translation candidate for cultural safety, localization naturalness, and consistency.
- Fill `context_analysis` first, using only evidence from the Korean source and current translation.
- Do not silently finalize changes. Provide `revised_translation` as a suggestion.
- Include concrete `problematic_spans` and `suggestions` when action is `ADAPT`, `FLAG`, or `BLOCK`.
- Provide suggestions as options where useful, such as preserve / soften / annotate / adapt.
- If no concrete issue exists, return `NOTE` with empty arrays.
- Keep `revised_translation` and `suggestions[].suggested` in {target_language}.

Output reminders:
- `context_analysis`, `risk_summary`, `problematic_spans[].issue`, `suggestions[].reason`, and `review_note`: Korean only.
- `intervention_policy`: `AUTO_APPLIED`, `USER_DECISION`, or `INFO_ONLY`.
