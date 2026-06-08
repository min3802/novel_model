from __future__ import annotations

import json
from typing import Any

from app.translation.infra.openai_client import get_openai_client


def join_episodes(episodes: str | list[str], max_episodes: int) -> str:
    """여러 화를 추출용 단일 텍스트로 합친다.

    - 리스트면 최대 max_episodes 화까지만(앞에서부터) 사용.
    - 화 경계를 '=== N화 ==='로 표시해 LLM 이 화 구분을 인지하게 한다.

    입력 글자 길이 보호(절단)는 여기서 하지 않는다 — 분량 제한은 업로드/저장 시점 책임이며,
    추출 단계는 화 개수 상한(max_episodes)만 책임진다.
    """
    if isinstance(episodes, str):
        return episodes
    selected = [ep for ep in episodes if (ep or "").strip()][:max_episodes]
    return "\n\n".join(
        f"=== {idx}화 ===\n{ep.strip()}" for idx, ep in enumerate(selected, start=1)
    )


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
