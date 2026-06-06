from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .config import PipelineConfig
from .openai_client import get_openai_client
from .prompt_loader import load_runtime_prompt


CHATBOT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "proposed_translation": {"type": "string"},
        "change_summary": {"type": "string"},
        "needs_user_confirmation": {"type": "boolean"},
    },
    "required": [
        "answer",
        "proposed_translation",
        "change_summary",
        "needs_user_confirmation",
    ],
}


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(slots=True)
class ChatbotReply:
    answer: str
    proposed_translation: str
    change_summary: str
    needs_user_confirmation: bool
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChatbotAgent:
    """Context-aware assistant for explaining and revising translation results."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.resources = config.resolved_resources()
        self.prompt_template = load_runtime_prompt("CHATBOT_PROMPT.md")

    def reply(
        self,
        *,
        user_message: str,
        source_text: str,
        draft_translation: str,
        reviewed_translation: str,
        translation_rationale: str = "",
        used_references: list[dict[str, Any]] | None = None,
        inspection_report: dict[str, Any] | None = None,
        translation_memory: list[dict[str, Any]] | None = None,
        chat_history: list[ChatMessage | dict[str, str]] | None = None,
    ) -> ChatbotReply:
        if self.config.mock:
            return self._mock_reply(
                user_message=user_message,
                source_text=source_text,
                reviewed_translation=reviewed_translation,
            )

        client = get_openai_client()
        schema_name = f"{self.resources.locale}_chatbot_reply".replace("-", "_")
        prompt = self._build_prompt(
            user_message=user_message,
            source_text=source_text,
            draft_translation=draft_translation,
            reviewed_translation=reviewed_translation,
            translation_rationale=translation_rationale,
            used_references=used_references or [],
            inspection_report=inspection_report or {},
            translation_memory=translation_memory or [],
            chat_history=chat_history or [],
        )
        response = client.responses.create(
            model=self.config.review_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a translation editing chatbot. Explain decisions, "
                        "propose revisions, and never claim changes are saved unless "
                        "the application confirms them. Return JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": CHATBOT_SCHEMA,
                    "strict": True,
                }
            },
        )
        payload = json.loads(response.output_text)
        return ChatbotReply(
            answer=payload["answer"],
            proposed_translation=payload["proposed_translation"],
            change_summary=payload["change_summary"],
            needs_user_confirmation=payload["needs_user_confirmation"],
            raw_response=payload,
        )

    def _mock_reply(
        self,
        *,
        user_message: str,
        source_text: str,
        reviewed_translation: str,
    ) -> ChatbotReply:
        """Deterministic local behavior for acceptance-test scenarios."""
        message = user_message.strip()
        unrelated_markers = ["저녁 메뉴", "집 가고 싶", "날씨", "농담"]
        if any(marker in message for marker in unrelated_markers):
            return ChatbotReply(
                answer="저는 번역 검수 및 현지화 지원을 전문으로 합니다. 번역 결과에 대한 질문이나 수정 요청을 입력해 주세요.",
                proposed_translation=reviewed_translation,
                change_summary="번역 검수와 무관한 질문이라 수정하지 않았습니다.",
                needs_user_confirmation=False,
                raw_response={},
            )
        vague_markers = ["뭔가 이상", "어색", "별로", "수정해줘"]
        if any(marker in message for marker in vague_markers) and not any(
            specific in message for specific in ["사랑해", "愛してる", "好きです", "번째", "문장"]
        ):
            return ChatbotReply(
                answer="어떤 부분이 어색하게 느껴지시나요? 해당 표현이나 문장을 알려주시면 자세하게 도움드릴 수 있어요!",
                proposed_translation=reviewed_translation,
                change_summary="수정 범위를 특정하기 위한 추가 질문을 반환했습니다.",
                needs_user_confirmation=False,
                raw_response={},
            )
        if "한강 데이트" in message and "한강" not in source_text:
            return ChatbotReply(
                answer="현재 작업 중인 회차에서 해당 장면을 찾을 수 없습니다.",
                proposed_translation=reviewed_translation,
                change_summary="원문에 없는 장면 요청이라 반영하지 않았습니다.",
                needs_user_confirmation=False,
                raw_response={},
            )
        if "사랑해" in message or "愛してる" in message:
            proposed = reviewed_translation.replace("愛してる", "好きです")
            return ChatbotReply(
                answer=(
                    "이 부분에서는 '愛してる'보다 '好きです'가 더 자연스러울 수 있습니다. "
                    "'愛してる'는 일본어 일상 대화에서 매우 무겁게 들릴 수 있어, "
                    "원문의 감정 강도가 강하지 않다면 '好きです'를 권합니다."
                ),
                proposed_translation=proposed,
                change_summary="'愛してる'를 일본 문화권에 더 자연스러운 '好きです'로 조정했습니다.",
                needs_user_confirmation=True,
                raw_response={},
            )
        return ChatbotReply(
            answer=(
                "Mock chatbot: 현재 번역 근거와 검수 결과를 바탕으로 설명하거나 "
                "수정안을 제안할 수 있습니다."
            ),
            proposed_translation=reviewed_translation,
            change_summary="No change in mock mode.",
            needs_user_confirmation=False,
            raw_response={},
        )

    def _build_prompt(
        self,
        *,
        user_message: str,
        source_text: str,
        draft_translation: str,
        reviewed_translation: str,
        translation_rationale: str,
        used_references: list[dict[str, Any]],
        inspection_report: dict[str, Any],
        translation_memory: list[dict[str, Any]],
        chat_history: list[ChatMessage | dict[str, str]],
    ) -> str:
        normalized_history = [
            asdict(row) if isinstance(row, ChatMessage) else row for row in chat_history
        ]
        return self.prompt_template.format(
            locale=self.resources.locale,
            target_language=self.resources.target_language,
            source_language=self.resources.source_language,
            source_text=source_text,
            draft_translation=draft_translation,
            reviewed_translation=reviewed_translation,
            translation_rationale=translation_rationale or "- none",
            used_references_json=json.dumps(used_references, ensure_ascii=False, indent=2),
            inspection_report_json=json.dumps(inspection_report, ensure_ascii=False, indent=2),
            translation_memory_json=json.dumps(translation_memory, ensure_ascii=False, indent=2),
            chat_history_json=json.dumps(normalized_history, ensure_ascii=False, indent=2),
            user_message=user_message,
        )
