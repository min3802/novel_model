{common_korean_rule}

Source {source_language} text:
{source_text}

Retrieved translation-expression references for {target_language} localization:
{rag_context}

Matched Korean cultural annotation/note candidates:
{cultural_context}

Task:
- Translate the {source_language} source into natural {target_language}.
- If the source is idiomatic or culture-bound, prefer a functionally equivalent {target_language} expression.
- Use translation-expression references as hints for rendering idioms, slang, or fixed expressions; do not treat cultural annotation cards as target-language expression recommendations.
- Use matched cultural annotation candidates as Korean cultural facts and possible note triggers, not as fixed wording.
- When a cultural candidate is relevant, decide whether to preserve, translate, annotate, or briefly explain it based on the source context and target reader needs.
- If a cultural annotation candidate is background-only or obvious in context, do not over-explain it.
- Do not invent country-specific facts from the cultural candidates. Country-specific risk and sensitivity will be checked by the inspection agent.
- Fill `translation_decisions` for each meaningful idiom, culture-bound expression, or localization decision.
- Each decision must connect source_span -> reference/cultural candidate -> translated_span -> Korean reason.
- For decisions based on translation RAG, set `reference_id` to the translation RAG id.
- For decisions based on the cultural lexicon or annotation RAG, set `reference_id` to the cultural candidate id and set `decision_type` to a cultural strategy such as `cultural_preserve`, `cultural_translate`, `cultural_annotate`, or `annotation_note`.
- If a reference or cultural candidate was not actually used in the translation, do not include it in `translation_decisions`.
- If no RAG reference or cultural candidate was used, return an empty `translation_decisions` array.

Output requirements:
- `translation`: natural {target_language} translation.
- `strategy`: short label.
- `rationale`: Korean explanation of why this translation strategy was chosen.
- `reference_ids`: IDs actually used.
- `translation_decisions[].reason`: Korean explanation of why the source expression was rendered that way.
