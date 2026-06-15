import html
import math
from datetime import datetime

from django.core.exceptions import ValidationError

from ..constants import RELATION_CHARACTER_LIMIT, RELATION_MAP_LIMIT_PER_WORK
from ..models import RelationshipMap
from .relation_extractor import extract_relation_data


STYLE_COLORS = {
    "romance": "#b56b82",
    "partnership": "#6c8a62",
    "hierarchy": "#7562a0",
    "rivalry": "#c95b4a",
    "mentorship": "#8a6bbb",
    "family": "#b8844c",
    "organization": "#5d7c99",
    "neutral": "#b99b72",
}


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def node_positions(characters: list[dict]) -> dict[str, tuple[float, float]]:
    if not characters:
        return {}
    main_index = next((i for i, item in enumerate(characters) if item.get("is_main")), 0)
    positions = {characters[main_index]["id"]: (590.0, 380.0)}
    others = [item for i, item in enumerate(characters) if i != main_index]
    for index, item in enumerate(others):
        angle = (2 * math.pi * index / max(len(others), 1)) - math.pi / 2
        positions[item["id"]] = (590 + 400 * math.cos(angle), 380 + 250 * math.sin(angle))
    return positions


def build_relation_html(work, relation_data: dict) -> str:
    work_title = esc(relation_data.get("work_title") or getattr(work, "title", "작품"))
    summary = esc(relation_data.get("summary", ""))
    main_character = esc(relation_data.get("main_character", ""))
    characters = (relation_data.get("characters") or [])[:RELATION_CHARACTER_LIMIT]
    relations = relation_data.get("relations") or []
    groups = relation_data.get("groups") or []
    warnings = relation_data.get("warnings") or []
    positions = node_positions(characters)
    character_by_id = {item["id"]: item for item in characters}

    edge_paths = []
    for relation in relations:
        source = positions.get(relation.get("source"))
        target = positions.get(relation.get("target"))
        if not source or not target:
            continue
        x1, y1 = source
        x2, y2 = target
        color = STYLE_COLORS.get(relation.get("style"), STYLE_COLORS["neutral"])
        marker = ' marker-end="url(#arrow)"' if relation.get("direction") == "one_way" else ""
        mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
        label_width = max(54, min(140, len(str(relation.get("relation", ""))) * 15 + 24))
        edge_paths.append(
            f'<path class="edge-line" d="M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}" stroke="{color}"{marker}></path>'
            f'<rect class="edge-label-bg" x="{mid_x - label_width / 2:.1f}" y="{mid_y - 16:.1f}" width="{label_width}" height="32" rx="15"></rect>'
            f'<text class="edge-label" x="{mid_x:.1f}" y="{mid_y:.1f}">{esc(relation.get("relation"))}</text>'
        )

    node_cards = []
    for item in characters:
        x, y = positions.get(item["id"], (590.0, 380.0))
        class_name = "node main" if item.get("is_main") else "node"
        initial = esc((item.get("name") or "?")[:1])
        image_path = item.get("image_path") or ""
        avatar = (
            f'<img class="avatar-img" src="{esc(image_path)}" alt="">'
            if image_path
            else f'<div class="avatar">{initial}</div>'
        )
        node_cards.append(
            f'<article class="{class_name}" style="left:{x:.1f}px; top:{y:.1f}px;">'
            f'{avatar}<div class="name">{esc(item.get("name"))}</div>'
            f'<div class="role">{esc(item.get("role"))}</div>'
            f'<div class="desc">{esc(item.get("description"))}</div></article>'
        )

    relation_items = []
    for relation in relations:
        source = character_by_id.get(relation.get("source"), {}).get("name", relation.get("source"))
        target = character_by_id.get(relation.get("target"), {}).get("name", relation.get("target"))
        arrow = "→" if relation.get("direction") == "one_way" else "↔"
        relation_items.append(
            f'<div class="item"><div class="item-title">{esc(source)} {arrow} {esc(target)} · {esc(relation.get("relation"))}</div>'
            f'<div class="item-meta">{esc(relation.get("description"))}</div></div>'
        )

    group_items = []
    for group in groups:
        chips = "".join(
            f'<span class="group-chip">{esc(character_by_id.get(member, {}).get("name", member))}</span>'
            for member in group.get("members", [])
        )
        group_items.append(
            f'<div class="item"><div class="item-title">{esc(group.get("name"))} <span class="item-meta">({esc(group.get("group_type"))})</span></div>'
            f'<div>{chips}</div><div class="item-meta">{esc(group.get("description"))}</div></div>'
        )

    warning_items = "".join(f'<div class="warning">{esc(item)}</div>' for item in warnings)
    raw_json = esc(html.unescape(str(relation_data))).replace("'", '"')
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{work_title} - 인물 관계도</title>
<style>
:root {{ --bg:#f7f3ec; --panel:#fffaf2; --ink:#2c241d; --muted:#796b5c; --line:#b99b72; --main:#47321f; --card:#fffdf8; --shadow:0 14px 36px rgba(56,39,20,.13); --radius:22px; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:radial-gradient(circle at top left,#fff8ec 0,var(--bg) 42%,#efe4d4 100%); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR","Malgun Gothic",sans-serif; }}
.page {{ max-width:1280px; margin:0 auto; padding:32px 24px 48px; }}
.header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:18px; }}
.kicker {{ color:var(--muted); font-size:13px; letter-spacing:.08em; font-weight:800; }} h1 {{ margin:6px 0 8px; font-size:34px; line-height:1.15; }} .summary {{ margin:0; color:var(--muted); font-size:15px; line-height:1.55; }}
.badge {{ display:inline-flex; align-items:center; gap:8px; padding:10px 14px; background:rgba(255,250,242,.82); border:1px solid rgba(94,72,45,.12); border-radius:999px; box-shadow:var(--shadow); color:var(--muted); font-size:13px; white-space:nowrap; }}
.graph-card {{ position:relative; width:100%; min-height:760px; background:rgba(255,250,242,.78); border:1px solid rgba(94,72,45,.14); border-radius:32px; overflow:hidden; box-shadow:var(--shadow); }}
.graph-inner {{ position:relative; width:1180px; height:760px; transform-origin:top left; }} .lines {{ position:absolute; inset:0; width:1180px; height:760px; z-index:1; }}
.node {{ position:absolute; width:178px; min-height:112px; transform:translate(-50%,-50%); z-index:2; background:linear-gradient(180deg,var(--card),#fff6e8); border:1px solid rgba(88,61,30,.16); border-radius:var(--radius); padding:14px 14px 12px; box-shadow:0 12px 28px rgba(47,33,17,.12); }}
.node.main {{ width:206px; min-height:128px; background:linear-gradient(180deg,#fff8ec,#ead4b5); border-color:rgba(92,58,25,.25); }}
.avatar {{ width:42px; height:42px; border-radius:50%; display:grid; place-items:center; font-weight:900; background:#e7d3b8; color:var(--main); margin-bottom:9px; }} .node.main .avatar {{ width:48px; height:48px; background:#61452a; color:white; }}
.avatar-img {{ width:48px; height:48px; border-radius:50%; object-fit:cover; display:block; margin-bottom:9px; border:2px solid rgba(97,69,42,.18); }}
.name {{ font-size:18px; font-weight:900; line-height:1.15; }} .role {{ margin-top:5px; font-size:12px; color:var(--muted); font-weight:700; }} .desc {{ margin-top:8px; font-size:12px; color:#5f5144; line-height:1.45; }}
.edge-label-bg {{ fill:rgba(255,250,242,.92); stroke:rgba(151,111,66,.24); }} .edge-label {{ font-size:13px; font-weight:900; fill:#5a3d22; text-anchor:middle; dominant-baseline:central; }} .edge-line {{ stroke-width:2.8; fill:none; stroke-linecap:round; }}
.content-grid {{ display:grid; grid-template-columns:minmax(0,1.2fr) minmax(320px,.8fr); gap:18px; margin-top:18px; }} .panel {{ background:rgba(255,250,242,.82); border:1px solid rgba(94,72,45,.13); border-radius:24px; padding:18px; box-shadow:0 10px 26px rgba(47,33,17,.08); }} .panel h2 {{ margin:0 0 12px; font-size:18px; }}
.item {{ padding:12px 0; border-top:1px solid rgba(94,72,45,.1); }} .item:first-of-type {{ border-top:0; }} .item-title {{ font-weight:900; }} .item-meta {{ margin-top:4px; color:var(--muted); font-size:13px; line-height:1.45; }} .group-chip {{ display:inline-block; margin:4px 6px 0 0; padding:5px 8px; border-radius:999px; background:#efe0cb; font-size:12px; font-weight:800; color:#5e472e; }}
details {{ margin-top:18px; }} summary {{ cursor:pointer; color:var(--muted); font-weight:800; }} pre {{ overflow-x:auto; background:#2d2720; color:#fff8ec; border-radius:18px; padding:16px; font-size:12px; }}
.notice {{ margin-top:14px; color:var(--muted); font-size:12px; }} .warning {{ background:#fff3d9; border:1px solid rgba(164,91,66,.18); color:#7e3f27; padding:10px 12px; border-radius:14px; margin-top:8px; font-size:13px; }}
@media(max-width:900px) {{ .header{{flex-direction:column;}} .content-grid{{grid-template-columns:1fr;}} .graph-card{{overflow-x:auto;}} }}
</style>
</head>
<body>
<div class="page">
  <div class="header"><div><div class="kicker">HTML RELATION MAP</div><h1>{work_title}</h1><p class="summary">{summary}</p></div><div class="badge">중심 인물 <strong>{main_character}</strong></div></div>
  <section class="graph-card"><div class="graph-inner"><svg class="lines" viewBox="0 0 1180 760" aria-hidden="true"><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#b99b72" /></marker></defs>{''.join(edge_paths)}</svg>{''.join(node_cards)}</div></section>
  <div class="content-grid"><section class="panel"><h2>관계 목록</h2>{''.join(relation_items) or '<p class="notice">추출된 관계가 없습니다.</p>'}</section><section class="panel"><h2>그룹/소속</h2>{''.join(group_items) or '<p class="notice">추출된 그룹이 없습니다.</p>'}{warning_items}<p class="notice">관계도 내용은 캐릭터 설정집을 기반으로 자동 요약됩니다. 수정이 필요하면 캐릭터 설정집을 수정한 뒤 다시 생성하세요.</p></section></div>
  <details><summary>원본 JSON 보기</summary><pre>{raw_json}</pre></details>
  <p class="notice">생성일: {created_at}</p>
</div>
</body>
</html>"""


def generate_relationship_map(work, title: str = "", character_ids: list[int] | None = None) -> RelationshipMap:
    if RelationshipMap.objects.filter(work=work).count() >= RELATION_MAP_LIMIT_PER_WORK:
        raise ValidationError(f"작품당 관계도는 최대 {RELATION_MAP_LIMIT_PER_WORK}개까지 저장할 수 있습니다.")
    data = extract_relation_data(work, character_ids=character_ids)
    relation_map = RelationshipMap(
        work=work,
        title=title.strip() or f"{getattr(work, 'title', '작품')} 관계도",
        relation_data=data,
        html_content=build_relation_html(work, data),
    )
    relation_map.full_clean()
    relation_map.save()
    return relation_map
