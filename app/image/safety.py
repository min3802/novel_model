from __future__ import annotations

from typing import Any

from app.translation.core.openai_client import get_openai_client
from app.translation.core.runtime import is_mock_mode

from .config import ImageConfig


# 사전 키워드 필터: 명백한 노출/성적 요청을 LLM 호출 전에 1차 차단.
_UNSAFE_TERMS = [
    "나체", "전신 노출", "성기", "음부", "자위", "성행위",
    "nude", "nudity", "fully naked", "genitals", "explicit sexual",
]


def is_unsafe_visual_request(text: str) -> bool:
    lowered = (text or "").lower()
    return any(term in lowered for term in _UNSAFE_TERMS)


# mock/폴백용 고정 거부 메시지. 기존 acceptance 테스트가 요구하는
# "생성해드릴 수 없습니다" 문구를 반드시 포함한다.
_FALLBACK_REFUSAL = (
    "전신 노출처럼 성기까지 드러나는 이미지는 생성해드릴 수 없습니다. "
    "대신 상의는 벗되 하의는 젖은 잠방이나 허리 천으로 가린 모습처럼, "
    "노출 수위를 낮춘 방향으로 조정하면 생성할 수 있습니다."
)

_SAFETY_SYSTEM = (
    "당신은 이미지 생성 안전 가이드입니다. 사용자의 시각화 요청 중 부적절한 부분(특히 성기 노출 등)을 "
    "단순 거부하지 말고, '어떤 부분이 불가한지' 짚은 뒤 '이렇게 조정하면 생성 가능'한 비노출 대안을 "
    "구체적으로 한 가지 제시하세요. 작품 맥락을 해치지 않는 선에서 현실적인 대안을 한국어로, 2~3문장으로 답합니다. "
    "반드시 '생성해드릴 수 없습니다'라는 표현을 포함하세요."
)


def build_refusal(request_text: str, config: ImageConfig | None = None) -> dict[str, Any]:
    """부적절 요청에 대한 '거부 + 대안 제시' 응답 생성.

    mock 모드거나 LLM 호출 실패 시 고정 폴백 메시지를 쓴다(테스트 안정성).
    """
    config = config or ImageConfig()
    message = _FALLBACK_REFUSAL

    if not is_mock_mode():
        try:
            client = get_openai_client()
            response = client.responses.create(
                model=config.safety_model,
                input=[
                    {"role": "system", "content": _SAFETY_SYSTEM},
                    {"role": "user", "content": f"요청 내용: {request_text}\n위 요청의 부적절 부분을 거부하고 비노출 대안을 제시해줘."},
                ],
            )
            text = (response.output_text or "").strip()
            if text:
                if "생성해드릴 수 없습니다" not in text:
                    text = "해당 요청은 그대로는 생성해드릴 수 없습니다. " + text
                message = text
        except Exception:
            message = _FALLBACK_REFUSAL  # LLM 실패 시 폴백

    return {
        "type": "refusal",
        "model": config.image_model,
        "message": message,
    }
