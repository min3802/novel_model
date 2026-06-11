from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DOCS = Path("docs")
RESPONSE_PATH = DOCS / "live_policy_localization_response.json"
PAYLOAD_PATH = DOCS / "live_policy_localization_payload.json"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def strip_repeated_lead(title: Any, sentence: Any) -> str:
    text = "" if sentence is None else str(sentence).strip()
    lead = "" if title is None else str(title).strip()
    for sep in (":", "："):
        prefix = f"{lead}{sep}"
        if lead and text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def policy_topics(cards: list[dict[str, Any]]) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for card in cards:
        parts = str(card.get("card_title") or "").replace("/", "·").replace(",", "·").replace("|", "·").split("·")
        parts.extend(card.get("matched_elements") or [])
        for part in parts:
            cleaned = str(part).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                topics.append(cleaned)
            if len(topics) >= 6:
                return topics
    return topics


def high_priority_count(cards: list[dict[str, Any]]) -> int:
    return sum(1 for card in cards if str(card.get("severity") or "").lower() in {"critical", "high"})


def join_ko(items: Any, fallback: str = "입력 없음") -> str:
    seen: set[str] = set()
    output: list[str] = []
    for item in items or []:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return " · ".join(output) if output else fallback


def includes_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def policy_sensitive(item: str) -> bool:
    return includes_any(item, ["R15", "R18", "연령", "잔혹", "폭력", "성적", "미성년", "피의 복수"])


COUNTRY_LABELS = {
    "japan": "일본",
    "jp": "일본",
    "일본": "일본",
    "日本": "일본",
    "us": "미국",
    "usa": "미국",
    "english": "미국",
    "영어권": "미국",
    "미국": "미국",
    "us/global english": "미국",
    "us/global English": "미국",
}


def country_label(response: dict[str, Any]) -> str:
    raw = str(response.get("displayCountry") or response.get("targetCountryDisplay") or response.get("targetCountry") or response.get("country") or "").strip()
    if not raw:
        return "대상 국가"
    return COUNTRY_LABELS.get(raw.lower()) or COUNTRY_LABELS.get(raw) or raw


def report_title(response: dict[str, Any]) -> str:
    return f"{country_label(response)} 현지화 가이드"


def payload_value(payload: dict[str, Any], response: dict[str, Any], *keys: str, fallback: str = "입력 없음") -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    for key in keys:
        value = response.get(key)
        if value:
            return str(value)
    return fallback


def as_particle(value: str) -> str:
    if value.endswith(("권", "본", "국", "어")):
        return f"{value}으로"
    return f"{value}로"


def display_country_name(value: Any) -> str:
    text = str(value or "").strip()
    mapping = {
        "us/global english": "미국",
        "us": "미국",
        "usa": "미국",
        "japan": "일본",
        "jp": "일본",
        "china": "중국",
        "cn": "중국",
        "thailand": "태국",
        "th": "태국",
    }
    return mapping.get(text.lower()) or mapping.get(text) or text


def result_summary(briefing: dict[str, Any], cards: list[dict[str, Any]], label: str) -> list[str]:
    input_summary = briefing.get("input_summary") or {}
    detected = join_ko(input_summary.get("detected_elements"))
    policy_text = " ".join(
        f"{card.get('card_title') or ''} {' '.join(card.get('matched_elements') or [])}" for card in cards
    )
    first = (
        f"이 작품은 {label} 플랫폼 기준으로 연령 등급/R15, 잔혹·성적 묘사, 로맨스 판타지 계열 태그를 먼저 확인해볼 만합니다."
        if includes_any(policy_text + detected, ["R15", "R18", "연령", "성적", "잔혹", "폭력"])
        else f"이 작품은 {label} 플랫폼에 올리기 전, 장르 태그가 어떻게 보일지와 게시 전 확인할 규정을 먼저 살펴보면 좋습니다."
    )
    missing = [
        str(card.get("input_element"))
        for card in briefing.get("missing_cards") or []
        if card.get("input_element") and not policy_sensitive(str(card.get("input_element")))
    ]
    second = (
        f"{join_ko(missing)}는 이번 순위권 태그 데이터에서 직접적인 이름으로는 뚜렷하게 잡히지 않았습니다. 안 맞는다는 뜻이 아니라, {label} 플랫폼 태그에서는 더 넓은 표현으로 묶여 보일 가능성이 큽니다."
        if missing
        else f"이 결과는 작품을 바꾸라는 뜻이 아니라, {label} 플랫폼에 올리기 전에 어떤 태그와 규정을 확인하면 좋을지 정리한 참고 자료입니다."
    )
    return [first, second]


def market_tag_sentence(card: dict[str, Any], label: str) -> str:
    title = str(card.get("card_title") or "")
    if "로맨스 판타지" in title:
        return f"{label} 플랫폼에서는 ‘로맨스 판타지’라는 한 단어보다, ‘연애/로맨스’, ‘이세계 로맨스’, ‘이세계 판타지’처럼 나뉘어 표시되는 경우가 많습니다."
    if "이세계 전생" in title:
        return f"입력 장르가 로맨스 판타지라서 함께 확인한 주변 태그입니다. 작품에 전생·빙의·전이 설정이 없다면 신경 쓰지 않아도 됩니다."
    if policy_sensitive(title):
        return f"{title} 요소는 순위권 태그로 보이는지보다 게시 전 등급·표현 기준을 확인하는 쪽이 더 중요합니다."
    return strip_repeated_lead(card.get("card_title"), card.get("display_sentence"))


def policy_checkpoints(cards: list[dict[str, Any]], label: str) -> list[dict[str, str]]:
    text = " ".join(
        f"{card.get('card_title') or ''} {' '.join(card.get('matched_elements') or [])} {card.get('display_sentence') or ''}"
        for card in cards
    )
    checkpoints: list[dict[str, str]] = []
    if includes_any(text, ["R15", "R18", "연령", "성인", "등급", "제한"]):
        checkpoints.append(
            {
                "title": "R15/R18 표시가 필요한가요?",
                "body": f"제목과 입력 요소에 R15·성적·잔혹 묘사가 걸려 있어, {label} 플랫폼에 올리기 전 연령 등급 표시를 먼저 확인하는 게 좋습니다.",
            }
        )
    if includes_any(text, ["잔혹", "폭력", "피의 복수", "과도한"]):
        checkpoints.append(
            {
                "title": "잔혹 묘사가 플랫폼 기준을 넘지 않나요?",
                "body": f"피의 복수나 잔혹 묘사가 핵심이라면 {label} 플랫폼별 경고 태그, 연령 등급, 표현 강도 기준을 함께 확인하세요.",
            }
        )
    if includes_any(text, ["성적", "미성년", "미성년자"]):
        checkpoints.append(
            {
                "title": "성적 묘사가 있다면 미성년자 관련 표현이 없는지 확인하세요.",
                "body": f"{label} 플랫폼은 성적 표현과 미성년자 보호 기준을 강하게 분리해서 보는 편이라, 등장인물 설정과 표현 방식을 함께 점검하는 게 안전합니다.",
            }
        )
    if includes_any(text, ["카테고리", "키워드", "제목", "소개", "메타"]):
        checkpoints.append(
            {
                "title": "카테고리와 키워드가 작품 내용과 맞나요?",
                "body": f"제목·소개·키워드가 실제 내용과 다르게 보이면 노출보다 규정 확인에서 문제가 될 수 있으니 {label} 게시 전 메타정보를 맞춰주세요.",
            }
        )
    return checkpoints[:4] or [
        {
            "title": "플랫폼 공식 규정을 한 번 더 확인하세요.",
            "body": f"입력 요소와 가까운 규정 후보가 있으므로, 게시 전 {label} 공식 가이드라인을 확인하는 것이 좋습니다.",
        }
    ]


def shell(title: str, body: str, details_meta: str = "", *, label: str = "대상 국가") -> str:
    now = datetime.now(timezone.utc).isoformat()
    meta_details = (
        f'<details class="dev-meta"><summary>자세한 생성 정보</summary><p>Generated at: {esc(now)}</p>{details_meta}</details>'
        if details_meta
        else f'<details class="dev-meta"><summary>자세한 생성 정보</summary><p>Generated at: {esc(now)}</p></details>'
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <style>
    body {{ margin: 0; background: #f6f3ee; color: #241f1a; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif; line-height: 1.58; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 64px; }}
    .meta, .section, .card {{ background: #fff; border: 1px solid #e2d9cd; border-radius: 22px; padding: 22px; box-shadow: 0 10px 30px rgba(57,43,25,.06); }}
    .meta {{ background: #fffaf3; margin-bottom: 18px; }}
    .meta p {{ margin: 6px 0 0; color: #70665d; }}
    h1, h2, h3 {{ margin: 0 0 10px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
    .stack {{ display: grid; gap: 16px; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .chip {{ border: 1px solid #e6ddcf; background: #fff7ed; border-radius: 999px; padding: 6px 10px; }}
    .chart-card {{ border: 1px solid #e6ddcf; border-radius: 18px; background: #fffaf5; padding: 16px; }}
    .chart-card h3 {{ font-size: 16px; margin-bottom: 12px; }}
    .chart-row {{ display: grid; grid-template-columns: minmax(110px, 1fr) 2fr minmax(48px, auto); gap: 10px; align-items: center; margin: 10px 0; }}
    .chart-label {{ font-weight: 800; color: #3f352c; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .chart-track {{ height: 12px; border-radius: 999px; background: #eee4d8; overflow: hidden; }}
    .chart-track span {{ display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #c57a32, #e0ad6b); }}
    .chart-value {{ color: #70665d; font-size: 12px; text-align: right; }}
    .market-snapshot .work-summary {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .muted {{ color: #70665d; }}
    .badge {{ display: inline-block; background: #efe7dc; border-radius: 999px; padding: 4px 9px; margin-right: 6px; font-size: 12px; }}
    a {{ color: #9b5a1f; }}
    details summary {{ cursor: pointer; font-weight: 800; }}
    .guide-report {{ display: grid; gap: 18px; }}
    .guide-cover, .guide-section {{ background: #fff; border: 1px solid #e2d9cd; border-radius: 22px; padding: 22px; box-shadow: 0 10px 30px rgba(57,43,25,.06); }}
    .guide-cover-label {{ color: #9b6a2f; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; }}
    .guide-cover-title {{ font-size: 32px; font-weight: 800; margin-top: 8px; }}
    .guide-cover-title em {{ color: #b1672d; font-style: normal; }}
    .guide-cover-sub, .guide-legacy-anchors {{ display: flex; flex-wrap: wrap; gap: 8px; color: #6f6256; margin-top: 12px; }}
    .guide-cover-sub span {{ background: #f3eadf; padding: 6px 10px; border-radius: 999px; }}
    .guide-legacy-anchors {{ padding: 12px 16px; border-radius: 14px; background: #efe7dc; }}
    .guide-section-title {{ font-size: 18px; font-weight: 800; }}
    .guide-section-help {{ margin: -4px 0 14px; color: #70665d; }}
    .guide-list {{ margin: 12px 0 0; padding-left: 20px; }}
    .guide-list li {{ margin: 8px 0; }}
    .note-list {{ display: grid; margin-top: 12px; border: 1px solid #e2d9cd; border-radius: 18px; overflow: hidden; background: #fff; }}
    .note-row {{ display: grid; grid-template-columns: 170px 1fr; gap: 18px; padding: 16px 18px; border-bottom: 1px solid #eee3d7; }}
    .note-row:last-child {{ border-bottom: 0; }}
    .note-row h3 {{ margin: 0; font-size: 16px; }}
    .note-row p {{ margin: 0; color: #70665d; }}
    .note-row small {{ display: block; margin-top: 5px; color: #8a7a6b; }}
    .work-summary {{ display: grid; grid-template-columns: 1.4fr .8fr; gap: 10px; margin: 14px 0; }}
    .work-summary div {{ display: grid; gap: 4px; border: 1px solid #e6ddcf; border-radius: 16px; background: #fffaf5; padding: 14px 16px; }}
    .work-summary small {{ color: #8a7a6b; font-weight: 800; }}
    .work-summary strong {{ color: #241f1a; }}
    .work-footnote {{ margin: 12px 0 0; color: #70665d; }}
    .quiet-note {{ margin-top: 14px; padding: 16px; border-radius: 16px; background: #f8f4ef; border: 1px dashed #d9cbb9; }}
    .quiet-note p {{ margin: 8px 0 4px; color: #70665d; }}
    .quiet-note small {{ color: #70665d; }}
    .policy-summary {{ display: grid; gap: 10px; margin: 14px 0; padding: 16px; border: 1px solid #e6ddcf; border-radius: 16px; background: #fffaf5; }}
    .policy-summary span {{ display: block; color: #9b5a1f; font-weight: 800; }}
    .policy-summary p {{ margin: 4px 0 0; color: #70665d; }}
    .policy-details {{ margin-top: 14px; padding: 16px; border: 1px solid #e2d9cd; border-radius: 16px; background: #fff; }}
    .policy-checkpoints {{ display: grid; gap: 12px; margin-top: 14px; }}
    .policy-checkpoint {{ display: grid; grid-template-columns: 34px 1fr; gap: 12px; padding: 16px; border: 1px solid #e6ddcf; border-radius: 16px; background: #fffaf5; }}
    .policy-checkpoint > span {{ display: grid; place-items: center; width: 34px; height: 34px; border-radius: 999px; background: #fff1df; color: #9b5a1f; font-weight: 900; }}
    .policy-checkpoint p {{ margin: 6px 0 0; color: #70665d; }}
    .summary-box {{ background: #fffaf3; }}
    .summary-box p {{ color: #3f352c; font-weight: 750; }}
    .dev-meta {{ margin-top: 18px; padding: 16px; border: 1px dashed #d9cbb9; border-radius: 16px; color: #70665d; }}
    .policy-detail-list {{ display: grid; gap: 10px; margin-top: 12px; }}
    .policy-detail-item {{ border: 1px solid #eee3d7; border-radius: 14px; padding: 14px; background: #fffdfb; }}
    .policy-detail-item p {{ margin: 6px 0 0; color: #70665d; }}
    .policy-detail-item small {{ color: #8a7a6b; }}
    @media(max-width: 720px) {{ .note-row, .work-summary {{ grid-template-columns: 1fr; gap: 6px; }} }}
  </style>
</head>
<body>
  <main>
    <section class="meta">
      <h1>{esc(title)}</h1>
      <p>입력한 작품 정보를 {esc(label)} 플랫폼 관찰 데이터와 게시 전 규정 데이터에 대조해, 참고할 태그 흐름과 체크포인트를 정리했어요.</p>
    </section>
    {body}
    {meta_details}
  </main>
</body>
</html>
"""


def policy_cards_html(cards: list[dict[str, Any]], limitations: list[str], label: str) -> str:
    parts = [
        '<section class="section"><h2>게시 전 체크포인트</h2>'
        '<p class="guide-section-help">규정 ID를 먼저 읽기보다, 작가가 게시 전에 바로 확인할 항목부터 정리했어요.</p>'
    ]
    if not cards:
        parts.append(
            f'<p>현재 입력 문구와 직접 겹쳐 자동 표시된 {esc(label)} 규정 후보는 없습니다. '
            "다만 이 말은 규정 데이터가 없다는 뜻이 아니라, 이번 입력에서 특정 위험 키워드가 직접 매칭되지 않았다는 뜻입니다.</p>"
        )
    else:
        parts.append('<div class="policy-checkpoints">')
        for index, item in enumerate(policy_checkpoints(cards, label), start=1):
            parts.append(
                f'<article class="policy-checkpoint"><span>{index}</span><div><strong>{esc(item["title"])}</strong><p>{esc(item["body"])}</p></div></article>'
            )
        parts.append("</div>")
        parts.append(f'<details class="policy-details"><summary>자세한 규정 후보 {len(cards)}건 보기</summary><div class="policy-detail-list">')
        for card in cards:
            refs = card.get("source_refs") or []
            refs_html = "".join(
                f'<li><a href="{esc(ref.get("url"))}" target="_blank" rel="noreferrer">{esc(ref.get("label") or ref.get("url"))}</a></li>'
                for ref in refs
                if ref.get("url")
            )
            parts.append(
                f"""
            <article class="policy-detail-item">
              <h3>{esc(card.get("card_title"))}</h3>
              <small>{esc(card.get("platform_display_name"))}</small>
              <p><b>규칙 ID</b>: {esc(", ".join(card.get("matched_rule_ids") or []))}</p>
              <p><b>확인 요소</b>: {esc(", ".join(card.get("matched_elements") or []))}</p>
              <p>{esc(card.get("display_sentence") or card.get("guide_message_ko"))}</p>
              {("<ul>" + refs_html + "</ul>") if refs_html else ""}
            </article>
            """
            )
        parts.append("</div></details>")
    if limitations:
        parts.append('<div class="quiet-note"><strong>읽기 전에</strong><ul>' + "".join(f"<li>{esc(item)}</li>" for item in limitations) + "</ul></div>")
    parts.append("</section>")
    return "\n".join(parts)


def data_usage_html(response: dict[str, Any], payload: dict[str, Any], label: str) -> str:
    briefing = response.get("contextPackBriefing") or {}
    evidence = response.get("contextPackEvidence") or {}
    input_summary = briefing.get("input_summary") or {}
    cards = response.get("policyAttentionCards") or []
    recs = response.get("recommendedCountries") or []
    platforms = evidence.get("platforms") or []
    signal_types = evidence.get("signal_types") or []
    synopsis = payload_value(payload, response, "synopsis", fallback="")
    synopsis_note = f"{len(synopsis)}자 입력" if synopsis else "입력 없음"
    used_title = input_summary.get("work_title") or payload_value(payload, response, "title", "workTitle")
    used_genre = input_summary.get("genre") or payload_value(payload, response, "genre")
    requested_country = payload_value(payload, response, "targetCountry", "target_country", "country")
    selected_country = response.get("displayCountry") or response.get("targetCountryDisplay") or label

    rec_items = []
    for rec in recs[:3]:
        reasons = " / ".join(str(item) for item in rec.get("reasons") or [])
        rec_items.append(f"{display_country_name(rec.get('displayCountry') or rec.get('country'))} 매칭값 {rec.get('score')}: {reasons}")

    return f"""
<section class="section">
  <h2>입력과 데이터 사용 흐름</h2>
  <p class="guide-section-help">아래는 사용자가 넣은 값이 리포트에서 어떻게 쓰였는지 사용자 관점으로 풀어 쓴 설명입니다.</p>
  <div class="note-list">
    <div class="note-row"><h3>사용자 입력</h3><p>제목: {esc(used_title)}<br>장르: {esc(used_genre)}<br>요청 국가: {esc(requested_country)}<br>시놉시스: {esc(synopsis_note)}</p></div>
    <div class="note-row"><h3>국가 해석</h3><p>요청 국가는 {esc(label)} 플랫폼 관찰 데이터에 연결했습니다.</p></div>
    <div class="note-row"><h3>트렌드 근거</h3><p>{esc(label)} 관찰 데이터에서 플랫폼 {esc(len(platforms))}곳, 순위권 작품 {esc(evidence.get('context_record_count') or '확인 중')}편을 참고했습니다.<br>참고 순위: {esc(join_ko(signal_types, '응답 evidence 기준'))}</p></div>
    <div class="note-row"><h3>정책 근거</h3><p>게시 전 체크포인트는 {esc(label)} 플랫폼 규정 데이터에서 입력 문구와 직접 겹치는 항목을 골라 표시했습니다. 이번 직접 매칭 규정 후보: {esc(len(cards))}건</p></div>
  </div>
  {('<div class="quiet-note"><strong>추천/선택 근거</strong><ul>' + ''.join(f'<li>{esc(item)}</li>' for item in rec_items) + '</ul></div>') if rec_items else ''}
</section>
"""


def final_context_html(response: dict[str, Any], payload: dict[str, Any]) -> str:
    briefing = response.get("contextPackBriefing") or {}
    input_summary = briefing.get("input_summary") or {}
    headline = briefing.get("headline_market_labels") or []
    overlap = briefing.get("overlap_cards") or []
    missing = briefing.get("missing_cards") or []
    cards = response.get("policyAttentionCards") or []
    label = country_label(response)
    work_title = input_summary.get("work_title") or payload_value(payload, response, "title", "workTitle")
    work_genre = input_summary.get("genre") or payload_value(payload, response, "genre")
    title_axis = input_summary.get("title_elements") or input_summary.get("detected_elements")
    comparable = input_summary.get("comparable_elements")
    missing_tag_items = [
        str(card.get("input_element"))
        for card in missing
        if card.get("input_element") and not policy_sensitive(str(card.get("input_element")))
    ]
    policy_check_items = [
        str(card.get("input_element"))
        for card in missing
        if card.get("input_element") and policy_sensitive(str(card.get("input_element")))
    ]

    parts: list[str] = []
    parts.append(
        '<section class="section summary-box"><h2>이번 결과 요약</h2>'
        + "".join(f"<p>{esc(sentence)}</p>" for sentence in result_summary(briefing, cards, label))
        + "</section>"
    )
    parts.append(data_usage_html(response, payload, label))
    parts.append(
        '<section class="section"><h2>입력 작품을 이렇게 읽었어요</h2>'
        '<div class="work-summary">'
        f'<div><small>작품 제목</small><strong>{esc(work_title)}</strong></div>'
        f'<div><small>장르 기준</small><strong>{esc(work_genre)}</strong></div>'
        '</div><div class="note-list">'
        f'<div class="note-row"><h3>제목에서 먼저 보인 축</h3><p>{esc(join_ko(title_axis))}</p></div>'
        f'<div class="note-row"><h3>함께 비교한 요소</h3><p>{esc(join_ko(comparable))}</p></div>'
        f'</div><p class="work-footnote">이 결과는 작품을 바꾸라는 뜻이 아니라, {label} 플랫폼에 올리기 전에 어떤 태그와 규정을 확인하면 좋을지 정리한 참고 자료입니다.</p></section>'
    )
    parts.append(
        f'<section class="section"><h2>{label} 플랫폼에서는 어떤 이름으로 보일 수 있을까요?</h2>'
        f'<p class="guide-section-help">내 작품에서 확인한 요소가 {label} 플랫폼에서는 어떤 태그 이름으로 보일 수 있는지 정리했어요.</p>'
        '<div class="note-list">'
    )
    for card in overlap[:10]:
        parts.append(
            f'<div class="note-row"><h3>{esc(card.get("card_title"))}</h3><div><p>{esc(market_tag_sentence(card, label))}</p></div></div>'
        )
    parts.append("</div>")
    if missing_tag_items:
        parts.append(
            '<div class="quiet-note"><strong>태그 데이터에서는 뚜렷하게 보이지 않은 요소</strong>'
            f'<p>{esc(" · ".join(missing_tag_items[:12]))}</p>'
            '<small>보이지 않는다는 것은 부적합하다는 뜻이 아니라, 살펴본 순위권 태그 안에서 직접 이름으로 확인되지 않았다는 뜻입니다.</small></div>'
        )
    if policy_check_items:
        parts.append(
            '<div class="quiet-note"><strong>규정 확인에서는 따로 봐야 하는 요소</strong>'
            f'<p>{esc(" · ".join(policy_check_items[:12]))}</p>'
            '<small>이 요소들은 인기 태그로 보이는지보다 게시 전 등급·표현 기준을 확인하는 쪽이 더 중요합니다.</small></div>'
        )
    parts.append("</section>")
    parts.append(
        f'<section class="section"><h2>{label} 순위권 작품에서 자주 보인 키워드</h2>'
        f'<p class="guide-section-help">아래 키워드는 내 작품과 모두 직접 연결된다는 뜻이 아니라, 이번에 살펴본 {label} 순위권 작품들에서 자주 보인 태그입니다.</p>'
        '<div class="chips">'
        + "".join(f'<span class="chip">{esc(item.get("label_ko"))}</span>' for item in headline[:12])
        + "</div></section>"
    )
    return "\n".join(parts)


def llm_context_html(response: dict[str, Any], payload: dict[str, Any]) -> str:
    llm_html = response.get("llmHtmlReport")
    if not llm_html:
        return final_context_html(response, payload)
    return str(llm_html)


def main() -> None:
    response = json.loads(RESPONSE_PATH.read_text(encoding="utf-8"))
    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8")) if PAYLOAD_PATH.exists() else {}
    briefing = response.get("contextPackBriefing") or {}
    cards = response.get("policyAttentionCards") or []
    limitations = response.get("policyLimitations") or []
    legacy_html = response.get("htmlReport") or ""
    label = country_label(response)
    title = report_title(response)

    DOCS.mkdir(exist_ok=True)
    legacy_meta = '<p class="muted">Source: live /api/guide response htmlReport field.</p>'
    (DOCS / "live_policy_intermediate_html_report.html").write_text(
        shell("중간 HTML 원문 확인", legacy_html or '<section class="section"><p>No htmlReport was returned.</p></section>', legacy_meta, label=label),
        encoding="utf-8",
    )

    policy_body = policy_cards_html(cards, limitations, label)
    policy_meta = f'<p class="muted">Policy cards: {len(cards)} / Source: raw platform rules + live /api/guide payload.</p>'
    (DOCS / "live_policy_intermediate_policy_cards.html").write_text(
        shell("규정 후보 중간 확인", policy_body, policy_meta, label=label),
        encoding="utf-8",
    )

    final_meta = (
        f'<p class="muted">Display title: {esc(title)} · Country: {esc(label)} · Genre: {esc(response.get("genre"))}</p>'
        f'<p class="muted">Context briefing: {bool(briefing)} · Policy cards: {len(cards)} · Evidence: {bool(response.get("contextPackEvidence"))}</p>'
    )
    final_body = llm_context_html(response, payload) + policy_body
    if not response.get("llmHtmlReport"):
        final_body += '<details class="section"><summary>기존 API htmlReport 원문 보기</summary>' + legacy_html + "</details>"
    (DOCS / "live_policy_final_localization_report.html").write_text(
        shell(title, final_body, final_meta, label=label),
        encoding="utf-8",
    )

    summary_path = DOCS / "live_policy_localization_smoke_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    summary.update(
        {
            "htmlExportsRegeneratedAt": datetime.now(timezone.utc).isoformat(),
            "htmlFiles": [
                "docs/live_policy_intermediate_html_report.html",
                "docs/live_policy_intermediate_policy_cards.html",
                "docs/live_policy_final_localization_report.html",
            ],
        }
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"policyCards": len(cards), "htmlFiles": summary["htmlFiles"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
