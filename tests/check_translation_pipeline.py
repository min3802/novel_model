"""
번역 파이프라인 전체 흐름 검증 (mock=False, 실제 LLM).

실행: (프로젝트 루트에서)
    python tests/check_translation_pipeline.py
    python tests/check_translation_pipeline.py --locale ko_en_us
    python tests/check_translation_pipeline.py --locale all          # 4개 국어 한 번에
    python tests/check_translation_pipeline.py --text "번역할 한국어 문장"
    python tests/check_translation_pipeline.py --file 1화.txt        # 긴 원문(웹소설 1화 등)
    python tests/check_translation_pipeline.py --file 1화.txt --locale ko_ja
    python tests/check_translation_pipeline.py --file 1화.txt --out 결과.html  # HTML로 저장

옵션:
    --locale  ko_ja | ko_en_us | ko_zh_cn | ko_th_th | all
    --text    한 줄 원문 (짧은 테스트용)
    --file    원문 텍스트 파일 경로. --text 보다 우선.
    --out     결과 HTML 저장 경로(미지정 시 tests/outputs/translation_result_<시각>.html 자동 생성)
              ※ 상대경로는 "실행하는 폴더(현재 디렉토리)" 기준으로 찾는다.
                예) 프로젝트 루트에서 실행하면 루트의 1화.txt 를 찾음(tests 폴더 아님).
                확실히 하려면 절대경로나 data/1화.txt 처럼 정확한 경로 사용.

확인 내용 (run_with_inspection 한 번):
    원문 → [검색: idiom + annotation] → [번역 gpt-4.1-mini] → [검수] → [inspect]
각 단계 결과를 콘솔에 출력하고, 보기 좋은 HTML 파일로도 저장한다(--out).

필요: OPENAI_API_KEY(.env), sentence-transformers(KURE), qdrant_local.
mock 은 강제로 끈다(WLIGHTER_MOCK_MODE=false).
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# 이 스크립트는 tests/ 안에 있지만, 프로젝트 루트의 app.translation 을 import 해야 한다.
# 어디서 실행하든(루트/ tests 폴더 등) 동작하도록 루트를 sys.path 에 추가한다.
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import argparse
import os
import sys
import time
import html as _html
from datetime import datetime

OK = "[OK]"
NO = "[FAIL]"


def section(t: str) -> None:
    print(f"\n{'='*64}\n{t}\n{'='*64}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", default="ko_ja",
                        help="ko_ja | ko_en_us | ko_zh_cn | ko_th_th | all (기본 ko_ja)")
    parser.add_argument("--text", default="자업자득이라더니, 결국 본인이 한 행동의 결과를 받는 거지.")
    parser.add_argument("--file", default=None,
                        help="번역할 원문이 담긴 텍스트 파일 경로(웹소설 1화 등 긴 원문). 지정 시 --text 무시.")
    parser.add_argument("--out", default=None,
                        help="결과를 저장할 HTML 파일 경로. 미지정 시 tests/outputs/translation_result_<시각>.html")
    args = parser.parse_args()

    # 입력 텍스트 결정: --file 우선, 없으면 --text
    if args.file:
        from pathlib import Path as _P
        fp = _P(args.file)
        if not fp.exists():
            print(f"{NO} 파일을 찾을 수 없습니다: {fp}")
            return 1
        source_text = fp.read_text(encoding="utf-8")
        print(f"[입력] 파일에서 {len(source_text)}자 읽음: {fp}")
    else:
        source_text = args.text

    os.environ["WLIGHTER_MOCK_MODE"] = "false"  # 실제 모드 강제

    # .env 로드(있으면)
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except Exception:
        pass

    section("0) 사전 점검")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        print(f"{NO} OPENAI_API_KEY 가 없습니다. .env 에 키를 넣어주세요.")
        return 1
    print(f"{OK} OPENAI_API_KEY 감지됨")
    try:
        import sentence_transformers  # noqa: F401
        print(f"{OK} sentence-transformers 설치됨")
    except ImportError:
        print(f"{NO} sentence-transformers 없음 → pip install sentence-transformers")
        return 1

    try:
        from app.translation import TranslationPipeline, PipelineConfig
    except Exception as exc:
        print(f"{NO} 패키지 import 실패: {exc!r}")
        return 1

    locales = ["ko_ja", "ko_en_us", "ko_zh_cn", "ko_th_th"] if args.locale == "all" else [args.locale]
    overall_ok = True
    html_blocks = []
    for loc in locales:
        section(f"########## LOCALE: {loc} ##########")
        rc, block = run_one(loc, source_text)
        html_blocks.append(block)
        if rc != 0:
            overall_ok = False

    # HTML 저장
    from pathlib import Path as _P
    if args.out:
        out_path = _P(args.out)
    else:
        out_dir = _ROOT / "tests" / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"translation_result_{datetime.now():%Y%m%d_%H%M%S}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_render_html(source_text, html_blocks), encoding="utf-8")
    print(f"\n{OK} 결과 HTML 저장: {out_path}")
    return 0 if overall_ok else 1


def run_one(locale: str, text: str):  # -> (rc:int, html_block:str)
    from app.translation import TranslationPipeline, PipelineConfig
    cfg = PipelineConfig(locale=locale, mock=False)
    print(f"   locale={cfg.locale}  translation_model={cfg.translation_model}  "
          f"chunk_strategy={cfg.chunk_strategy}")

    section("1) 파이프라인 생성 (KURE 로딩 + qdrant 연결)")
    t0 = time.time()
    try:
        pipe = TranslationPipeline(cfg)
        print(f"{OK} 생성 완료 ({time.time()-t0:.1f}s)")
    except Exception as exc:
        print(f"{NO} 생성 실패: {exc!r}")
        return 1, f"<section><h2>{locale}</h2><p class='fail'>생성 실패: {_html.escape(repr(exc))}</p></section>"

    section("2) run_with_inspection 실행 (검색→번역→검수→inspect)")
    print(f"   원문: {text}")
    t1 = time.time()
    try:
        result = pipe.run_with_inspection(text)
        elapsed = time.time() - t1
        print(f"{OK} 전체 실행 완료 ({elapsed:.1f}s)")
    except Exception as exc:
        print(f"{NO} 실행 실패: {exc!r}")
        import traceback
        traceback.print_exc()
        return 1, f"<section><h2>{locale}</h2><p class='fail'>실행 실패: {_html.escape(repr(exc))}</p></section>"

    section("3) 단계별 결과")
    print(f"[검색] idiom {len(result.retrievals)}건, annotation {len(result.annotation_matches)}건")
    for r in result.retrievals[:3]:
        it = r.get("item", {})
        print(f"   - idiom score={r.get('similarity_score', 0):.3f} "
              f"id={it.get('source_id')} {str(it.get('embedding_text',''))[:36]}")
    for a in result.annotation_matches[:3]:
        it = a.get("item", {})
        print(f"   - anno  score={a.get('similarity_score', 0):.3f} "
              f"keyword={it.get('keyword_ko')}")

    draft = result.draft or {}
    print(f"\n[번역 초안] {str(draft.get('translation',''))[:200]}")
    if draft.get("rationale"):
        print(f"   근거: {str(draft.get('rationale',''))[:150]}")

    review = result.translation_review or {}
    print(f"\n[검수]")
    print(f"   조치(recommended_action): {review.get('recommended_action','')}")
    print(f"   위험요약(risk_summary): {str(review.get('risk_summary',''))[:200]}")
    if review.get('review_note'):
        print(f"   검수메모(review_note): {str(review.get('review_note',''))[:200]}")
    if review.get('detected_constraints'):
        print(f"   감지된 제약: {review.get('detected_constraints')}")
    print(f"   수정본(revised): {str(review.get('revised_translation',''))[:200]}")

    insp = result.inspection or {}
    print(f"\n[검수챗봇 inspect]")
    print(f"   심각도(severity): {insp.get('severity','')}  |  조치: {insp.get('recommended_action','')}  |  정책: {insp.get('intervention_policy','')}")
    if insp.get('risk_summary'):
        print(f"   위험요약: {str(insp.get('risk_summary',''))[:200]}")
    spans = insp.get('problematic_spans') or []
    if spans:
        print(f"   문제구간(problematic_spans) {len(spans)}건:")
        for s in spans[:5]:
            print(f"      - {s}")
    sugg = insp.get('suggestions') or []
    if sugg:
        print(f"   수정제안(suggestions) {len(sugg)}건:")
        for s in sugg[:5]:
            print(f"      - {s}")

    print(f"\n[최종 번역] {result.reviewed_translation}")

    section("결과")
    print(f"{OK} 번역 파이프라인 전체 흐름이 실제 LLM 으로 끝까지 정상 작동.")

    block = _build_html_block(locale, cfg, elapsed, result)
    return 0, block


def _esc(v) -> str:
    return _html.escape(str(v if v is not None else ""))


def _build_html_block(locale, cfg, elapsed, result) -> str:
    """한 locale의 결과를 HTML 섹션으로."""
    draft = result.draft or {}
    review = result.translation_review or {}
    insp = result.inspection or {}

    # 검색 결과 행들
    def idiom_rows():
        rows = []
        for r in result.retrievals:
            it = r.get("item", {})
            rows.append(f"<tr><td>{r.get('similarity_score',0):.3f}</td>"
                        f"<td>{_esc(it.get('source_id'))}</td>"
                        f"<td>{_esc(str(it.get('embedding_text',''))[:80])}</td></tr>")
        return "".join(rows) or "<tr><td colspan=3>(없음)</td></tr>"

    def anno_rows():
        rows = []
        for a in result.annotation_matches:
            it = a.get("item", {})
            rows.append(f"<tr><td>{a.get('similarity_score',0):.3f}</td>"
                        f"<td>{_esc(it.get('keyword_ko'))}</td>"
                        f"<td>{_esc(it.get('category'))}</td></tr>")
        return "".join(rows) or "<tr><td colspan=3>(없음)</td></tr>"

    spans = insp.get("problematic_spans") or []
    sugg = insp.get("suggestions") or []
    spans_html = "".join(f"<li>{_esc(s)}</li>" for s in spans) or "<li>(없음)</li>"
    sugg_html = "".join(f"<li>{_esc(s)}</li>" for s in sugg) or "<li>(없음)</li>"

    return f"""
<section>
  <h2>{_esc(locale)} <small>({_esc(cfg.translation_model)}, chunk={_esc(cfg.chunk_strategy)}, 실행 {elapsed:.1f}s)</small></h2>

  <h3>검색 — idiom ({len(result.retrievals)}건)</h3>
  <table><tr><th>score</th><th>source_id</th><th>embedding_text</th></tr>{idiom_rows()}</table>

  <h3>검색 — annotation/kculture ({len(result.annotation_matches)}건)</h3>
  <table><tr><th>score</th><th>keyword</th><th>category</th></tr>{anno_rows()}</table>

  <h3>번역 초안</h3>
  <div class="box">{_esc(draft.get('translation'))}</div>
  <p class="muted">근거: {_esc(draft.get('rationale'))}</p>

  <h3>검수 (review)</h3>
  <p>조치: <b>{_esc(review.get('recommended_action'))}</b> · 위험요약: {_esc(review.get('risk_summary'))}</p>
  <p class="muted">검수메모: {_esc(review.get('review_note'))}</p>
  <div class="box">수정본: {_esc(review.get('revised_translation'))}</div>

  <h3>검수챗봇 (inspect)</h3>
  <p>심각도: <b>{_esc(insp.get('severity'))}</b> · 조치: {_esc(insp.get('recommended_action'))} · 정책: {_esc(insp.get('intervention_policy'))}</p>
  <p>문제구간:</p><ul>{spans_html}</ul>
  <p>수정제안:</p><ul>{sugg_html}</ul>

  <h3>최종 번역</h3>
  <div class="box final">{_esc(result.reviewed_translation)}</div>
</section>
"""


def _render_html(source_text, blocks) -> str:
    style = """
    body{font-family:system-ui,'Malgun Gothic',sans-serif;max-width:900px;margin:24px auto;padding:0 16px;line-height:1.6;color:#222}
    h1{border-bottom:2px solid #333;padding-bottom:8px}
    h2{margin-top:36px;background:#f0f4f8;padding:8px 12px;border-radius:6px}
    h2 small{font-weight:normal;color:#666;font-size:0.7em}
    h3{margin-top:20px;color:#2c5}
    h3{color:#1a6}
    table{border-collapse:collapse;width:100%;margin:8px 0;font-size:0.9em}
    th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}
    th{background:#f7f7f7}
    .box{background:#fafafa;border:1px solid #e0e0e0;border-radius:6px;padding:12px;white-space:pre-wrap}
    .box.final{background:#eef9f0;border-color:#bce3c5;font-weight:500}
    .muted{color:#777;font-size:0.9em}
    .fail{color:#c00;font-weight:bold}
    .src{background:#fff8e1;border:1px solid #ffe082;border-radius:6px;padding:12px;white-space:pre-wrap;max-height:300px;overflow:auto}
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = "".join(blocks)
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>번역 파이프라인 결과</title><style>{style}</style></head>
<body>
<h1>번역 파이프라인 검증 결과</h1>
<p class="muted">생성: {ts} · mock=False (실제 LLM)</p>
<h3>원문</h3>
<div class="src">{_esc(source_text)}</div>
{body}
</body></html>"""


if __name__ == "__main__":
    sys.exit(main())
