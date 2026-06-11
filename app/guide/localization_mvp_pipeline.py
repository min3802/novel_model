from __future__ import annotations

import html
from typing import Any

from .context_pack_analysis import build_context_pack_overlap_report
from .cultural_localization import build_cultural_localization
from .regulation_policy_analysis import build_policy_attention_report
from .work_analysis import analyze_work


MARKET_BY_COUNTRY = {
    "US": "english",
    "JP": "japan",
    "CN": "china",
    "TH": "thailand",
}

POLICY_CHECKPOINT_SUMMARIES = {
    "성적 묘사": {
        "checkpoint": "성적 묘사 수위와 연령 등급 표시 확인",
        "reason": "Work Analyzer가 성적 표현 또는 성인 표시 단서를 게시 전 점검 후보로 분리했습니다.",
    },
    "성폭력 소재": {
        "checkpoint": "성폭력·비동의성 소재 표현 방식 확인",
        "reason": "비동의성/성폭력 단서는 단순 성적 묘사보다 높은 수위의 별도 점검 항목입니다.",
    },
    "잔혹 묘사": {
        "checkpoint": "폭력/잔혹 묘사 수위 확인",
        "reason": "살인·폭력·유혈 등 잔혹 묘사 가능성이 있는 단서가 확인됐습니다.",
    },
    "트라우마/정서적 상처": {
        "checkpoint": "트라우마·학대·정서적 상처 묘사 방식 확인",
        "reason": "정서적 상처나 트라우마 소재는 미화·자극적 소비로 보이지 않게 본문 수위를 확인해야 합니다.",
    },
    "미성년자 관련 표현": {
        "checkpoint": "미성년자 관련 표현과 연령 설정 확인",
        "reason": "학생·청소년 등 미성년자 관련 단서가 있어 연령 설정과 표현 수위를 확인합니다.",
    },
    "혐오/차별 가능성": {
        "checkpoint": "혐오/차별 표현 가능성 확인",
        "reason": "보호 속성 또는 집단 비하로 읽힐 수 있는 표현이 없는지 확인합니다.",
    },
    "저작권/표지 사용 권한": {
        "checkpoint": "저작권·표지·상표 사용 권한 확인",
        "reason": "실존 저작물·상표·표지 사용 권한과 플랫폼 업로드 조건을 확인합니다.",
    },
    "군사/국가 시스템": {
        "checkpoint": "군사/국가 시스템 묘사와 민감도 확인",
        "reason": "군 복무·징병·전쟁 등 국가 시스템 소재는 대상 국가 독자가 오해하지 않도록 맥락을 확인합니다.",
    },
    "종교/의례 민감성": {
        "checkpoint": "종교/의례 소재 설명 방식 확인",
        "reason": "종교·의례 요소는 대상 국가의 민감도와 번역 설명 방식을 확인합니다.",
    },
    "연령 등급 표시": {
        "checkpoint": "R15 등 연령 등급 표시 기준 확인",
        "reason": "R15는 성적 묘사 확정이 아니라 폭력·민감 주제 등을 포함한 넓은 연령 기준일 수 있습니다.",
    },
    "성인 등급 표시": {
        "checkpoint": "R18/성인 등급 표시 기준 확인",
        "reason": "성인 등급 단서가 있어 플랫폼별 성인 표시와 노출 제한 기준을 확인합니다.",
    },
}

POLICY_LIMITATIONS_FOR_SUMMARY = [
    "정책 체크포인트는 원문 규정 위반 확정이 아니라 게시 전 확인 후보입니다.",
    "플랫폼 원문 규정 카드는 내부 근거로 보관하고, 사용자 화면에는 소재별 요약을 우선 표시합니다.",
    "시놉시스 기반 민감 요소는 본문 수위와 메타데이터 노출 정도를 별도로 확인해야 합니다.",
]


def _market_context_payload(payload: dict[str, Any], work: dict[str, Any]) -> dict[str, Any] | None:
    market = MARKET_BY_COUNTRY.get(str(work.get("targetCountry") or ""))
    if not market:
        return None
    try:
        report = build_context_pack_overlap_report(
            {
                "title": work.get("title") or payload.get("title") or "입력 작품",
                "target_market": market,
                "genre": work.get("genre") or payload.get("genre") or "",
                "synopsis": work.get("synopsis") or payload.get("synopsis") or "",
                "title_elements": work.get("confirmedElements") or [],
                "comparable_signals": [work.get("genre")] if work.get("genre") else [],
                "declared_signals": payload.get("declaredSignals") or payload.get("declared_signals") or [],
            }
        )
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "guidance": ["시장 관찰 데이터 연결에 실패해 작품/문화/정책 중심으로만 안내합니다."],
        }
    return {
        "available": True,
        "briefing": report["ui_briefing_payload"],
        "evidence": report["evidence"],
    }


def build_policy_checkpoints(payload: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
    """Match platform rules from Work Analyzer cautions, not raw synopsis text."""

    caution_payload = {
        "targetCountry": work.get("targetCountry") or payload.get("targetCountry") or payload.get("country"),
        "declaredSignals": work.get("contentCautions") or [],
        "titleElements": [],
        "comparableSignals": [],
        "title": "",
        "genre": "",
        "synopsis": "",
    }
    report = build_policy_attention_report(caution_payload)
    raw_cards = report["policy_attention_cards"]
    platforms_by_caution: dict[str, list[str]] = {}
    raw_by_caution: dict[str, list[dict[str, Any]]] = {}
    for card in raw_cards:
        matched = [str(item) for item in card.get("matched_elements") or []]
        platform = str(card.get("platform_display_name") or "").strip()
        for caution in work.get("contentCautions") or []:
            if caution in matched:
                if platform:
                    platforms_by_caution.setdefault(caution, []).append(platform)
                raw_by_caution.setdefault(caution, []).append(card)

    summarized_cards: list[dict[str, Any]] = []
    for caution in work.get("contentCautions") or []:
        summary = POLICY_CHECKPOINT_SUMMARIES.get(
            str(caution),
            {
                "checkpoint": f"{caution} 확인",
                "reason": "Work Analyzer가 게시 전 확인 후보로 분리한 소재입니다.",
            },
        )
        platforms = list(dict.fromkeys(platforms_by_caution.get(str(caution), [])))
        summarized_cards.append(
            {
                "card_title": summary["checkpoint"],
                "checkpoint": summary["checkpoint"],
                "status_label": "게시 전 확인",
                "severity": "medium",
                "match_source": "direct_input",
                "matched_elements": [str(caution)],
                "platforms": platforms,
                "display_sentence": summary["reason"],
                "note": "위반 확정이 아니라 게시 전 확인 항목입니다.",
                "rawPolicyCards": raw_by_caution.get(str(caution), []),
            }
        )
    return {
        "policyCheckpoints": summarized_cards,
        "rawPolicyCards": raw_cards,
        "policyLimitations": POLICY_LIMITATIONS_FOR_SUMMARY if summarized_cards else report["policy_limitations"],
        "matchedFrom": "work_profile.contentCautions",
        "contentCautions": work.get("contentCautions") or [],
    }


def compose_localization_report(
    payload: dict[str, Any],
    work: dict[str, Any],
    market: dict[str, Any] | None,
    culture: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    briefing = (market or {}).get("briefing") or {}
    headline_labels = briefing.get("headline_market_labels") or []
    top_tags = [str(item.get("label_ko") or item.get("label") or "") for item in headline_labels[:8] if item]
    overlap_cards = briefing.get("overlap_cards") or []

    metadata_guidance = [
        "제목/소개문은 스토리 수정 지시가 아니라 독자가 처음 이해해야 할 배경·관계·갈등을 정리하는 용도로 사용합니다.",
        "태그는 작품에 실제로 있는 요소만 검토하고, 플랫폼 관찰 데이터에서 자주 보였다는 이유만으로 추가하지 않습니다.",
    ]
    if top_tags:
        metadata_guidance.append(f"대상 시장 관찰 태그 참고 후보: {', '.join(top_tags[:6])}")
    if work.get("confirmedElements"):
        metadata_guidance.append(f"소개문에서 먼저 풀어볼 수 있는 작품 요소: {', '.join(work['confirmedElements'][:6])}")

    executive_summary = [
        "현재 자료로는 작품 소개·메타데이터·문화 설명·게시 전 점검 중심의 MVP 현지화 가이드를 생성합니다.",
        "시장 데이터는 플랫폼 태그 관찰 참고 자료이며 성공 가능성 예측이나 국가 적합도 단정에 쓰지 않습니다.",
    ]
    if culture.get("cultureNotes"):
        executive_summary.append("한국 문화/제도 요소는 유지하되 대상 국가 독자가 이해할 수 있게 짧은 설명을 붙이는 방향을 우선 검토합니다.")

    return {
        "pipelineVersion": "localization_guide_mvp_v1",
        "guideKind": "metadata_culture_policy_localization_guide",
        "reportMode": work.get("mode") or "baseline",
        "workProfile": work,
        "marketContext": {
            "available": bool((market or {}).get("available")),
            "topObservedTags": top_tags,
            "overlapCards": overlap_cards[:6],
            "dataBoundary": "플랫폼 관찰 데이터는 태그/장르 맥락 참고용이며 흥행·독자 취향 예측 근거가 아닙니다.",
        },
        "culturalLocalization": culture,
        "policyCheck": policy,
        "metadataPositioning": {
            "titleIntroTagDirections": metadata_guidance,
            "doNotUseAs": [
                "완성형 소개문 정답",
                "스토리 수정 지시",
                "독자 취향/성공 가능성 예측",
            ],
        },
        "localizationGuideMvp": {
            "executiveSummary": executive_summary,
            "workReading": {
                "title": work.get("title"),
                "mode": work.get("mode"),
                "genre": work.get("genre"),
                "targetCountry": work.get("targetCountryDisplay") or work.get("targetCountry"),
                "confirmedElements": work.get("confirmedElements") or [],
                "baselineSignals": (work.get("confirmedElements") or []) if work.get("mode") == "baseline" else [],
                "supportingInputSignals": work.get("supportingInputSignals") or [],
                "additionalInputSignals": work.get("additionalInputSignals") or [],
                "contentCautions": work.get("contentCautions") or [],
                "assumptions": work.get("assumptions") or [],
            },
            "marketContext": [
                "대상 국가 플랫폼의 공개 태그/순위 관찰 데이터를 작품 요소와 비교합니다.",
                "관찰 태그는 작성 참고 후보이지 작품에 없는 태그를 붙이라는 뜻이 아닙니다.",
            ]
            + ([f"자주 보인 태그 예: {', '.join(top_tags[:6])}"] if top_tags else []),
            "cultureNotes": culture.get("cultureNotes") or [],
            "policyCheckpoints": policy.get("policyCheckpoints") or [],
            "metadataDirections": metadata_guidance,
            "limitations": final_guard_limitations(),
        },
    }


def final_guard_limitations() -> list[str]:
    return [
        "이 가이드는 법적 판단이나 플랫폼 승인 보장이 아니라 게시 전 확인 체크리스트입니다.",
        "스토리 내용을 바꾸라고 지시하지 않고 소개·태그·문화 설명·정책 점검 방향만 제안합니다.",
        "플랫폼 관찰 데이터만으로 특정 국가 성공 가능성이나 독자 선호를 단정하지 않습니다.",
        "시놉시스 기반 민감 요소는 본문 수위 확인 필요 항목으로만 표시합니다.",
    ]


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _li(items: list[Any]) -> str:
    clean = [item for item in items if item]
    return "".join(f"<li>{_esc(item)}</li>" for item in clean) or "<li class='muted'>표시할 항목이 없습니다.</li>"


def _culture_note_items(notes: list[dict[str, Any]]) -> str:
    if not notes:
        return "<li class='muted'>baseline 입력에서는 문화 요소를 확정하지 않았습니다.</li>"
    rows = []
    for note in notes:
        rows.append(
            "<li>"
            f"<strong>{_esc(note.get('element') or '문화 요소')}</strong>"
            f"<p>{_esc(note.get('issue'))}</p>"
            f"<p class='guide'>{_esc(note.get('guide'))}</p>"
            f"<small>confidence: {_esc(note.get('confidence'))} · source: {_esc(note.get('source'))}</small>"
            "</li>"
        )
    return "".join(rows)


def _policy_card_items(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return "<li class='muted'>작품별 정책 체크포인트를 특정하지 않았습니다.</li>"
    rows = []
    for card in cards:
        rows.append(
            "<li>"
            f"<strong>{_esc(card.get('card_title') or '정책 체크')}</strong>"
            f"<p>{_esc(card.get('display_sentence') or card.get('guide_message_ko'))}</p>"
            f"<p class='guide'>{_esc(card.get('note') or '')}</p>"
            f"<small>severity: {_esc(card.get('severity'))} · matched: {_esc(', '.join(card.get('matched_elements') or []))}</small>"
            "</li>"
        )
    return "".join(rows)


def _analysis_cards(work: dict[str, Any]) -> str:
    element_title = "입력에서 읽은 기준 정보" if work.get("mode") == "baseline" else "확인된 작품 요소"
    cards = [
        (element_title, work.get("confirmedElements") or []),
        ("게시 전 점검 후보", work.get("contentCautions") or []),
    ]
    additional = work.get("additionalInputSignals") or []
    if additional:
        cards.append(("입력 키워드/추가 신호", additional))
    assumptions = work.get("assumptions") or []
    if assumptions:
        cards.append(("입력 한계/가정", assumptions))
    return "".join(
        f"<div class=\"card\"><small>{_esc(title)}</small><ul>{_li(items)}</ul></div>" for title, items in cards
    )


def render_localization_guide_html(report: dict[str, Any]) -> str:
    guide = report.get("localizationGuideMvp") or {}
    work = guide.get("workReading") or report.get("workProfile") or {}
    market = report.get("marketContext") or {}
    culture = report.get("culturalLocalization") or {}
    policy = report.get("policyCheck") or {}
    tags = market.get("topObservedTags") or []
    mode = report.get("reportMode") or "baseline"
    title = work.get("title") or "입력 작품"
    country = work.get("targetCountry") or "대상 국가"
    genre = work.get("genre") or "-"
    mode_label = "상세 현지화 가이드" if mode == "detailed" else "기준선 리포트"

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)} - 해외 플랫폼 현지화 가이드</title>
  <style>
    :root {{ color-scheme: light; --ink:#16181d; --muted:#667085; --line:#e5e7eb; --panel:#f8fafc; --brand:#6d28d9; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",Arial,sans-serif; color:var(--ink); background:#fff; }}
    main {{ max-width:1040px; margin:0 auto; padding:40px 22px 64px; }}
    .hero {{ padding:32px; border-radius:28px; background:linear-gradient(135deg,#20124d,#6d28d9); color:white; }}
    .eyebrow {{ text-transform:uppercase; letter-spacing:.08em; font-size:12px; opacity:.78; }}
    h1 {{ margin:10px 0 8px; font-size:36px; line-height:1.18; }}
    h2 {{ margin:0 0 14px; font-size:22px; }}
    section {{ margin-top:22px; padding:24px; border:1px solid var(--line); border-radius:22px; background:#fff; }}
    .summary {{ background:var(--panel); }}
    .badges {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:18px; }}
    .badge {{ padding:7px 11px; border-radius:999px; background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.22); font-size:13px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:14px; }}
    .card {{ padding:16px; border:1px solid var(--line); border-radius:16px; background:var(--panel); }}
    ul {{ margin:0; padding-left:20px; }}
    li {{ margin:8px 0; }}
    p {{ margin:6px 0; line-height:1.62; }}
    small,.muted {{ color:var(--muted); }}
    .guide {{ color:#344054; }}
    .tag {{ display:inline-block; margin:4px 6px 4px 0; padding:7px 10px; border-radius:999px; background:#f4f3ff; color:#4c1d95; font-size:13px; }}
    .warning {{ border-color:#fed7aa; background:#fff7ed; }}
    .footer {{ margin-top:26px; color:var(--muted); font-size:13px; }}
  </style>
</head>
<body>
<main>
  <div class="hero">
    <div class="eyebrow">해외 플랫폼 현지화 가이드</div>
    <h1>{_esc(title)}</h1>
    <p>{_esc(mode_label)} · { _esc(country) } · { _esc(genre) }</p>
    <div class="badges">
      <span class="badge">{'상세 리포트' if mode == 'detailed' else '기준선 리포트'}</span>
      <span class="badge">게시 전 체크 기준: {'시놉시스에서 확인한 소재' if policy.get('matchedFrom') == 'work_profile.contentCautions' else '상세 시놉시스 보강 필요'}</span>
      <span class="badge">플랫폼 참고 데이터: {'사용함' if market.get('available') else '없음'}</span>
    </div>
  </div>

  <section class="summary">
    <h2>이번 결과 요약</h2>
    <ul>{_li(guide.get('executiveSummary') or [])}</ul>
  </section>

  <section>
    <h2>입력 작품 분석</h2>
    <div class="grid">
      {_analysis_cards(work)}
    </div>
  </section>

  <section>
    <h2>시장 태그 맥락</h2>
    <p class="muted">{_esc(market.get('dataBoundary'))}</p>
    <div>{''.join(f'<span class="tag">{_esc(tag)}</span>' for tag in tags) or '<span class="muted">표시할 태그가 없습니다.</span>'}</div>
    <ul>{_li(guide.get('marketContext') or [])}</ul>
  </section>

  <section>
    <h2>문화 현지화 노트</h2>
    <ul>{_culture_note_items(guide.get('cultureNotes') or [])}</ul>
    <h3>현지화 방향</h3>
    <ul>{_li(culture.get('localizationDirections') or [])}</ul>
  </section>

  <section>
    <h2>제목/소개문/태그 방향</h2>
    <ul>{_li(guide.get('metadataDirections') or [])}</ul>
  </section>

  <section class="warning">
    <h2>게시 전 정책 체크포인트</h2>
    <ul>{_policy_card_items(guide.get('policyCheckpoints') or [])}</ul>
    <h3>정책 한계</h3>
    <ul>{_li(policy.get('policyLimitations') or [])}</ul>
  </section>

  <section>
    <h2>과장 금지 / 한계</h2>
    <ul>{_li(guide.get('limitations') or [])}</ul>
  </section>

  <div class="footer">이 결과는 법적 판단이나 플랫폼 승인 보장이 아니라, 게시 전 확인을 돕기 위한 참고 자료입니다.</div>
</main>
</body>
</html>"""


def final_guard(report: dict[str, Any]) -> dict[str, Any]:
    guarded = dict(report)
    guide = dict(guarded.get("localizationGuideMvp") or {})
    limitations = list(dict.fromkeys((guide.get("limitations") or []) + final_guard_limitations()))
    guide["limitations"] = limitations
    guarded["localizationGuideMvp"] = guide
    guarded["finalGuard"] = {
        "overclaimPrevention": [
            "no_success_prediction",
            "no_story_rewrite_instruction",
            "no_policy_violation_determination_from_synopsis_only",
        ],
        "limitations": limitations,
    }
    guarded["htmlReport"] = render_localization_guide_html(guarded)
    return guarded


def build_localization_guide_mvp(payload: dict[str, Any]) -> dict[str, Any]:
    work = analyze_work(payload)
    market = _market_context_payload(payload, work)
    if work.get("mode") == "baseline":
        culture = {
            "cultureNotes": [],
            "localizationDirections": [
                "시놉시스가 충분하지 않아 작품 고유 문화 요소를 확정하지 않습니다.",
                "국가+장르 기준 시장 관찰 맥락만 먼저 확인하고, 상세 문화 설명은 시놉시스 보강 후 진행합니다.",
            ],
            "cultureRiskCheckpoints": [],
            "doNotOverclaim": [
                "작품 고유 소재를 확정하지 않습니다.",
                "정책 위험을 특정하지 않습니다.",
                "국가/장르 관찰 데이터를 성공 가능성 예측으로 쓰지 않습니다.",
            ],
            "evidence": {
                "kcultureCardCount": 0,
                "lexiconMatchCount": 0,
                "constraintCount": 0,
                "countryCode": work.get("targetCountry"),
                "skippedReason": "baseline_input",
            },
        }
        policy = {
            "policyCheckpoints": [],
            "policyLimitations": [
                "시놉시스가 없거나 짧아 작품별 정책 위험을 특정하지 않았습니다.",
                "장르명만으로 성적/폭력/혐오 등 민감 요소를 확정하지 않습니다.",
            ],
            "matchedFrom": "baseline_skipped",
            "contentCautions": [],
        }
    else:
        culture = build_cultural_localization(payload, work)
        policy = build_policy_checkpoints(payload, work)
    return final_guard(compose_localization_report(payload, work, market, culture, policy))


def run_localization_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    """Public entry point for the synopsis-first localization guide pipeline."""

    return build_localization_guide_mvp(payload)
