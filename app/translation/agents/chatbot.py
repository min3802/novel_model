from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from ..config import PipelineConfig
from ..infra.mock_adapters import chatbot_payload
from ..infra.openai_client import get_openai_client
from ..infra.prompt_loader import load_runtime_prompt


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
            payload = chatbot_payload(user_message, source_text, reviewed_translation)
            return ChatbotReply(
                answer=payload["answer"],
                proposed_translation=payload["proposed_translation"],
                change_summary=payload["change_summary"],
                needs_user_confirmation=payload["needs_user_confirmation"],
                raw_response=payload["raw_response"],
            )

        # 의도 판정 게이트: 번역 검수/수정과 전적으로 무관한 잡담만 차단한다.
        # FN(정당한 질문을 막는 것)을 최소화하기 위해 애매하면 통과(IN_SCOPE)시키고,
        # 분류기가 정확히 OUT_OF_SCOPE를 반환했을 때에만 거절한다(보수적 파싱).
        if self._classify_scope(user_message) == "OUT_OF_SCOPE":
            return ChatbotReply(
                answer=(
                    "방금 요청은 번역 검수·수정과는 거리가 있어 보여요. "
                    "저는 번역 검수와 현지화 수정을 돕는 챗봇이에요. "
                    "번역 결과에 대한 질문이나 수정 요청을 입력해 주세요. "
                    "혹시 번역 관련 질문이었다면 어느 문장·표현인지 조금만 더 구체적으로 다시 물어봐 주세요."
                ),
                # 거절 = "제안 없음". proposed_translation은 빈 문자열로 둔다.
                # (스키마상 required string이라 필드는 있어야 하므로 ""로 채움.)
                # 번역 상태는 프런트가 finalTranslation을 그대로 두므로 별도로 실어 보낼 필요 없다.
                proposed_translation="",
                change_summary="번역 검수 범위를 벗어난 요청이라 번역을 변경하지 않았습니다.",
                needs_user_confirmation=False,
                raw_response={"scope": "OUT_OF_SCOPE"},
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

    def _classify_scope(self, user_message: str) -> str:
        """질문이 번역 검수/수정 범위인지 IN_SCOPE/OUT_OF_SCOPE로만 판정한다(짧은 1회 호출).

        설계 원칙(FN 최소화):
        - 세션 맥락 제공: '지금은 번역 검수·수정 중'이라는 프레임을 줘서
          "뭔가 어색한데?" 같은 모호한 말도 '(번역이) 어색하다'로 해석되게 한다.
        - 관대 판정: 중의적/애매하면 IN_SCOPE. OUT_OF_SCOPE는 번역물과 전적으로 무관한
          일상 잡담·일반 상식(날씨·식사 등)에 한한다. (few-shot 없이 범주 정의로 경계 설정)
        - 보수적 파싱: 정확히 'OUT_OF_SCOPE'를 반환했을 때만 거절. 그 외(문장형·빈값·에러)는 IN_SCOPE.
        """
        try:
            client = get_openai_client()
            resp = client.responses.create(
                model=self.config.review_model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a router for a translation-review chatbot. "
                            "The user is currently in a translation review/editing session and has just "
                            "received a translation result. Decide whether the user's message relates to "
                            "the translation, its review, wording, tone, localization, or a requested edit "
                            "(IN_SCOPE), or is entirely unrelated everyday small talk or general knowledge "
                            "such as weather, meals, or chit-chat (OUT_OF_SCOPE). "
                            "If the message is vague or ambiguous, treat it as IN_SCOPE. "
                            "Answer with exactly one word: IN_SCOPE or OUT_OF_SCOPE."
                        ),
                    },
                    {"role": "user", "content": user_message},
                ],
            )
            out = (resp.output_text or "").strip().upper()
        except Exception:
            # 분류 호출 실패 시에는 통과시킨다(거절로 인한 FN 방지).
            return "IN_SCOPE"
        return "OUT_OF_SCOPE" if out == "OUT_OF_SCOPE" else "IN_SCOPE"

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
