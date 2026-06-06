from __future__ import annotations

import json
import re
from typing import Iterable

from .openai_client import get_openai_client
from .prompt_loader import load_runtime_prompt


KOREAN_TRANSLATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "translations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["translations"],
}


def has_hangul(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text or ""))


def looks_like_explanation(text: str) -> bool:
    return bool(re.search(r"[A-Za-zぁ-んァ-ン一-龯]", text or ""))


def needs_korean(text: str) -> bool:
    stripped = (text or "").strip()
    return bool(stripped) and not has_hangul(stripped) and looks_like_explanation(stripped)


def koreanize_texts(texts: Iterable[str], *, model: str) -> list[str]:
    originals = list(texts)
    indexes = [idx for idx, text in enumerate(originals) if needs_korean(text)]
    if not indexes:
        return originals

    targets = [originals[idx] for idx in indexes]
    client = get_openai_client()
    prompt = load_runtime_prompt("KOREAN_OUTPUT_PROMPT.md").format(
        targets_json=json.dumps(targets, ensure_ascii=False, indent=2)
    )
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": "You translate UI explanation text into Korean. Return JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "korean_explanation_translations",
                "schema": KOREAN_TRANSLATION_SCHEMA,
                "strict": True,
            }
        },
    )
    payload = json.loads(response.output_text)
    translations = payload.get("translations", [])
    if len(translations) != len(targets):
        return originals

    result = originals[:]
    for idx, translated in zip(indexes, translations):
        result[idx] = translated
    return result


def koreanize_text(text: str, *, model: str) -> str:
    return koreanize_texts([text], model=model)[0]
