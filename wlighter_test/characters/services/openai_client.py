import json
import os

from django.conf import settings


def get_openai_client():
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다.")
    return OpenAI(api_key=api_key)


def request_json(system_prompt: str, user_prompt: str) -> dict:
    client = get_openai_client()
    model = getattr(settings, "WLIGHTER_TEXT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content or "{}")

