{common_korean_rule}

Source {source_language} text:
{source_text}

Retrieved translation-expression references for {target_language} localization:
{rag_context}

Task:
- Translate the {source_language} source into natural {target_language}.
- If the source is idiomatic or culture-bound, prefer a functionally equivalent {target_language} expression.
- Use translation-expression references as hints for rendering idioms, slang, or fixed expressions.
- Do not invent country-specific facts. Country-specific risk and sensitivity will be checked by the inspection agent, and reader-facing cultural notes are proposed separately as annotation candidates.
- Fill `translation_decisions` for each meaningful idiom, culture-bound expression, or localization decision.
- Each decision must connect source_span -> reference -> translated_span -> Korean reason.
- For decisions based on translation RAG, set `reference_id` to the translation RAG id.
- If a reference was not actually used in the translation, do not include it in `translation_decisions`.
- If no RAG reference was used, return an empty `translation_decisions` array.

Output requirements:
- `translation`: natural {target_language} translation.
- `strategy`: short label.
- `rationale`: Korean explanation of why this translation strategy was chosen.
- `reference_ids`: IDs actually used.
- `translation_decisions[].reason`: Korean explanation of why the source expression was rendered that way.
