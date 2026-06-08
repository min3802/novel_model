from __future__ import annotations

import json
from typing import Any

from app.translation.core.openai_client import get_openai_client


def join_episodes(episodes: str | list[str], max_episodes: int, max_chars: int) -> str:
    """여러 화를 추출용 단일 텍스트로 합친다.

    - 리스트면 최대 max_episodes 화까지만(앞에서부터) 사용.
    - 화 경계를 '=== N화 ==='로 표시해 LLM 이 화 구분을 인지하게 한다.
    - 최종 길이가 max_chars 초과 시 뒤쪽(최신 화) 우선 보존하며 앞을 자른다.
    """
    if isinstance(episodes, str):
        joined = episodes
    else:
        selected = [ep for ep in episodes if (ep or "").strip()][:max_episodes]
        joined = "\n\n".join(
            f"=== {idx}화 ===\n{ep.strip()}" for idx, ep in enumerate(selected, start=1)
        )
    if len(joined) > max_chars:
        joined = joined[-max_chars:]
    return joined


def call_structured(model: str, system_prompt: str, user_prompt: str,
                    schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """번역 엔진과 동일한 Responses API + json_schema(strict) 구조화 호출."""
    client = get_openai_client()
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    )
    payload = json.loads(response.output_text)
    payload["raw_response"] = {"model": model}
    return payload
