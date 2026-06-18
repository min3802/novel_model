import html
import math
from datetime import datetime

from django.core.exceptions import ValidationError

from ..models import RelationMap
from .relation_extractor import RELATION_CHARACTER_LIMIT, extract_relation_data


RELATION_MAP_LIMIT_PER_WORK = 10

STYLE_COLORS = {
    'romance': '#b56b82',
    'partnership': '#6c8a62',
    'hierarchy': '#7562a0',
    'rivalry': '#c95b4a',
    'mentorship': '#8a6bbb',
    'family': '#b8844c',
    'organization': '#5d7c99',
    'neutral': '#b99b72',
}

CANVAS_WIDTH = 1440
CANVAS_HEIGHT = 980
CENTER_X = CANVAS_WIDTH / 2
CENTER_Y = CANVAS_HEIGHT / 2
RADIUS_X = 540
RADIUS_Y = 335
NODE_WIDTH = 176
NODE_HEIGHT = 118
MAIN_NODE_WIDTH = 214
MAIN_NODE_HEIGHT = 136
ARROW_SAFE_GAP = 48


def esc(value):
    return html.escape(str(value or ''), quote=True)


def node_edge_gap(item, unit_x, unit_y):
    is_main = bool(item.get('is_main'))
    half_width = (MAIN_NODE_WIDTH if is_main else NODE_WIDTH) / 2
    half_height = (MAIN_NODE_HEIGHT if is_main else NODE_HEIGHT) / 2

    x_gap = half_width / abs(unit_x) if abs(unit_x) > 0.001 else float('inf')
    y_gap = half_height / abs(unit_y) if abs(unit_y) > 0.001 else float('inf')
    return min(x_gap, y_gap) + ARROW_SAFE_GAP


def shorten_line(x1, y1, x2, y2, source_item=None, target_item=None):
    dx = x2 - x1
    dy = y2 - y1
    distance = math.hypot(dx, dy)
    if not distance:
        return x1, y1, x2, y2

    unit_x = dx / distance
    unit_y = dy / distance
    start_gap = node_edge_gap(source_item or {}, unit_x, unit_y)
    end_gap = node_edge_gap(target_item or {}, unit_x, unit_y)

    if distance <= start_gap + end_gap:
        shrink = distance * 0.35
        start_gap = shrink
        end_gap = shrink

    return (
        x1 + unit_x * start_gap,
        y1 + unit_y * start_gap,
        x2 - unit_x * end_gap,
        y2 - unit_y * end_gap,
    )


def node_positions(characters):
    if not characters:
        return {}

    main_index = next((i for i, item in enumerate(characters) if item.get('is_main')), 0)
    positions = {characters[main_index]['id']: (CENTER_X, CENTER_Y)}
    others = [item for i, item in enumerate(characters) if i != main_index]

    for index, item in enumerate(others):
        angle = (2 * math.pi * index / max(len(others), 1)) - math.pi / 2
        radius_jitter_x = 1 + (0.08 if index % 2 == 0 else -0.04)
        radius_jitter_y = 1 + (0.10 if index % 3 == 0 else -0.03)

        positions[item['id']] = (
            CENTER_X + RADIUS_X * radius_jitter_x * math.cos(angle),
            CENTER_Y + RADIUS_Y * radius_jitter_y * math.sin(angle),
        )

    return positions


def build_relation_html(work, relation_data):
    work_title = esc(relation_data.get('work_title') or work.title)
    summary = esc(relation_data.get('summary', ''))
    main_character = esc(relation_data.get('main_character', ''))
    characters = (relation_data.get('characters') or [])[:RELATION_CHARACTER_LIMIT]
    relations = relation_data.get('relations') or []
    groups = relation_data.get('groups') or []
    warnings = relation_data.get('warnings') or []
    positions = node_positions(characters)
    character_by_id = {item['id']: item for item in characters}

    edge_paths = []
    for index, relation in enumerate(relations):
        source_item = character_by_id.get(relation.get('source'), {})
        target_item = character_by_id.get(relation.get('target'), {})
        source = positions.get(relation.get('source'))
        target = positions.get(relation.get('target'))
        if not source or not target:
            continue

        x1, y1 = source
        x2, y2 = target
        line_x1, line_y1, line_x2, line_y2 = shorten_line(
            x1,
            y1,
            x2,
            y2,
            source_item=source_item,
            target_item=target_item,
        )
        color = STYLE_COLORS.get(relation.get('style'), STYLE_COLORS['neutral'])
        if relation.get('direction') == 'one_way':
            marker = ' marker-end="url(#arrow)"'
        else:
            marker = ' marker-start="url(#arrow)" marker-end="url(#arrow)"'

        curve_offset = ((index % 5) - 2) * 30
        dx = line_x2 - line_x1
        dy = line_y2 - line_y1
        length = math.hypot(dx, dy) or 1
        normal_x = -dy / length
        normal_y = dx / length
        label_t = 0.38 + (index % 5) * 0.06
        mid_x = line_x1 + (line_x2 - line_x1) * label_t + normal_x * curve_offset
        mid_y = line_y1 + (line_y2 - line_y1) * label_t + normal_y * curve_offset

        edge_paths.append(
            f'<path class="edge-line" d="M {line_x1:.1f} {line_y1:.1f} Q {mid_x:.1f} {mid_y:.1f} {line_x2:.1f} {line_y2:.1f}" stroke="{color}"{marker}></path>'
        )

    node_cards = []
    for item in characters:
        x, y = positions.get(item['id'], (CENTER_X, CENTER_Y))
        class_name = 'node main' if item.get('is_main') else 'node'
        initial = esc((item.get('name') or '?')[:1])
        node_cards.append(
            f'<article class="{class_name}" style="left:{x:.1f}px; top:{y:.1f}px;">'
            f'<div class="avatar">{initial}</div>'
            f'<div class="name">{esc(item.get("name"))}</div>'
            f'<div class="role">{esc(item.get("role"))}</div>'
            f'<div class="desc">{esc(item.get("description"))}</div></article>'
        )

    relation_items = []
    for relation in relations:
        source = character_by_id.get(relation.get('source'), {}).get('name', relation.get('source'))
        target = character_by_id.get(relation.get('target'), {}).get('name', relation.get('target'))
        arrow = '→' if relation.get('direction') == 'one_way' else '↔'
        relation_items.append(
            f'<div class="item"><div class="item-title">{esc(source)} {arrow} {esc(target)} · {esc(relation.get("relation"))}</div>'
            f'<div class="item-meta">{esc(relation.get("description"))}</div></div>'
        )

    group_items = []
    for group in groups:
        chips = ''.join(
            f'<span class="group-chip">{esc(character_by_id.get(member, {}).get("name", member))}</span>'
            for member in group.get('members', [])
        )
        group_items.append(
            f'<div class="item"><div class="item-title">{esc(group.get("name"))} <span class="item-meta">({esc(group.get("group_type"))})</span></div>'
            f'<div>{chips}</div><div class="item-meta">{esc(group.get("description"))}</div></div>'
        )

    warning_items = ''.join(f'<div class="warning">{esc(item)}</div>' for item in warnings)
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M')

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{work_title} - 인물 관계도</title>
<style>
:root {{ --bg:#f7f3ec; --panel:#fffaf2; --ink:#2c241d; --muted:#796b5c; --line:#b99b72; --main:#47321f; --card:#fffdf8; --shadow:0 14px 36px rgba(56,39,20,.13); --radius:22px; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:radial-gradient(circle at top left,#fff8ec 0,var(--bg) 42%,#efe4d4 100%); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR","Malgun Gothic",sans-serif; }}
.page {{ max-width:1500px; margin:0 auto; padding:32px 24px 48px; }}
.header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:18px; }}
.kicker {{ color:var(--muted); font-size:13px; letter-spacing:.08em; font-weight:800; }} h1 {{ margin:6px 0 8px; font-size:34px; line-height:1.15; }} .summary {{ margin:0; color:var(--muted); font-size:15px; line-height:1.55; }}
.badge {{ display:inline-flex; align-items:center; gap:8px; padding:10px 14px; background:rgba(255,250,242,.82); border:1px solid rgba(94,72,45,.12); border-radius:999px; box-shadow:var(--shadow); color:var(--muted); font-size:13px; white-space:nowrap; }}
.graph-card {{ position:relative; width:100%; min-height:920px; background:rgba(255,250,242,.78); border:1px solid rgba(94,72,45,.14); border-radius:32px; overflow:auto; box-shadow:var(--shadow); }}
.graph-inner {{ position:relative; width:{CANVAS_WIDTH}px; height:{CANVAS_HEIGHT}px; transform-origin:top left; }} .lines {{ position:absolute; inset:0; width:{CANVAS_WIDTH}px; height:{CANVAS_HEIGHT}px; z-index:1; }}
.node {{ position:absolute; width:176px; min-height:118px; transform:translate(-50%,-50%); z-index:2; background:linear-gradient(180deg,var(--card),#fff6e8); border:1px solid rgba(88,61,30,.16); border-radius:var(--radius); padding:14px 14px 12px; box-shadow:0 12px 28px rgba(47,33,17,.12); }}
.node.main {{ width:214px; min-height:136px; background:linear-gradient(180deg,#fff8ec,#ead4b5); border-color:rgba(92,58,25,.25); box-shadow:0 16px 34px rgba(47,33,17,.18); }}
.avatar {{ width:42px; height:42px; border-radius:50%; display:grid; place-items:center; font-weight:900; background:#e7d3b8; color:var(--main); margin-bottom:9px; }} .node.main .avatar {{ width:48px; height:48px; background:#61452a; color:white; }}
.name {{ font-size:18px; font-weight:900; line-height:1.15; word-break:keep-all; }} .role {{ margin-top:5px; font-size:12px; color:var(--muted); font-weight:700; }} .desc {{ margin-top:8px; font-size:12px; color:#5f5144; line-height:1.45; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
.edge-line {{ stroke-width:2; opacity:.64; fill:none; stroke-linecap:round; }}
.content-grid {{ display:grid; grid-template-columns:minmax(0,1.2fr) minmax(320px,.8fr); gap:18px; margin-top:18px; }} .panel {{ background:rgba(255,250,242,.82); border:1px solid rgba(94,72,45,.13); border-radius:24px; padding:18px; box-shadow:0 10px 26px rgba(47,33,17,.08); }} .panel h2 {{ margin:0 0 12px; font-size:18px; }}
.item {{ padding:12px 0; border-top:1px solid rgba(94,72,45,.1); }} .item:first-of-type {{ border-top:0; }} .item-title {{ font-weight:900; }} .item-meta {{ margin-top:4px; color:var(--muted); font-size:13px; line-height:1.45; }} .group-chip {{ display:inline-block; margin:4px 6px 0 0; padding:5px 8px; border-radius:999px; background:#efe0cb; font-size:12px; font-weight:800; color:#5e472e; }}
.notice {{ margin-top:14px; color:var(--muted); font-size:12px; }} .warning {{ background:#fff3d9; border:1px solid rgba(164,91,66,.18); color:#7e3f27; padding:10px 12px; border-radius:14px; margin-top:8px; font-size:13px; }}
@media(max-width:900px) {{ .header{{flex-direction:column;}} .content-grid{{grid-template-columns:1fr;}} }}
</style>
</head>
<body>
<div class="page">
  <div class="header"><div><div class="kicker">HTML RELATION MAP</div><h1>{work_title}</h1><p class="summary">{summary}</p></div><div class="badge">중심 인물 <strong>{main_character}</strong></div></div>
  <section class="graph-card"><div class="graph-inner"><svg class="lines" viewBox="0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}" aria-hidden="true"><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5.2" markerHeight="5.2" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#a88c68" /></marker></defs>{''.join(edge_paths)}</svg>{''.join(node_cards)}</div></section>
  <div class="content-grid"><section class="panel"><h2>관계 목록</h2>{''.join(relation_items) or '<p class="notice">추출된 관계가 없습니다.</p>'}</section><section class="panel"><h2>그룹/소속</h2>{''.join(group_items) or '<p class="notice">추출된 그룹이 없습니다.</p>'}{warning_items}<p class="notice">관계도 내용은 캐릭터 설정집을 기반으로 자동 요약됩니다. 수정이 필요하면 캐릭터 설정집을 수정한 뒤 다시 생성하세요.</p></section></div>
  <p class="notice">생성일: {created_at}</p>
</div>
</body>
</html>"""


def generate_relationship_map(work, *, title='', character_ids=None):
    if RelationMap.objects.filter(work=work).count() >= RELATION_MAP_LIMIT_PER_WORK:
        raise ValidationError(f'작품당 관계도는 최대 {RELATION_MAP_LIMIT_PER_WORK}개까지 저장할 수 있습니다.')

    data = extract_relation_data(work, character_ids=character_ids)
    relation_map = RelationMap.objects.create(
        work=work,
        title=title.strip() or f'{work.title} 관계도',
        relation_data=data,
        html_content=build_relation_html(work, data),
        status='DONE',
    )
    return relation_map
