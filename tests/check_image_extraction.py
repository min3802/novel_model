"""이미지 기능 추출·생성 end-to-end 검증 스크립트 (표지/관계도 분리 플로우).

사용 예:
    # mock 검증만 (LLM 호출 없음)
    WLIGHTER_MOCK_MODE=true python tests/check_image_extraction.py

    # 실제 추출 end-to-end (OPENAI_API_KEY 필요). 이미지 생성은 비용/모델승인 필요해 기본 제외.
    python tests/check_image_extraction.py            # 추출까지 실제 호출
    python tests/check_image_extraction.py --images   # 이미지 생성까지 실제 호출

결과 HTML: tests/outputs/image_extraction_result.html
"""
from __future__ import annotations

import html
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from app.image import (  # noqa: E402
    CoverExtractor, CoverGenerator, ImageConfig,
    RelationExtractor, RelationGenerator,
)
from app.translation.infra.runtime import is_mock_mode  # noqa: E402

SAMPLE = ROOT / "tests" / "엘리트_1화.txt"
OUT_DIR = ROOT / "tests" / "outputs"
OUT_HTML = OUT_DIR / "image_extraction_result.html"


def esc(x):
    return html.escape(str(x))


def check_cover(source: str, cfg: ImageConfig, do_image: bool):
    problems = []
    t0 = time.perf_counter()
    ex = CoverExtractor(cfg).extract(source)
    t_ext = time.perf_counter() - t0
    if not ex.characters:
        problems.append("표지: characters 비어 있음")
    for i, c in enumerate(ex.characters):
        if not c.arc_summary:
            problems.append(f"표지 character[{i}].arc_summary 비어 있음")
        if not isinstance(c.key_moments, list):
            problems.append(f"표지 character[{i}].key_moments 가 list 아님")

    gen_out = None
    t_gen = 0.0
    if do_image:
        t1 = time.perf_counter()
        gen_out = CoverGenerator(cfg).generate(ex, work_title="엘리트", genre="현대 음악")
        t_gen = time.perf_counter() - t1
        if gen_out.get("type") not in ("mock_image", "base64", "url"):
            problems.append(f"표지 생성 type 이상: {gen_out.get('type')}")
    if (t_ext + t_gen) > 90:
        problems.append(f"표지 응답 90초 초과: {t_ext + t_gen:.1f}s")
    return ex, gen_out, t_ext, t_gen, problems


def check_relation(source: str, cfg: ImageConfig, do_image: bool):
    problems = []
    t0 = time.perf_counter()
    ex = RelationExtractor(cfg).extract(source)
    t_ext = time.perf_counter() - t0
    if not ex.nodes:
        problems.append("관계도: nodes 비어 있음")
    for i, r in enumerate(ex.relations):
        if not isinstance(r.directed, bool):
            problems.append(f"관계도 relation[{i}].directed 가 bool 아님")

    gen_out = None
    t_gen = 0.0
    if do_image:
        t1 = time.perf_counter()
        gen_out = RelationGenerator(cfg).generate(ex, work_title="엘리트")
        t_gen = time.perf_counter() - t1
        if gen_out.get("type") not in ("mock_image", "base64", "url"):
            problems.append(f"관계도 생성 type 이상: {gen_out.get('type')}")
    if (t_ext + t_gen) > 90:
        problems.append(f"관계도 응답 90초 초과: {t_ext + t_gen:.1f}s")
    return ex, gen_out, t_ext, t_gen, problems


def render_html(cover_ex, rel_ex, meta) -> str:
    crows = "".join(
        f"<tr><td>{esc(c.name)}</td><td>{esc(c.gender)}</td><td>{esc(c.age_estimate)}</td>"
        f"<td>{esc(', '.join(c.appearance))}</td><td>{esc(c.personality)}</td><td>{esc(c.role)}</td>"
        f"<td>{esc(c.arc_summary)}</td><td>{esc(' / '.join(c.key_moments))}</td></tr>"
        for c in cover_ex.characters
    )
    nrows = "".join(f"<tr><td>{esc(n.name)}</td><td>{esc(n.role)}</td></tr>" for n in rel_ex.nodes)
    rrows = "".join(
        f"<tr><td>{esc(r.from_)}</td><td>{'→' if r.directed else '↔'}</td><td>{esc(r.to)}</td>"
        f"<td>{esc(r.relation_type)}</td><td>{esc('방향' if r.directed else '양방향')}</td>"
        f"<td>{esc(r.evidence)}</td></tr>"
        for r in rel_ex.relations
    )
    mrows = "".join(f"<li><b>{esc(k)}</b>: {esc(v)}</li>" for k, v in meta.items())
    return f"""<!doctype html><meta charset="utf-8"><title>이미지 추출·생성 검증</title>
<style>
 body{{font-family:system-ui,'Malgun Gothic',sans-serif;margin:24px;color:#1a1a1a}}
 h1{{font-size:20px}} h2{{font-size:16px;margin-top:28px}}
 table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:6px}}
 th,td{{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}}
 th{{background:#f4f4f5}} ul{{font-size:13px}}
</style>
<h1>이미지 기능 추출·생성 검증</h1>
<ul>{mrows}</ul>
<h2>표지 플로우 — 등장인물 ({len(cover_ex.characters)})</h2>
<table><tr><th>이름</th><th>성별</th><th>나이</th><th>외형</th><th>성격</th><th>역할</th><th>행보(arc)</th><th>임팩트(key_moments)</th></tr>{crows}</table>
<h2>관계도 플로우 — 노드 ({len(rel_ex.nodes)})</h2>
<table><tr><th>이름</th><th>역할</th></tr>{nrows}</table>
<h2>관계도 플로우 — 관계 ({len(rel_ex.relations)})</h2>
<table><tr><th>from</th><th></th><th>to</th><th>관계유형</th><th>방향성</th><th>근거</th></tr>{rrows}</table>
"""


def main() -> int:
    do_image = "--images" in sys.argv
    cfg = ImageConfig()
    mock = is_mock_mode()
    if not SAMPLE.exists():
        print(f"[FAIL] 샘플 원문 없음: {SAMPLE}")
        return 1
    source = SAMPLE.read_text(encoding="utf-8")
    print(f"[INFO] mock={mock}, model={cfg.extract_model}, 원문 {len(source)}자, 이미지생성={do_image}")

    cover_ex, cover_gen, ct_e, ct_g, p1 = check_cover(source, cfg, do_image)
    rel_ex, rel_gen, rt_e, rt_g, p2 = check_relation(source, cfg, do_image)
    problems = p1 + p2

    print(f"[표지]  추출 {ct_e:.2f}s, 캐릭터 {len(cover_ex.characters)}명, 생성 {ct_g:.2f}s")
    print(f"[관계도] 추출 {rt_e:.2f}s, 노드 {len(rel_ex.nodes)}, 관계 {len(rel_ex.relations)}, 생성 {rt_g:.2f}s")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "mock_mode": mock, "extract_model": cfg.extract_model,
        "원문 글자수": len(source), "이미지 생성 호출": do_image,
        "표지 추출(s)": f"{ct_e:.2f}", "관계도 추출(s)": f"{rt_e:.2f}",
        "표지 캐릭터": len(cover_ex.characters),
        "관계도 노드/관계": f"{len(rel_ex.nodes)}/{len(rel_ex.relations)}",
    }
    OUT_HTML.write_text(render_html(cover_ex, rel_ex, meta), encoding="utf-8")
    print(f"[INFO] HTML 저장: {OUT_HTML}")

    for c in cover_ex.characters:
        print(f"  표지· {c.name}({c.role}) 외형={c.appearance} 행보={c.arc_summary}")
    for r in rel_ex.relations:
        print(f"  관계· {r.from_} {'→' if r.directed else '↔'} {r.to} [{r.relation_type}]")

    if problems:
        print("\n[FAIL] 검증 문제:")
        for p in problems:
            print(f"   ✗ {p}")
        return 1
    print("\n[PASS] 형식 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
