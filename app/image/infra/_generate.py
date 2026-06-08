from __future__ import annotations

from typing import Any

from app.translation.infra.openai_client import get_openai_client
from app.translation.infra.runtime import is_mock_mode

from ..config import ImageConfig


def generate_image(prompt: str, config: ImageConfig | None = None) -> dict[str, Any]:
    """gpt-image 실제 호출(공통). mock 모드면 결정적 가짜 응답.

    출력 계약(기존 image_service/acceptance 테스트와 호환):
      - mock:  {"type":"mock_image", "data", "model", "notice", "prompt"}
      - base64:{"type":"base64", "data", "model", "notice", "prompt"}
      - url:   {"type":"url", "data", "model", "notice", "prompt"}
    """
    config = config or ImageConfig()
    if is_mock_mode():
        return {
            "type": "mock_image",
            "data": "mock://w-lighter/generated-image",
            "model": config.image_model,
            "notice": config.ai_notice,
            "prompt": prompt,
        }

    client = get_openai_client()
    response = client.images.generate(
        model=config.image_model,
        prompt=prompt,
        size=config.image_size,
        n=1,
    )
    item = response.data[0]
    b64 = getattr(item, "b64_json", None)
    url = getattr(item, "url", None)
    base = {"model": config.image_model, "notice": config.ai_notice, "prompt": prompt}
    if b64:
        return {"type": "base64", "data": b64, **base}
    if url:
        return {"type": "url", "data": url, **base}
    raise RuntimeError("이미지 데이터를 찾지 못했습니다.")
