from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import api_server


DEFAULT_JSON = Path("docs/live_model_smoke_results.json")
DEFAULT_MD = Path("docs/live_model_smoke_report.md")


def _run_case(
    case_id: str,
    fn: Callable[[], dict[str, Any]],
    check: Callable[[dict[str, Any]], bool],
    *,
    category: str,
) -> dict[str, Any]:
    started = time.time()
    try:
        output = fn()
        passed = check(output)
        return {
            "id": case_id,
            "category": category,
            "status": "pass" if passed else "fail",
            "elapsed_sec": round(time.time() - started, 2),
            "output": output,
        }
    except Exception as exc:  # pragma: no cover - diagnostic runner
        return {
            "id": case_id,
            "category": category,
            "status": "error",
            "elapsed_sec": round(time.time() - started, 2),
            "error": repr(exc),
        }


def _skip_case(case_id: str, *, category: str, reason: str) -> dict[str, Any]:
    return {
        "id": case_id,
        "category": category,
        "status": "skipped",
        "elapsed_sec": 0,
        "reason": reason,
    }


def _translation_case(source_text: str, target_country: str) -> dict[str, Any]:
    result = api_server.translate({"sourceText": source_text, "targetCountry": target_country})
    workflow = result.get("workflow") or {}
    return {
        "locale": result.get("locale"),
        "retrievalCount": result.get("retrievalCount"),
        "finalTranslation": result.get("finalTranslation", ""),
        "reviewSummary": result.get("reviewSummary", ""),
        "inspection": workflow.get("inspection", {}),
        "annotationMatches": workflow.get("annotation_matches", []),
        "retrievals": workflow.get("retrievals", []),
    }


def _chat_case() -> dict[str, Any]:
    return api_server.inspect_chat(
        {
            "targetCountry": "일본",
            "question": "2번째 문장의 사랑해라는 표현이 너무 직역된 것 같아. 일본 문화에 적합하게 수정해줘.",
            "sourceText": "그는 조용히 사랑한다고 말했다.",
            "currentTranslation": "彼は静かに「愛してる」と言った。",
        }
    )


def _guide_case() -> dict[str, Any]:
    result = api_server.guide(
        {
            "targetCountry": "미국",
            "genre": "현대 로맨스",
            "synopsis": "상처를 감춘 여자와 뒤늦게 진실을 알아가는 남자의 정략결혼 로맨스.",
        }
    )
    return {
        "title": result.get("title"),
        "sections": result.get("sections", []),
        "htmlReportSnippet": result.get("htmlReport", "")[:1200],
    }


def _cover_image_case() -> dict[str, Any]:
    result = api_server.cover_image(
        {
            "workTitle": "소나기",
            "targetCountry": "일본",
            "genre": "근대 문학 / 첫사랑",
            "episodes": [
                "징검다리에서 소년과 소녀가 마주쳤다. 얼굴이 검게 탄 소년은 무명 겹저고리에 잠방이 차림으로 서툰 관심을 주고받았다.",
                "비가 내리자 소년은 소녀와 함께 피할 곳을 찾았고, 둘의 감정 거리가 가까워졌다.",
            ],
            "extraPrompt": "썸네일에서 소년과 소녀의 첫사랑 분위기가 바로 보이도록 구성",
        }
    )
    return {
        "type": result.get("type"),
        "model": result.get("model"),
        "notice": result.get("notice", "AI 생성 이미지입니다." if result.get("type") in {"base64", "url"} else ""),
        "dataPreview": str(result.get("data", ""))[:120],
    }


def _relation_image_case() -> dict[str, Any]:
    result = api_server.relation_image(
        {
            "workTitle": "소나기",
            "episodes": [
                "소년은 소녀에게 설렘과 호감을 느꼈고, 소녀는 소년에게 장난스럽게 관심을 보였다.",
            ],
            "extraPrompt": "clean relationship map",
        }
    )
    return {
        "type": result.get("type"),
        "model": result.get("model"),
        "notice": result.get("notice", "AI 생성 이미지입니다." if result.get("type") in {"base64", "url"} else ""),
        "dataPreview": str(result.get("data", ""))[:120],
    }


def run(live: bool, include_images: bool) -> list[dict[str, Any]]:
    os.environ["WLIGHTER_MOCK_MODE"] = "false" if live else "true"
    cases: list[tuple[str, str, Callable[[], dict[str, Any]], Callable[[dict[str, Any]], bool]]] = [
        (
            "TST-TRANS-001",
            "translation",
            lambda: _translation_case(
                "그러다가 소녀가 물 속에서 무엇을 하나 집어 낸다. 하얀 조약돌이었다. "
                "그리고는 벌떡 일어나 팔짝팔짝 징검다리를 뛰어 건너간다.",
                "일본",
            ),
            lambda out: out.get("locale") == "ko_ja" and bool(out.get("finalTranslation")) and bool(out.get("inspection")),
        ),
        (
            "TST-TRANS-002",
            "translation",
            lambda: _translation_case(
                "“에이, 오라질년, 조랑복은 할 수가 없어, 못 먹어 병, 먹어서 병! "
                "어쩌란 말이야! 왜 눈을 바루 뜨지 못해!” 하고 앓는 이의 뺨을 한 번 후려갈겼다.",
                "중국",
            ),
            lambda out: (out.get("inspection") or {}).get("recommended_action") in {"ADAPT", "REVISE", "NOTE"},
        ),
        (
            "TST-TRANS-003",
            "translation",
            lambda: _translation_case(
                "1회차에서 김첨지가 등장했다. 이날이야말로 동소문 안에서 인력거꾼 노릇을 하는 김첨지에게는 "
                "오래간만에도 닥친 운수 좋은 날이었다. 2회차에서도 김첨지가 다시 등장했다.",
                "태국",
            ),
            lambda out: bool(out.get("finalTranslation")),
        ),
        (
            "TST-CHAT-001",
            "chat",
            _chat_case,
            lambda out: bool(out.get("answer")) and bool(out.get("proposedTranslation")) and out.get("needsUserConfirmation") is True,
        ),
        (
            "TST-GDE-001",
            "guide",
            _guide_case,
            lambda out: "작성 방향" in out.get("htmlReportSnippet", "") and len(out.get("sections", [])) >= 3,
        ),
    ]
    results = [_run_case(case_id, fn, check, category=category) for case_id, category, fn, check in cases]
    image_cases: list[tuple[str, Callable[[], dict[str, Any]], Callable[[dict[str, Any]], bool]]] = [
        (
            "TST-IMG-001",
            _cover_image_case,
            lambda out: out.get("type") in {"base64", "url", "mock_image"} and bool(out.get("model")),
        ),
        (
            "TST-IMG-002",
            _relation_image_case,
            lambda out: out.get("type") in {"base64", "url", "mock_image"} and bool(out.get("model")),
        ),
    ]
    if include_images:
        results.extend(_run_case(case_id, fn, check, category="image") for case_id, fn, check in image_cases)
    else:
        reason = "Skipped by default because image generation makes billable API calls; rerun with --include-images."
        results.extend(_skip_case(case_id, category="image", reason=reason) for case_id, _, _ in image_cases)
    return results


def write_markdown(results: list[dict[str, Any]], path: Path, live: bool) -> None:
    lines = [
        "# Live Model Smoke Report",
        "",
        f"- Mode: {'live OpenAI API' if live else 'mock'}",
        f"- Passed: {sum(row['status'] == 'pass' for row in results)} / {sum(row['status'] != 'skipped' for row in results)} executed",
        f"- Skipped: {sum(row['status'] == 'skipped' for row in results)}",
        "",
        "| Test ID | Category | Status | Seconds | Summary |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for row in results:
        output = row.get("output") or {}
        summary = (
            output.get("finalTranslation")
            or output.get("answer")
            or output.get("title")
            or output.get("notice")
            or row.get("reason")
            or row.get("error", "")
        )
        summary = str(summary).replace("\n", " ")[:180]
        lines.append(f"| {row['id']} | {row['category']} | {row['status']} | {row['elapsed_sec']} | {summary} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run model-facing smoke tests from the final test report.")
    parser.add_argument("--mock", action="store_true", help="Run without live OpenAI calls.")
    parser.add_argument(
        "--include-images",
        action="store_true",
        help="Also run billable image-generation smoke cases.",
    )
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    live = not args.mock
    results = run(live=live, include_images=args.include_images)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(results, args.md_out, live=live)
    executed = [row for row in results if row["status"] != "skipped"]
    print(
        json.dumps(
            {
                "live": live,
                "include_images": args.include_images,
                "passed": sum(row["status"] == "pass" for row in executed),
                "executed": len(executed),
                "skipped": sum(row["status"] == "skipped" for row in results),
                "total": len(results),
            },
            ensure_ascii=False,
        )
    )
    if any(row["status"] not in {"pass", "skipped"} for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
