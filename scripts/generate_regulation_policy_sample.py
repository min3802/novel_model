from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.guide.regulation_policy_analysis import build_policy_attention_report


SAMPLE_PAYLOAD = {
    "targetCountry": "Japan",
    "title": "R15 기준 악역영애는 피의 복수를 시작한다",
    "genre": "로맨스 판타지",
    "titleElements": ["R15 기준", "악역영애", "피의 복수"],
    "comparableSignals": ["잔혹 묘사", "성적 묘사", "이세계 전생", "귀족"],
    "synopsis": "주인공은 유혈이 낭자한 복수극 속에서 연령제한 설정과 R18 표시가 필요할 수 있는 사건을 추적한다.",
}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 게시 전 확인하면 좋은 규정",
        "",
        "이 섹션은 위반 판단이 아니라 게시 전 확인 후보입니다.",
        "",
    ]
    cards = report.get("policy_attention_cards") or []
    if not cards:
        lines.append("현재 입력에서 자동으로 표시된 규정 확인 후보는 없습니다.")
    for card in cards:
        lines.extend(
            [
                f"## {card['card_title']}",
                "",
                f"- 상태: {card['status_label']}",
                f"- 심각도: {card['severity']}",
                f"- 매칭 출처: {card['match_source']}",
                f"- 플랫폼: {card['platform_display_name']}",
                f"- 규칙 ID: {', '.join(card['matched_rule_ids'])}",
                f"- 매칭 요소: {', '.join(card['matched_elements'])}",
                "",
                card["display_sentence"],
                "",
            ]
        )
        if card.get("source_refs"):
            lines.append("출처:")
            for ref in card["source_refs"]:
                lines.append(f"- {ref['label']}: {ref['url']}")
            lines.append("")
    lines.extend(["## 한계", ""])
    for item in report.get("policy_limitations") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> None:
    docs = Path("docs")
    docs.mkdir(exist_ok=True)
    report = build_policy_attention_report(SAMPLE_PAYLOAD)
    ui_payload = {
        "policyAttentionCards": report["policy_attention_cards"],
        "policyLimitations": report["policy_limitations"],
    }
    _write_json(docs / "regulation_policy_sample.json", {"input": SAMPLE_PAYLOAD, **report})
    _write_json(docs / "regulation_policy_sample.ui.json", ui_payload)
    (docs / "regulation_policy_sample.md").write_text(_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "cards": len(report["policy_attention_cards"]),
                "saved": [
                    "docs/regulation_policy_sample.json",
                    "docs/regulation_policy_sample.ui.json",
                    "docs/regulation_policy_sample.md",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

