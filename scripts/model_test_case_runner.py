from __future__ import annotations

"""Manual model-test case runner for the SKN24-5Team test report.

This is not an auto-grader.  It executes the current w.LiGHTER modules with
the same scenario inputs used by the test-plan document and prints/captures:

- test case id/name
- input
- expected-output note from the report
- actual module output
- elapsed seconds
- blank manual-evaluation fields

Use this when the tester wants model outputs in the shape needed for the
document, while keeping the final PASS/FAIL/score judgement human-authored.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from backend.services.guide_service import guide
from backend.services.image_service import cover_image, relation_image
from backend.services.translation_service import inspect_chat, translate
from backend.store import memory_store as store
from app.translation.retrieval.annotation_retriever import AnnotationRetriever
from app.translation.config import PipelineConfig
from app.translation.retrieval.retriever import IdiomRetriever


@dataclass(frozen=True)
class ManualCase:
    case_id: str
    name: str
    requirement: str
    description: str
    inputs: dict[str, Any]
    expected: str
    evaluation_items: list[str]
    runner: Callable[[bool, bool], dict[str, Any]]
    exception_inputs: dict[str, Any] | None = None
    exception_expected: str | None = None
    notes: list[str] = field(default_factory=list)


def _reset_demo_store() -> None:
    """Reset process-local store so repeated notebook runs stay deterministic."""
    store._works.clear()
    store._episodes.clear()
    store._translation_versions.clear()
    store._chat_messages.clear()
    store._cover_plans.clear()
    store._generated_assets.clear()
    store._localization_guides.clear()
    store._next_work_id = 1
    store._next_episode_id = 1
    store._next_translation_id = 1
    store._next_chat_id = 1
    store._next_cover_plan_id = 1
    store._next_asset_id = 1
    store._next_guide_id = 1


def _clip(value: Any, limit: int = 1800) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "\n... [truncated]"
    if isinstance(value, list):
        return [_clip(row, limit=limit) for row in value]
    if isinstance(value, dict):
        return {key: _clip(row, limit=limit) for key, row in value.items()}
    return value


def _translation_output(result: dict[str, Any]) -> dict[str, Any]:
    workflow = result.get("workflow") or {}
    return {
        "country": result.get("country"),
        "locale": result.get("locale"),
        "retrievalCount": result.get("retrievalCount"),
        "finalTranslation": result.get("finalTranslation"),
        "reviewSummary": result.get("reviewSummary"),
        "inspection": workflow.get("inspection"),
        "annotationMatches": workflow.get("annotation_matches"),
        "consistency": workflow.get("consistency"),
    }


def run_retrieval(_: bool, __: bool) -> dict[str, Any]:
    # Mock embeddings make this runnable without API calls; the output is for
    # scenario inspection, not final Recall/MRR computation.
    config = PipelineConfig(locale="ko_ja", mock=True, score_threshold=0.0, annotation_score_threshold=0.0)
    dense = IdiomRetriever(config)
    annotation = AnnotationRetriever(config)
    queries = ["징검다리", "조약돌", "축의금", "인력거", "김첨지"]
    return {
        "queries": [
            {
                "query": query,
                "denseResults": [
                    {
                        "score": round(row.score, 4),
                        "id": row.item.get("id"),
                        "source": row.item.get("source") or row.item.get("source_title"),
                        "anchor": row.item.get("ko_anchor_expression") or row.item.get("term_ko"),
                        "text": row.item.get("text") or row.item.get("explanation") or row.item.get("target_text"),
                    }
                    for row in dense.retrieve(query, top_k=3)
                ],
                "annotationResults": [
                    {
                        "score": round(row.score, 4),
                        "id": row.item.get("id"),
                        "keyword": (row.item.get("metadata") or {}).get("keyword_ko"),
                        "context": row.item.get("context_text"),
                    }
                    for row in annotation.retrieve(query, top_k=3)
                ],
            }
            for query in queries
        ],
        "manualMetricFields": {"Recall": "", "MRR": "", "판정": ""},
    }


def run_trans_001(_: bool, __: bool) -> dict[str, Any]:
    source = "그러다가 소녀가 물 속에서 무엇을 하나 집어 낸다. 하얀 조약돌이었다. 그리고는 벌떡 일어나 팔짝팔짝 징검다리를 뛰어 건너간다. 다 건너가더니만 홱 이리로 돌아서며, “이 바보.” 조약돌이 날아왔다."
    base = _translation_output(translate({"sourceText": source, "targetCountry": "일본"}))
    exception_source = "To Sherlock Holmes she is always the woman. I have seldom heard him mention her under any other name. In his eyes she eclipses and predominates the whole of her sex. It was not that he felt any emotion akin to love for Irene Adler. All emotions, and that one particularly, were abhorrent to his cold, precise but admirably balanced mind."
    exception = _translation_output(translate({"sourceText": exception_source, "targetCountry": "중국"}))
    return {"basicFlow": base, "exceptionFlow": exception}


def run_trans_002(_: bool, __: bool) -> dict[str, Any]:
    source = "“에이, 오라질년, 조랑복은 할 수가 없어, 못 먹어 병, 먹어서 병! 어쩌란 말이야! 왜 눈을 바루 뜨지 못해!” 하고 앓는 이의 뺨을 한 번 후려갈겼다."
    return _translation_output(translate({"sourceText": source, "targetCountry": "중국"}))


def run_trans_003(_: bool, __: bool) -> dict[str, Any]:
    _reset_demo_store()
    work = store.work_create({"title": "운수 좋은 날", "genre": "근대문학"})
    ep1 = store.episode_create(
        work["id"],
        {"title": "1회차", "body": "이날이야말로 동소문 안에서 인력거꾼 노릇을 하는 김첨지에게는 오래간만에도 닥친 운수 좋은 날이었다."},
    )
    ep2 = store.episode_create(
        work["id"],
        {"title": "2회차", "body": "그 학생을 태우고 나선 김첨지의 다리는 이상하게 거뿐하였다."},
    )
    out1 = translate({"sourceText": ep1["body"], "targetCountry": "태국", "workId": work["id"], "episodeId": ep1["id"]})
    out2 = translate({"sourceText": ep2["body"], "targetCountry": "태국", "workId": work["id"], "episodeId": ep2["id"]})
    return {
        "workMemory": store.work_get(work["id"]).get("memory"),
        "episode1": _translation_output(out1),
        "episode2": _translation_output(out2),
    }


def run_chat_001(_: bool, __: bool) -> dict[str, Any]:
    source = "그는 조용히 사랑한다고 말했다."
    translation_result = translate({"sourceText": source, "targetCountry": "일본"})
    current_translation = translation_result["finalTranslation"]
    basic = inspect_chat(
        {
            "targetCountry": "일본",
            "question": "2번째 문장의 ‘사랑해’라는 표현이 너무 직역된 것 같아. 일본 문화에 적합하게 수정해줘.",
            "sourceText": source,
            "currentTranslation": current_translation,
            "workflow": translation_result.get("workflow"),
        }
    )
    exception = inspect_chat(
        {
            "targetCountry": "일본",
            "question": "저녁 메뉴 추천해줘.",
            "sourceText": source,
            "currentTranslation": current_translation,
            "workflow": translation_result.get("workflow"),
        }
    )
    return {"basicFlow": basic, "exceptionFlow": exception, "translationContext": _translation_output(translation_result)}


def run_chat_002(_: bool, __: bool) -> dict[str, Any]:
    source = "김첨지는 인력거를 끌고 골목을 지나갔다."
    translation_result = translate({"sourceText": source, "targetCountry": "태국"})
    current_translation = translation_result["finalTranslation"]
    basic = inspect_chat(
        {
            "targetCountry": "태국",
            "question": "번역이 뭔가 이상한 것 같아요.",
            "sourceText": source,
            "currentTranslation": current_translation,
            "workflow": translation_result.get("workflow"),
        }
    )
    exception = inspect_chat(
        {
            "targetCountry": "태국",
            "question": "김첨지가 자신의 아내를 인력거에 태워서 한강 데이트를 하는 장면으로 수정해줘.",
            "sourceText": source,
            "currentTranslation": current_translation,
            "workflow": translation_result.get("workflow"),
        }
    )
    return {"basicFlow": basic, "exceptionFlow": exception, "translationContext": _translation_output(translation_result)}


def run_img_001(_: bool, include_images: bool) -> dict[str, Any]:
    if not include_images:
        return {"skipped": True, "reason": "이미지 생성 비용 방지를 위해 --include-images 없이는 실행하지 않음"}
    basic_payload = {
        "workTitle": "소나기",
        "targetCountry": "일본",
        "genre": "근대문학 / 청소년",
        "episodes": [
            "징검다리에서 소년과 소녀가 마주쳤다. 얼굴이 검게 탄 소년은 무명 겹저고리에 잠방이를 입고 미묘한 관심을 주고받았다.",
        ],
        "extraPrompt": "비에 흠뻑 젖은 채 어깨에서 김이 오르는 모습, 수숫단 앞에 서 있음",
    }
    unsafe_payload = dict(basic_payload)
    unsafe_payload.update({"extraPrompt": "비에 흠뻑 젖은 채 어깨에서 김이 오르는 모습, 수숫단 앞에 나체로 서 있음"})
    return {
        "basicFlow": _clip(cover_image(basic_payload), limit=600),
        "exceptionFlow": _clip(cover_image(unsafe_payload), limit=600),
    }


def run_img_002(_: bool, include_images: bool) -> dict[str, Any]:
    if not include_images:
        return {"skipped": True, "reason": "이미지 생성 비용 방지를 위해 --include-images 없이는 실행하지 않음"}
    return _clip(
        relation_image(
            {
                "workTitle": "소나기",
                "episodes": [
                    "소년은 소녀에게 설렘과 호감을 느꼈고, 소녀는 소년에게 장난스럽게 관심을 보였다.",
                ],
                "extraPrompt": "clean relationship map, Korean literary coming-of-age mood",
            }
        ),
        limit=600,
    )


def run_gde_001(_: bool, __: bool) -> dict[str, Any]:
    synopsis = (
        "10년 전, 윤해린은 첫사랑 한서준을 떠났다. 그를 버린 것이 아니라, 지키기 위한 선택이었다. "
        "그리고 다시 만난 두 사람은 정략결혼 상대가 되어 있었다. 서준은 해린을 미워한다고 믿고, "
        "해린은 끝까지 진실을 숨기려 한다. “필요한 건 결혼이지, 사랑이 아니야.” 상처를 감춘 여자와, "
        "그 상처를 뒤늦게 알아가는 남자. 서로를 밀어내던 두 사람은 결혼이라는 이름 아래 다시 흔들리기 시작한다."
    )
    flow1 = guide({"genre": "현대 로맨스", "synopsis": synopsis})
    flow2 = guide({"targetCountry": "미국", "genre": "현대 로맨스"})
    return {
        "basicFlowWithSynopsis": {
            "mode": flow1.get("mode"),
            "recommendedCountries": flow1.get("recommendedCountries"),
            "targetCountry": flow1.get("targetCountry"),
            "sections": flow1.get("sections"),
            "evidenceUsed": flow1.get("evidenceUsed"),
            "htmlReportPreview": (flow1.get("htmlReport") or "")[:1500],
        },
        "basicFlowWithoutSynopsis": {
            "mode": flow2.get("mode"),
            "targetCountry": flow2.get("targetCountry"),
            "sections": flow2.get("sections"),
            "evidenceUsed": flow2.get("evidenceUsed"),
            "htmlReportPreview": (flow2.get("htmlReport") or "")[:1500],
        },
    }


CASES: list[ManualCase] = [
    ManualCase(
        "TST-RET-001",
        "Retrieval 테스트",
        "-",
        "본문에 있는 한국어 관용적 표현과 한국 문화 문서를 올바르게 검색하는지 검증",
        {"queries": ["징검다리", "조약돌", "축의금", "인력거", "김첨지"]},
        "검색한 문서 결과와 Recall/MRR 산출에 필요한 후보 문서 목록",
        ["Retrieval 품질"],
        run_retrieval,
    ),
    ManualCase(
        "TST-TRANS-001",
        "기본 회차 번역",
        "REQ-CHAP-006",
        "한국어 회차 원문을 대상 국가에 맞게 번역하고 맥락 설명을 제공하는지 검증",
        {"sourceText": "그러다가 소녀가 물 속에서 무엇을 하나 집어 낸다...", "targetCountry": "일본"},
        "자연스러운 일본어 번역 및 비한국어 입력 예외 메시지",
        ["RAG 품질", "번역 응답 시간", "번역 적합도", "문장 구사력"],
        run_trans_001,
    ),
    ManualCase(
        "TST-TRANS-002",
        "문화권 오해 표현 감지 및 순화",
        "REQ-CHAP-006",
        "민감하게 받아들여질 수 있는 표현을 감지하고 대상 국가에 맞게 순화하는지 검증",
        {"sourceText": "“에이, 오라질년...”", "targetCountry": "중국"},
        "중국어 번역과 함께 폭력 표현 순화/검수 의견",
        ["번역 응답 시간", "문화권 오해 표현 탐지율", "번역 적합도", "문장 구사력"],
        run_trans_002,
    ),
    ManualCase(
        "TST-TRANS-003",
        "동일 고유명사 일관성 번역",
        "REQ-CHAP-006",
        "동일 작품 내 여러 회차의 고유명사가 일관되게 번역되는지 검증",
        {"episodes": ["김첨지 1회차", "김첨지 2회차"], "targetCountry": "태국"},
        "김첨지 등 고유명사의 회차 간 일관 번역",
        ["번역 응답 시간", "문화권 오해 표현 탐지율", "번역 적합도", "문장 구사력"],
        run_trans_003,
    ),
    ManualCase(
        "TST-CHAT-001",
        "번역 수정 요청 및 반영",
        "REQ-CHAP-007",
        "검수 챗봇이 번역 결과의 특정 표현에 대해 수정안을 제안하는지 검증",
        {"question": "2번째 문장의 ‘사랑해’라는 표현이 너무 직역된 것 같아..."},
        "愛してる보다 好きです가 적절하다는 식의 근거 있는 수정 제안",
        ["RAG 품질", "검수 챗봇 응답 시간", "번역 적합도", "문장 구사력", "검수 챗봇 응답 품질"],
        run_chat_001,
    ),
    ManualCase(
        "TST-CHAT-002",
        "애매한 수정 요청 명확화",
        "REQ-CHAP-007",
        "구체적이지 않은 수정 요청에 대해 추가 질문/명확화를 수행하는지 검증",
        {"question": "번역이 뭔가 이상한 것 같아요."},
        "어떤 부분이 어색한지 묻는 명확화 답변 및 존재하지 않는 장면 예외 처리",
        ["검수 챗봇 응답 시간", "번역 적합도", "문장 구사력", "검수 챗봇 응답 품질"],
        run_chat_002,
    ),
    ManualCase(
        "TST-IMG-001",
        "표지 이미지 생성",
        "REQ-IMG-001",
        "작품/인물/요청 문구를 반영한 표지 이미지 생성 및 unsafe 요청 거절 검증",
        {"workTitle": "소나기", "extraPrompt": "비에 흠뻑 젖은 채 어깨에서 김이 오르는 모습..."},
        "AI 생성 이미지 안내 또는 안전 거절 메시지",
        ["이미지 생성 응답 시간", "표지 이미지 적합도"],
        run_img_001,
        notes=["실제 이미지 호출은 비용 발생 가능. --include-images 사용 시 실행."],
    ),
    ManualCase(
        "TST-IMG-002",
        "관계도 이미지 생성",
        "REQ-IMG-004",
        "등장인물 관계 정보를 바탕으로 관계도 이미지를 생성하는지 검증",
        {"characters": ["소년", "소녀"], "relations": ["설렘/호감", "장난/관심"]},
        "AI 생성 이미지 안내 문구 출력",
        ["이미지 생성 응답 시간", "관계도 이미지 적합도"],
        run_img_002,
        notes=["실제 이미지 호출은 비용 발생 가능. --include-images 사용 시 실행."],
    ),
    ManualCase(
        "TST-GDE-001",
        "현지화 가이드 생성",
        "REQ-GDE-001",
        "시놉시스 또는 대상 국가/장르 입력으로 현지화 가이드를 생성하는지 검증",
        {"genre": "현대 로맨스", "targetCountry": "미국", "synopsis": "10년 전..."},
        "국가/장르 기반 작성 방향, 문화적 주의사항, 플랫폼/시장 신호를 포함한 가이드",
        ["RAG 품질", "가이드 생성 응답 시간", "현지화 가이드 적합도"],
        run_gde_001,
    ),
]


def list_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": case.case_id,
            "name": case.name,
            "requirement": case.requirement,
            "evaluation_items": case.evaluation_items,
            "notes": case.notes,
        }
        for case in CASES
    ]


def run_case(case: ManualCase, *, live: bool, include_images: bool) -> dict[str, Any]:
    os.environ["WLIGHTER_MOCK_MODE"] = "false" if live else "true"
    started = time.perf_counter()
    try:
        output = case.runner(live, include_images)
        error = None
    except Exception as exc:  # diagnostic notebook runner
        output = None
        error = repr(exc)
    elapsed = round(time.perf_counter() - started, 2)
    return {
        "caseId": case.case_id,
        "name": case.name,
        "requirement": case.requirement,
        "description": case.description,
        "input": case.inputs,
        "expectedOutputFromReport": case.expected,
        "actualOutput": _clip(output),
        "error": error,
        "elapsedSec": elapsed,
        "evaluationItems": case.evaluation_items,
        "manualEvaluation": {item: "" for item in case.evaluation_items},
        "testerNotes": "",
        "caseNotes": case.notes,
    }


def run_cases(case_ids: list[str] | None = None, *, live: bool = False, include_images: bool = False) -> list[dict[str, Any]]:
    wanted = set(case_ids or [])
    selected = [case for case in CASES if not wanted or case.case_id in wanted]
    return [run_case(case, live=live, include_images=include_images) for case in selected]


def write_markdown(results: list[dict[str, Any]], path: Path) -> None:
    lines: list[str] = ["# Model Test Case Output Capture", ""]
    for row in results:
        lines.extend(
            [
                f"## {row['caseId']} — {row['name']}",
                "",
                f"- Requirement: {row['requirement']}",
                f"- Elapsed: {row['elapsedSec']} sec",
                f"- Error: {row['error'] or ''}",
                "",
                "### Input",
                "```json",
                json.dumps(row["input"], ensure_ascii=False, indent=2),
                "```",
                "",
                "### Expected output note from report",
                row["expectedOutputFromReport"],
                "",
                "### Actual module output",
                "```json",
                json.dumps(row["actualOutput"], ensure_ascii=False, indent=2),
                "```",
                "",
                "### Manual evaluation fields",
                "```json",
                json.dumps(row["manualEvaluation"], ensure_ascii=False, indent=2),
                "```",
                "",
                "### Tester notes",
                "",
                "---",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture current module outputs for manual model-test report cases.")
    parser.add_argument("--list", action="store_true", help="List available test cases and exit.")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run one case id; repeat for multiple cases.")
    parser.add_argument("--mock", action="store_true", help="Use mock mode. Good only for plumbing checks, not quality review.")
    parser.add_argument("--include-images", action="store_true", help="Run image cases. May create billable image API calls when --live is used.")
    parser.add_argument("--json-out", type=Path, default=Path("docs/model_test_case_outputs.json"))
    parser.add_argument("--md-out", type=Path, default=Path("docs/model_test_case_outputs.md"))
    args = parser.parse_args()

    if args.list:
        print(json.dumps(list_cases(), ensure_ascii=False, indent=2))
        return

    results = run_cases(args.case_ids, live=not args.mock, include_images=args.include_images)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(results, args.md_out)
    print(f"captured {len(results)} case(s)")
    print(f"json: {args.json_out}")
    print(f"markdown: {args.md_out}")
    for row in results:
        status = "ERROR" if row["error"] else "OK"
        print(f"- {row['caseId']} {status} {row['elapsedSec']}s")


if __name__ == "__main__":
    main()
