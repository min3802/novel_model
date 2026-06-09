"""번역 + 검수 챗봇 수동 평가용 통합 스크립트.

테스트 계획 보고서(수동 평가)의 번역/챗봇 항목을 한 번에 실행하고 HTML로 기록한다.
- 번역 실행 + 응답시간(기준 180초, 코드 상수)
- retrieval 가시화: idiom (N / idiom_return_k), kculture (M / annotation_return_k) 상한 준수 확인
- 사용자 산출물: Inspector summary+issues, annotation 주석 후보 리스트
- 검수 챗봇 3종 질문 자동 실행 + 각 응답시간(기준 30초)

실행(실제 LLM):
    WLIGHTER_MOCK_MODE=false python tests/eval_translation_chatbot.py --file 야구소설_1.txt --locale ko_ja --out 평가_ja.html
    WLIGHTER_MOCK_MODE=false python tests/eval_translation_chatbot.py --file 야구소설_1.txt --locale all
    WLIGHTER_MOCK_MODE=false python tests/eval_translation_chatbot.py --file 1화.txt --locale ko_ja --question "이 표현 너무 직역 아냐?"
    WLIGHTER_MOCK_MODE=false python tests/eval_translation_chatbot.py --file 1화.txt --no-chat

옵션:
    --file      회차 원문 텍스트 파일 (필수, 또는 --text)
    --text      한 줄 원문(짧은 테스트)
    --locale    ko_ja | ko_en_us | ko_zh_cn | ko_th_th | all
    --question  챗봇에 던질 질문(지정 시 기본 3종 대신 이 질문만 사용, 반복 지정 가능)
    --no-chat   챗봇 단계 생략(번역만)
    --out       결과 HTML 경로(미지정 시 tests/outputs/eval_<시각>.html)

필요: OPENAI_API_KEY(.env), sentence-transformers(KURE), qdrant_local. mock 모드면 결정적 더미 출력.
"""
from __future__ import annotations

import argparse
import html as _html
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트(이 파일의 부모의 부모)를 import 경로에 추가
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# .env 자동 로드(다른 진단 스크립트와 동일 패턴). export 없이 실행 가능.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.translation.config import PipelineConfig
from backend.services import translation_service as svc

# --- 판정 기준선(보고서 + 사용자 지정) ---
TRANSLATION_TIME_LIMIT_S = 180.0   # 번역 응답시간 기준 (사용자 지정: 3분)
CHATBOT_TIME_LIMIT_S = 30.0        # 검수 챗봇 응답시간 기준 (보고서)

LOCALE_TO_COUNTRY = {
    "ko_ja": "일본",
    "ko_en_us": "미국",
    "ko_zh_cn": "중국",
    "ko_th_th": "태국",
}
ALL_LOCALES = ["ko_ja", "ko_en_us", "ko_zh_cn", "ko_th_th"]

# 기본 챗봇 질문 3종(보고서 검수 챗봇 응답 품질 항목을 자극)
DEFAULT_QUESTIONS = [
    # ① 구체적 수정 요청형 — inspection issues 참조 + 구체 제안 + 사용자 확인
    "검수에서 지적된 표현 중 가장 심각한 부분을 대상 국가 독자에게 자연스럽게 바꿔줘. 어떻게 바꿨는지도 설명해줘.",
    # ② 근거 설명 요청형 — 원문 맥락/rationale 반영(임의 수정 안 하는지)
    "첫 문장을 왜 이렇게 번역했는지 원문 맥락과 함께 설명해줘.",
    # ③ 모호 요청형 — 어디가 문제인지 되묻는지
    "뭔가 좀 어색한 것 같은데?",
    # ④ 무관 잡담형 — 번역 검수 범위를 벗어난 요청을 거절/안내하는지
    "오늘 점심 뭐 먹지?",
    # ⑤ 대화 맥락 유지 검증 — chat_history를 참조해 '맨 처음 요청'을 기억하는지(마지막에 배치)
    "내가 맨 처음에 무슨 요청을 했지?",
]


def _esc(v) -> str:
    return _html.escape(str(v if v is not None else ""))


def _limits_for(locale: str) -> tuple[int, int]:
    cfg = PipelineConfig(locale=locale)
    return cfg.idiom_return_k, cfg.annotation_return_k


def _warmup(locale: str) -> float:
    # 타이머 시작 전에 KURE 임베딩 모델 로딩(+첫 추론)을 끝내둔다.
    # create_embedding_backend가 모델명 기준으로 캐싱하므로, 이후 본 측정은 로딩 없이 추론만 한다.
    # → 측정된 번역 응답시간에서 1회성 모델 로딩이 제외되어 실서비스(상주 모델)에 가깝게 측정됨.
    country = LOCALE_TO_COUNTRY[locale]
    w0 = time.perf_counter()
    svc.translate({"targetCountry": country, "sourceText": "워밍업"})
    return time.perf_counter() - w0


def run_one_locale(locale: str, source_text: str, questions: list[str], do_chat: bool) -> dict:
    country = LOCALE_TO_COUNTRY[locale]
    idiom_limit, anno_limit = _limits_for(locale)

    # --- 0) 워밍업: 모델 로딩을 측정에서 분리 ---
    warmup_elapsed = _warmup(locale)

    # --- 1) 번역 실행 + 시간 측정 (모델 로딩 제외, 순수 번역 응답시간) ---
    t0 = time.perf_counter()
    result = svc.translate({"targetCountry": country, "sourceText": source_text})
    translate_elapsed = time.perf_counter() - t0

    workflow = result.get("workflow", {}) or {}
    retrievals = workflow.get("retrievals", []) or []
    annotations = workflow.get("annotation_matches", []) or []
    inspection = workflow.get("inspection", {}) or {}

    # --- 2) 챗봇 자동 질문 + 시간 측정 ---
    chat_runs = []
    if do_chat:
        chat_history = []
        for q in questions:
            c0 = time.perf_counter()
            reply = svc.inspect_chat({
                "targetCountry": country,
                "question": q,
                "sourceText": source_text,
                "currentTranslation": result.get("finalTranslation", ""),
                "workflow": workflow,
                "chatHistory": chat_history,
            })
            chat_elapsed = time.perf_counter() - c0
            chat_runs.append({"question": q, "elapsed": chat_elapsed, "reply": reply})
            chat_history.append({"role": "user", "content": q})
            chat_history.append({"role": "ai", "content": reply.get("answer", "")})

    return {
        "locale": locale,
        "country": country,
        "idiom_limit": idiom_limit,
        "anno_limit": anno_limit,
        "warmup_elapsed": warmup_elapsed,
        "translate_elapsed": translate_elapsed,
        "result": result,
        "retrievals": retrievals,
        "annotations": annotations,
        "inspection": inspection,
        "chat_runs": chat_runs,
    }


def _pass_fail(ok: bool) -> str:
    return f'<b style="color:{"#1a8a3a" if ok else "#c00"}">{"PASS" if ok else "FAIL"}</b>'


def render_block(run: dict) -> str:
    r = run["result"]
    insp = run["inspection"]
    retrievals = run["retrievals"]
    annotations = run["annotations"]

    # 번역 응답시간 판정
    t_ok = run["translate_elapsed"] <= TRANSLATION_TIME_LIMIT_S
    time_row = (
        f"번역 응답시간(모델 로딩 제외): <b>{run['translate_elapsed']:.1f}s</b> "
        f"(기준 {TRANSLATION_TIME_LIMIT_S:.0f}s) {_pass_fail(t_ok)}"
        f"<br><span class='muted'>참고 · 워밍업(모델 로딩+첫 추론) 1회: {run.get('warmup_elapsed', 0):.1f}s</span>"
    )

    # idiom 표
    idiom_n = len(retrievals)
    idiom_over = idiom_n > run["idiom_limit"]
    idiom_rows = "".join(
        f"<tr><td>{(row.get('similarity_score') or row.get('score') or 0):.3f}</td>"
        f"<td>{_esc((row.get('item') or {}).get('source_id') or (row.get('item') or {}).get('id'))}</td>"
        f"<td>{_esc(str((row.get('item') or {}).get('embedding_text',''))[:90])}</td></tr>"
        for row in retrievals
    ) or "<tr><td colspan=3>(없음)</td></tr>"
    idiom_badge = (
        f'<span style="color:{"#c00" if idiom_over else "#1a8a3a"}">'
        f'{idiom_n} / {run["idiom_limit"]}{" ⚠ 상한 초과" if idiom_over else ""}</span>'
    )

    # annotation(kculture) 표
    anno_n = len(annotations)
    anno_over = anno_n > run["anno_limit"]
    anno_rows = "".join(
        f"<tr><td>{(row.get('similarity_score') or row.get('score') or 0):.3f}</td>"
        f"<td>{_esc((row.get('item') or {}).get('keyword_ko'))}</td>"
        f"<td>{_esc((row.get('item') or {}).get('category'))}</td>"
        f"<td>{_esc(str((row.get('item') or {}).get('context_text',''))[:80])}</td></tr>"
        for row in annotations
    ) or "<tr><td colspan=4>(없음)</td></tr>"
    anno_badge = (
        f'<span style="color:{"#c00" if anno_over else "#1a8a3a"}">'
        f'{anno_n} / {run["anno_limit"]}{" ⚠ 상한 초과" if anno_over else ""}</span>'
    )

    # Inspector issues
    issues = insp.get("issues", []) or []
    issues_html = "".join(
        f"<li><b>[{_esc(it.get('severity'))}]</b> {_esc(it.get('problem'))}"
        f"<br><small>원문: {_esc(it.get('source_span'))}<br>"
        f"번역: {_esc(it.get('translated_span'))} → 제안: {_esc(it.get('suggested')) or '(제안 없음)'}<br>"
        f"맥락: {_esc(it.get('context'))}</small></li>"
        for it in issues
    ) or "<li>(검출된 issue 없음)</li>"

    # annotation 주석 후보 리스트(사용자가 받는 산출물)
    anno_list = "".join(
        f"<li><b>{_esc((row.get('item') or {}).get('keyword_ko'))}</b> "
        f"<small>{_esc(str((row.get('item') or {}).get('context_text',''))[:160])}</small></li>"
        for row in annotations
    ) or "<li>(주석 후보 없음)</li>"

    # 챗봇 Q&A
    chat_html = ""
    for run_i in run["chat_runs"]:
        reply = run_i["reply"]
        c_ok = run_i["elapsed"] <= CHATBOT_TIME_LIMIT_S
        chat_html += (
            f'<div class="qa">'
            f'<p class="q">Q. {_esc(run_i["question"])}</p>'
            f'<p class="muted">응답시간: <b>{run_i["elapsed"]:.1f}s</b> (기준 {CHATBOT_TIME_LIMIT_S:.0f}s) {_pass_fail(c_ok)}'
            f' · 확인필요(needsUserConfirmation): {_esc(reply.get("needsUserConfirmation"))}</p>'
            f'<p class="a">A. {_esc(reply.get("answer"))}</p>'
            f'<div class="box">제안 번역: {_esc(reply.get("proposedTranslation")) or "(변경 없음)"}</div>'
            f'<p class="muted">변경요약: {_esc(reply.get("changeSummary"))}</p>'
            f'</div>'
        )
    if not run["chat_runs"]:
        chat_html = "<p class='muted'>(챗봇 단계 생략됨 --no-chat)</p>"

    return f"""
<section>
  <h2>{_esc(run['country'])} ({_esc(run['locale'])})</h2>
  <p class="metric">{time_row}</p>

  <h3>① 검색 — idiom 반환 {idiom_badge}</h3>
  <table><tr><th>score</th><th>source_id</th><th>embedding_text</th></tr>{idiom_rows}</table>

  <h3>① 검색 — annotation/kculture 반환 {anno_badge}</h3>
  <table><tr><th>score</th><th>keyword</th><th>category</th><th>context</th></tr>{anno_rows}</table>

  <h3>② 최종 번역</h3>
  <div class="box final">{_esc(r.get('finalTranslation'))}</div>

  <h3>③ 사용자 산출물 — 검수(Inspector)</h3>
  <p>요약: {_esc(insp.get('summary'))}</p>
  <p>문제(issues) {len(issues)}건:</p><ul>{issues_html}</ul>

  <h3>③ 사용자 산출물 — 주석(역주) 후보 {len(annotations)}건</h3>
  <ul>{anno_list}</ul>

  <h3>④ 검수 챗봇 Q&amp;A</h3>
  {chat_html}
</section>
"""


def render_html(source_text: str, blocks: list[str]) -> str:
    style = """
    body{font-family:system-ui,'Malgun Gothic',sans-serif;max-width:960px;margin:24px auto;padding:0 16px;line-height:1.6;color:#222}
    h1{border-bottom:2px solid #333;padding-bottom:8px}
    h2{margin-top:36px;background:#eef4fb;padding:8px 12px;border-radius:6px}
    h3{margin-top:20px;color:#1a6}
    table{border-collapse:collapse;width:100%;margin:8px 0;font-size:.9em}
    th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}
    th{background:#f7f7f7}
    .box{background:#fafafa;border:1px solid #e0e0e0;border-radius:6px;padding:12px;white-space:pre-wrap}
    .box.final{background:#eef9f0;border-color:#bce3c5}
    .src{background:#fff8e1;border:1px solid #ffe082;border-radius:6px;padding:12px;white-space:pre-wrap;max-height:260px;overflow:auto}
    .muted{color:#777;font-size:.9em}
    .metric{background:#f3f0fb;border:1px solid #ddd2f0;border-radius:6px;padding:8px 12px}
    .qa{border-left:3px solid #cfe;padding:6px 12px;margin:12px 0;background:#fbfdff}
    .qa .q{font-weight:600}
    .qa .a{white-space:pre-wrap}
    """
    body = "\n".join(blocks)
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>번역·챗봇 평가</title><style>{style}</style></head>
<body>
<h1>번역 · 검수 챗봇 수동 평가 결과</h1>
<p class="muted">생성: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} · mock={os.environ.get("WLIGHTER_MOCK_MODE","")}</p>
<h3>원문 ({len(source_text)}자)</h3>
<div class="src">{_esc(source_text)}</div>
{body}
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--text")
    ap.add_argument("--locale", default="ko_ja")
    ap.add_argument("--question", action="append", default=[])
    ap.add_argument("--no-chat", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.file:
        source_text = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        source_text = args.text
    else:
        print("ERROR: --file 또는 --text 를 지정하세요.")
        return 2

    locales = ALL_LOCALES if args.locale == "all" else [args.locale]
    for loc in locales:
        if loc not in LOCALE_TO_COUNTRY:
            print(f"ERROR: 알 수 없는 locale {loc}")
            return 2

    questions = args.question or DEFAULT_QUESTIONS
    do_chat = not args.no_chat

    blocks = []
    for loc in locales:
        print(f"[실행] {loc} ...", flush=True)
        run = run_one_locale(loc, source_text, questions, do_chat)
        print(f"  워밍업 {run.get('warmup_elapsed',0):.1f}s | 번역 {run['translate_elapsed']:.1f}s | idiom {len(run['retrievals'])}/{run['idiom_limit']}"
              f" | kculture {len(run['annotations'])}/{run['anno_limit']}"
              f" | issues {len(run['inspection'].get('issues',[]))}"
              f" | chat {len(run['chat_runs'])}건", flush=True)
        blocks.append(render_block(run))

    out_path = Path(args.out) if args.out else (
        ROOT / "tests" / "outputs" / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(source_text, blocks), encoding="utf-8")
    print(f"\n[저장] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
