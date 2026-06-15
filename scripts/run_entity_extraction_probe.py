from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "gpt-5.4-mini"


def _load_dotenv_key_only(path: Path = Path(".env")) -> None:
    if os.getenv("OPENAI_API_KEY") or not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "OPENAI_API_KEY":
            os.environ["OPENAI_API_KEY"] = value.strip().strip('"').strip("'")
            return


def _schema_for_locale(target_locale: str) -> dict[str, Any]:
    locale_key = target_locale.strip() or "target_locale"
    locale_hint_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "canonical": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["canonical", "aliases"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "canonicalName": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"},
                        "targetLocaleHint": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {locale_key: locale_hint_schema},
                            "required": [locale_key],
                        },
                    },
                    "required": [
                        "canonicalName",
                        "aliases",
                        "confidence",
                        "evidence",
                        "reason",
                        "targetLocaleHint",
                    ],
                },
            },
            "places": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"},
                        "targetLocaleHint": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {locale_key: locale_hint_schema},
                            "required": [locale_key],
                        },
                    },
                    "required": ["name", "aliases", "confidence", "evidence", "reason", "targetLocaleHint"],
                },
            },
            "organizations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"},
                        "targetLocaleHint": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {locale_key: locale_hint_schema},
                            "required": [locale_key],
                        },
                    },
                    "required": ["name", "aliases", "confidence", "evidence", "reason", "targetLocaleHint"],
                },
            },
            "ambiguousTerms": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "text": {"type": "string"},
                        "possibleEntity": {"type": "string"},
                        "possibleCommonMeaning": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "note": {"type": "string"},
                    },
                    "required": [
                        "text",
                        "possibleEntity",
                        "possibleCommonMeaning",
                        "confidence",
                        "evidence",
                        "note",
                    ],
                },
            },
        },
        "required": ["characters", "places", "organizations", "ambiguousTerms"],
    }


def _build_prompt(*, source_text: str, target_locale: str) -> str:
    return f"""목적:
긴 한국어 웹소설 원문에서 등장인물, 별칭, 지명, 조직명, 고유명사 후보를 구조화해 추출한다.

대상 로케일: {target_locale}

중요 지시:
- 번역하지 말 것.
- 원문에서 인물명/별칭/고유명사 후보만 추출할 것.
- 성+이름으로 등장한 인물이 이후 이름만으로 등장하면 alias로 묶을 것.
- canonicalName은 원문에서 확인되는 가장 긴/완전한 이름 표기를 사용할 것.
- 성+이름과 짧은 이름이 둘 다 있으면 성+이름을 canonicalName, 짧은 이름을 aliases에 둘 것.
- 같은 문자열이 일반명사일 수도 있으면 ambiguousTerms에 표시할 것.
- 인물 alias가 일반명사로도 읽힐 수 있으면 ambiguousTerms에 포함할 것.
- alias 판단은 문맥 근거/evidence를 반드시 포함할 것.
- 확신이 없으면 confidence를 medium 또는 low로 둘 것.
- JSON 외 텍스트를 출력하지 말 것.
- targetLocaleHint는 강제 번역표가 아니라 사람이 검토할 수 있는 표기 후보만 적을 것.
- 원문에 근거가 부족한 후보는 만들지 말 것.

원문:
{source_text}
"""


def _call_openai(*, source_text: str, target_locale: str, model: str) -> dict[str, Any]:
    _load_dotenv_key_only()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to run the probe.")

    from openai import OpenAI

    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You extract structured entities from Korean webnovel source text. "
                    "Do not translate the source. Return JSON only."
                ),
            },
            {"role": "user", "content": _build_prompt(source_text=source_text, target_locale=target_locale)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "entity_extraction_probe",
                "schema": _schema_for_locale(target_locale),
                "strict": True,
            }
        },
    )
    return json.loads(response.output_text)


def _print_summary(result: dict[str, Any], output_path: Path) -> None:
    characters = result.get("characters") or []
    places = result.get("places") or []
    organizations = result.get("organizations") or []
    ambiguous_terms = result.get("ambiguousTerms") or []

    print(f"Wrote {output_path}")
    print(f"characters={len(characters)}")
    print(f"places={len(places)}")
    print(f"organizations={len(organizations)}")
    print(f"ambiguousTerms={len(ambiguous_terms)}")

    for character in characters[:12]:
        print(
            "character: "
            f"{character.get('canonicalName', '')} "
            f"aliases={character.get('aliases') or []} "
            f"confidence={character.get('confidence', '')}"
        )
    for term in ambiguous_terms[:12]:
        print(
            "ambiguous: "
            f"{term.get('text', '')} "
            f"possibleEntity={term.get('possibleEntity', '')} "
            f"possibleCommonMeaning={term.get('possibleCommonMeaning', '')} "
            f"confidence={term.get('confidence', '')}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe whether an OpenAI model can extract Korean webnovel entity candidates as JSON."
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to a UTF-8 Korean source text file.")
    parser.add_argument("--target-locale", required=True, help="Target locale hint, for example ko_ja.")
    parser.add_argument("--output", required=True, type=Path, help="Path to write JSON probe output.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model. Defaults to {DEFAULT_MODEL}.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_text = args.input.read_text(encoding="utf-8")
    result = _call_openai(source_text=source_text, target_locale=args.target_locale, model=args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_summary(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
