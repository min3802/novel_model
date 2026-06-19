"""HTML-to-PDF helpers for localization guide downloads."""

from __future__ import annotations

import html
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


_SECTION_ORDER = [
    "market_trend_fit",
    "genre_trope_alignment",
    "title_synopsis_localization",
    "terminology_glossary_risks",
    "content_rating_sensitivity",
    "adaptation_checklist",
    "evidence_used",
]

_GUIDE_PDF_CSS = """
:root {
  color-scheme: light;
  --guide-bg:#FFF9F7;
  --guide-surface:#ffffff;
  --guide-surface-soft:#F6F1EB;
  --guide-main:#6E5BB8;
  --guide-main-strong:#5B46A8;
  --guide-text:#2D2440;
  --guide-muted:#6E638C;
  --guide-line:#B7A9E6;
  --guide-line-soft:#CFC3FB;
  --guide-chip:#E9E1FF;
  --guide-chip-soft:#F3EEFF;
}

@page {
  size: A4;
  margin: 12mm;
}

html,
body {
  margin: 0;
  padding: 0;
  width: 100%;
  background: var(--guide-bg);
  color: var(--guide-text);
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
  font-family: "Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", system-ui, sans-serif;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

img,
svg,
video,
canvas {
  max-width: 100%;
}

a {
  color: var(--guide-main);
  text-decoration: none;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.guide-pdf-document {
  width: 100%;
  min-height: 100vh;
}

.guide-pdf-shell {
  width: min(184mm, 100%);
  margin: 0 auto;
  padding: 0;
}

.guide-report {
  display: grid;
  gap: 12px;
  color: var(--guide-text);
}

.guide-cover,
.guide-section,
.section,
.chart-card,
.quiet-note,
.work-summary,
.guide-html-preview,
.guide-evidence-panel {
  break-inside: avoid;
  page-break-inside: avoid;
}

.guide-cover {
  border: 1px solid var(--guide-line);
  border-radius: 18px;
  padding: 16px 18px;
  background:
    radial-gradient(circle at top left, rgba(110, 91, 184, 0.15), transparent 26%),
    linear-gradient(180deg, #fffdfd 0%, #f7f2ff 100%);
  box-shadow: none;
}

.guide-cover-label {
  color: var(--guide-main);
  font-size: 10.5px;
  font-weight: 900;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.guide-cover-title {
  margin: 6px 0 8px;
  color: var(--guide-text);
  font-size: 24px;
  line-height: 1.2;
  font-weight: 950;
  letter-spacing: -0.03em;
}

.guide-cover-title em {
  font-style: normal;
  color: var(--guide-main);
}

.guide-cover-sub {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.guide-cover-sub span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 4px 9px;
  border-radius: 999px;
  background: var(--guide-chip-soft);
  border: 1px solid var(--guide-line-soft);
  color: var(--guide-muted);
  font-size: 11px;
  font-weight: 800;
}

.guide-legacy-anchors {
  display: none !important;
}

.guide-section,
.section {
  border: 1px solid var(--guide-line-soft);
  border-radius: 16px;
  background: #ffffff;
  padding: 14px 15px;
  box-shadow: none;
}

.guide-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.guide-section-num {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 9px;
  background: var(--guide-chip-soft);
  color: var(--guide-main);
  font-size: 11px;
  font-weight: 950;
  flex: 0 0 auto;
}

.guide-section-title,
.section h2,
.chart-card h3 {
  margin: 0;
  color: var(--guide-text);
  font-weight: 950;
  letter-spacing: -0.02em;
}

.guide-section-title {
  font-size: 18px;
  line-height: 1.3;
}

.section h2 {
  font-size: 22px;
  line-height: 1.25;
  margin-bottom: 10px;
}

.guide-section-help,
.muted,
.guide-html-preview summary,
.guide-evidence-item small {
  color: var(--guide-muted);
}

.guide-list {
  margin: 0;
  padding-left: 1.08rem;
  display: grid;
  gap: 0.45rem;
}

.guide-list li {
  line-height: 1.75;
  font-size: 14px;
}

.guide-html,
.guide-report {
  display: grid;
  gap: 12px;
}

.guide-html {
  font-size: 14px;
  line-height: 1.75;
}

.guide-html :is(h1, h2, h3, h4, h5, h6) {
  margin: 0 0 10px;
  color: var(--guide-text);
  letter-spacing: -0.03em;
}

.guide-html :is(h1) {
  font-size: 28px;
  line-height: 1.18;
}

.guide-html :is(h2) {
  font-size: 22px;
  line-height: 1.22;
}

.guide-html :is(h3) {
  font-size: 18px;
  line-height: 1.28;
}

.guide-html :is(h4) {
  font-size: 16px;
  line-height: 1.3;
}

.guide-html :is(p, li, td, th, small, span, blockquote, code, pre) {
  margin: 0;
  color: var(--guide-text);
  font-size: 14px;
  line-height: 1.75;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.guide-html :is(table) {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid var(--guide-line-soft);
  border-radius: 14px;
  overflow: hidden;
}

.guide-html :is(th, td) {
  border: 1px solid var(--guide-line-soft);
  padding: 8px 10px;
  vertical-align: top;
}

.guide-html :is(blockquote) {
  padding: 12px 14px;
  border-left: 4px solid var(--guide-main);
  background: #fbf9ff;
  border-radius: 12px;
}

.guide-html :is(code) {
  padding: 2px 5px;
  border-radius: 6px;
  background: var(--guide-chip-soft);
}

.guide-html :is(pre) {
  white-space: pre-wrap;
  background: #fbf9ff;
  border: 1px solid var(--guide-line-soft);
  border-radius: 12px;
  padding: 12px;
}

.guide-html :is(ul, ol) {
  margin: 0;
  padding-left: 1.15rem;
}

.guide-html :is(li) {
  margin: 0;
}

.guide-html :is(a) {
  color: var(--guide-main);
}

.guide-html :is(strong, b) {
  color: var(--guide-text);
}

.guide-html :is(img) {
  max-width: 100%;
  height: auto;
}

.guide-html :is(.guide-section-help) {
  margin: 0 0 10px;
  color: var(--guide-muted);
  font-size: 14px;
  line-height: 1.7;
}

.guide-html :is(.quiet-note) {
  border: 1px solid var(--guide-line-soft);
  border-radius: 16px;
  background: #fff;
  padding: 12px 14px;
}

.guide-html :is(.work-summary) {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}

.guide-html :is(.work-summary > div) {
  border: 1px solid var(--guide-line-soft);
  border-radius: 14px;
  background: #fff;
  padding: 11px 12px;
}

.guide-html :is(.work-summary small) {
  display: block;
  color: var(--guide-muted);
  font-size: 11px;
  line-height: 1.35;
  margin-bottom: 3px;
}

.guide-html :is(.work-summary strong) {
  display: block;
  color: var(--guide-text);
  font-size: 16px;
  line-height: 1.35;
}

.guide-html :is(.chips) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.guide-html :is(.chip) {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 4px 9px;
  border-radius: 999px;
  border: 1px solid var(--guide-line-soft);
  background: var(--guide-chip-soft);
  color: var(--guide-main);
  font-size: 11px;
  font-weight: 850;
}

.guide-html :is(.grid) {
  display: grid;
  gap: 12px;
}

.guide-html :is(.chart-card) {
  border: 1px solid var(--guide-line-soft);
  border-radius: 16px;
  background: #fff;
  padding: 14px 15px;
}

.guide-html :is(.chart-card h3) {
  font-size: 16px;
  line-height: 1.28;
  margin-bottom: 10px;
}

.guide-html :is(.chart-row) {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 2fr) auto;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
}

.guide-html :is(.chart-label) {
  font-size: 13px;
  font-weight: 800;
  color: var(--guide-text);
}

.guide-html :is(.chart-track) {
  height: 10px;
  background: var(--guide-surface-soft);
  border: 1px solid var(--guide-line-soft);
  border-radius: 999px;
  overflow: hidden;
}

.guide-html :is(.chart-track > span) {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--guide-chip) 0%, var(--guide-main) 100%);
  border-radius: inherit;
}

.guide-html :is(.chart-value) {
  font-size: 12px;
  color: var(--guide-muted);
  text-align: right;
  white-space: nowrap;
}

.guide-html :is(.market-snapshot) {
  border: 1px solid var(--guide-line-soft);
  border-radius: 16px;
  background: #fff;
  padding: 14px 15px;
}

.guide-html :is(.market-snapshot .chips) {
  margin-top: 10px;
}

.guide-html :is(.guide-doc-meta) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.guide-html :is(.guide-doc-meta span) {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 4px 9px;
  border-radius: 999px;
  background: var(--guide-chip-soft);
  border: 1px solid var(--guide-line-soft);
  color: var(--guide-main);
  font-size: 11px;
  font-weight: 850;
}

.guide-html :is(.guide-legacy-anchors) {
  display: none !important;
}

@media print {
  .guide-pdf-shell {
    width: 100%;
    max-width: none;
  }
}
""".strip()


def _guide_source(record: dict[str, Any]) -> dict[str, Any]:
    guide = record.get("guide")
    if isinstance(guide, dict):
        return guide
    return record


def _guide_title(source: dict[str, Any], guide_id: int) -> str:
    return str(source.get("title") or source.get("guideTitle") or f"현지화 가이드 #{guide_id}")


def _guide_country(source: dict[str, Any]) -> str:
    return str(
        source.get("targetCountryDisplay")
        or source.get("displayCountry")
        or source.get("targetCountry")
        or source.get("country")
        or "미선택"
    )


def _guide_genre(source: dict[str, Any]) -> str:
    return str(source.get("genre") or "미지정")


def _guide_fragment(source: dict[str, Any], guide_id: int) -> str:
    for key in ("guide_html", "htmlReport", "llmHtmlReport"):
        fragment = source.get(key)
        if isinstance(fragment, str) and fragment.strip():
            return fragment.strip()
    return _guide_sections_fragment(source, guide_id)


def _guide_sections_fragment(source: dict[str, Any], guide_id: int) -> str:
    esc = html.escape
    title = esc(_guide_title(source, guide_id))
    country = esc(_guide_country(source))
    genre = esc(_guide_genre(source))
    created_at = esc(str(source.get("createdAt") or source.get("created_at") or ""))
    summary_text = str(source.get("summary_text") or source.get("summaryText") or "").strip()
    recommendation_reasons = list(source.get("recommendation_reasons") or source.get("recommendationReasons") or [])
    limitation_notice = str(source.get("limitation_notice") or source.get("limitationNotice") or "").strip()
    recommended_country = str(
        source.get("recommended_country_display")
        or source.get("recommendedCountryDisplay")
        or source.get("recommended_country")
        or source.get("recommendedCountry")
        or ""
    ).strip()
    section_order = [key for key in _SECTION_ORDER if key in (source.get("sections") or {})]
    sections = source.get("sections") or {}
    extra_sections = [key for key in sections if key not in section_order]
    ordered_sections = section_order + extra_sections

    meta_bits = [
        f"<span>{country}</span>",
        f"<span>{genre}</span>",
    ]
    if recommended_country:
        meta_bits.append(f"<span>추천 국가: {esc(recommended_country)}</span>")
    if created_at:
        meta_bits.append(f"<span>{created_at}</span>")

    summary_block = f"<p class='guide-section-help'>{esc(summary_text)}</p>" if summary_text else ""
    recommendation_block = ""
    next_section_num = 1
    if recommendation_reasons:
        recommendation_block = (
            "<section class='guide-section'>"
            f"<div class='guide-section-header'><span class='guide-section-num'>{next_section_num}</span>"
            "<span class='guide-section-title'>추천 이유</span></div>"
            f"<ul class='guide-list'>{''.join(f'<li>{esc(reason)}</li>' for reason in recommendation_reasons)}</ul>"
            "</section>"
        )
        next_section_num += 1
    limitation_block = ""
    if limitation_notice:
        limitation_block = (
            "<section class='guide-section'>"
            f"<div class='guide-section-header'><span class='guide-section-num'>{next_section_num}</span>"
            "<span class='guide-section-title'>제한 사항</span></div>"
            f"<p class='guide-section-help'>{esc(limitation_notice)}</p>"
            "</section>"
        )
        next_section_num += 1

    section_html: list[str] = []
    for index, key in enumerate(ordered_sections, start=next_section_num):
        section = sections.get(key) or {}
        section_title = esc(str(section.get("title") or key))
        items = section.get("items") or []
        item_html = "".join(f"<li>{esc(str(item))}</li>" for item in items)
        if not item_html:
            body = f"<p class='guide-section-help'>항목이 없습니다.</p>"
        else:
            body = f"<ul class='guide-list'>{item_html}</ul>"
        section_html.append(
            "<section class='guide-section'>"
            f"<div class='guide-section-header'><span class='guide-section-num'>{index}</span>"
            f"<span class='guide-section-title'>{section_title}</span></div>"
            f"{body}"
            "</section>"
        )

    cover = (
        "<div class='guide-cover'>"
        "<div class='guide-cover-label'>번역 전 현지화 기준서 · PDF</div>"
        f"<div class='guide-cover-title'>{title}<br><em>현지화 리포트</em></div>"
        f"<div class='guide-cover-sub'>{''.join(meta_bits)}</div>"
        f"{summary_block}"
        "</div>"
    )

    body_parts = [cover, recommendation_block, limitation_block, *section_html]
    return "<div class='guide-report'>" + "".join(body_parts) + "</div>"


def build_localization_guide_pdf_html(record: dict[str, Any], guide_id: int) -> str:
    source = _guide_source(record)
    title = html.escape(_guide_title(source, guide_id))
    fragment = _guide_fragment(source, guide_id)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light" />
  <title>{title}</title>
  <style>{_GUIDE_PDF_CSS}</style>
</head>
<body>
  <main class="guide-pdf-document">
    <div class="guide-pdf-shell">
      <div class="guide-html">
        {fragment}
      </div>
    </div>
  </main>
</body>
</html>"""


def _find_pdf_browser() -> Path | None:
    candidates: list[Path] = []

    for env_name in ("GUIDE_PDF_BROWSER", "CHROME_PATH", "EDGE_PATH", "CHROMIUM_PATH"):
        raw = os.environ.get(env_name)
        if raw:
            candidates.append(Path(raw))

    for command in ("msedge", "msedge.exe", "chrome", "chrome.exe", "chromium", "chromium.exe", "google-chrome", "google-chrome.exe"):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(Path(resolved))

    windows_candidates = [
        ("PROGRAMFILES(X86)", ("Microsoft", "Edge", "Application", "msedge.exe")),
        ("PROGRAMFILES", ("Google", "Chrome", "Application", "chrome.exe")),
        ("LOCALAPPDATA", ("Microsoft", "Edge", "Application", "msedge.exe")),
        ("LOCALAPPDATA", ("Google", "Chrome", "Application", "chrome.exe")),
    ]
    for env_name, parts in windows_candidates:
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base).joinpath(*parts))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate
    return None


def _render_pdf_with_browser(browser: Path, html_path: Path, pdf_path: Path) -> bytes:
    url = html_path.as_uri()
    base_flags = [
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--allow-file-access-from-files",
        "--no-first-run",
        "--no-default-browser-check",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=2500",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={pdf_path}",
    ]
    attempts = ("--headless=new", "--headless")
    last_error: Exception | None = None

    for headless_flag in attempts:
        if pdf_path.exists():
            pdf_path.unlink()
        cmd = [str(browser), headless_flag, *base_flags, url]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
            if not pdf_path.exists():
                raise RuntimeError("browser did not create a PDF file")
            pdf_bytes = pdf_path.read_bytes()
            if not pdf_bytes.startswith(b"%PDF"):
                raise RuntimeError("rendered output is not a PDF document")
            return pdf_bytes
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    if last_error is None:
        raise RuntimeError("browser PDF render failed")
    raise RuntimeError(f"browser PDF render failed: {last_error}") from last_error


def build_localization_guide_pdf_bytes(record: dict[str, Any], guide_id: int) -> bytes:
    browser = _find_pdf_browser()
    if browser is None:
        raise RuntimeError("Chromium/Edge browser was not found for localization guide PDF rendering")

    html_doc = build_localization_guide_pdf_html(record, guide_id)
    with tempfile.TemporaryDirectory(prefix="guide-pdf-") as temp_dir:
        temp_path = Path(temp_dir)
        html_path = temp_path / "guide.html"
        pdf_path = temp_path / "guide.pdf"
        html_path.write_text(html_doc, encoding="utf-8")
        return _render_pdf_with_browser(browser, html_path, pdf_path)
