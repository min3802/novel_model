from __future__ import annotations

import base64
import html
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
IMAGE_DIR = DATA_DIR / "images"
RELATION_DIR = DATA_DIR / "relations"
CHARACTER_FILE = DATA_DIR / "characters.json"
IMAGE_FILE = DATA_DIR / "images.json"
RELATION_FILE = DATA_DIR / "relations.json"

CHARACTER_LIMIT_PER_WORK = 20
RELATION_CHARACTER_LIMIT = 10
COVER_IMAGE_LIMIT = 5
EXTRA_PROMPT_LIMIT = 500

COUNTRY_LABELS = {
    "JP": "일본",
    "CN": "중국",
    "US": "미국",
    "TH": "태국",
}

COUNTRY_GUIDE = {
    "JP": "Japanese web novel market, clean commercial light-novel cover readability",
    "CN": "Chinese online fiction market, dramatic composition with strong genre signal",
    "US": "US web fiction market, cinematic readable thumbnail and clear protagonist hook",
    "TH": "Thai web novel market, polished romantic/dramatic web fiction cover readability",
}


def setup_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    RELATION_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def compact(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def cut(value: str | None, limit: int) -> str:
    return compact(value)[:limit]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    return OpenAI(api_key=api_key)


def request_json(system_prompt: str, user_prompt: str) -> dict:
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY 또는 openai 패키지가 없어 실제 AI 호출을 건너뜁니다.")

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content or "{}")


def init_state() -> None:
    setup_dirs()
    st.session_state.setdefault("work", {
        "title": "운수 좋은 날",
        "genre": "현대 드라마",
        "synopsis": "가난한 인력거꾼 김첨지가 비 오는 날 뜻밖의 돈을 벌지만, 병든 아내를 둔 집으로 돌아가는 하루를 다룬 비극적 이야기.",
    })
    st.session_state.setdefault("characters", read_json(CHARACTER_FILE, []))
    st.session_state.setdefault("images", read_json(IMAGE_FILE, []))
    st.session_state.setdefault("relations", read_json(RELATION_FILE, []))
    st.session_state.setdefault("last_relation_data", None)
    st.session_state.setdefault("last_cover_prompt", "")


def save_characters() -> None:
    write_json(CHARACTER_FILE, st.session_state["characters"])


def save_images() -> None:
    write_json(IMAGE_FILE, st.session_state["images"])


def save_relations() -> None:
    write_json(RELATION_FILE, st.session_state["relations"])


def character_extract_prompt(work: dict) -> tuple[str, str]:
    system_prompt = """
너는 한국어 웹소설의 시놉시스를 읽고 작품 관리용 캐릭터 설정집을 만드는 분석가다.
반드시 JSON만 반환한다. 원문 근거가 부족한 값은 빈 문자열로 둔다.
"""
    user_prompt = f"""
[작품 정보]
제목: {work["title"]}
장르: {work["genre"]}

[시놉시스]
{work["synopsis"]}

[반환 JSON 형식]
{{
  "characters": [
    {{
      "name": "필수, 30자 이내",
      "age": "선택, 10자 이내",
      "role": "주인공/주요인물/조연/단역 중 하나 권장, 5자 이내",
      "gender": "선택, 5자 이내",
      "relation": "다른 인물과의 관계 요약, 500자 이내",
      "appearance": "외형 정보, 300자 이내",
      "detail": "성격/직업/소속/서사 역할 등 세부 설정, 1000자 이내"
    }}
  ]
}}

[규칙]
- 최대 {CHARACTER_LIMIT_PER_WORK}명까지만 추출한다.
- 이름이 없는 항목은 만들지 않는다.
- 내용은 모두 한국어로 작성한다.
"""
    return system_prompt, user_prompt


def normalize_character(item: dict) -> dict:
    return {
        "id": item.get("id") or uuid4().hex[:12],
        "name": cut(item.get("name"), 30),
        "age": cut(item.get("age"), 10),
        "role": cut(item.get("role"), 5),
        "gender": cut(item.get("gender"), 5),
        "relation": cut(item.get("relation"), 500),
        "appearance": cut(item.get("appearance"), 300),
        "detail": cut(item.get("detail"), 1000),
        "source": item.get("source") or "ai",
        "updated_at": now_text(),
    }


def fallback_characters(work: dict) -> list[dict]:
    text = work.get("synopsis", "")
    names = []
    for token in re.findall(r"[가-힣]{2,5}", text):
        if token not in names and token not in {"가난한", "인력거꾼", "비극적", "이야기", "하루를"}:
            names.append(token)
        if len(names) >= 3:
            break
    if not names:
        names = ["주인공"]

    rows = []
    for index, name in enumerate(names):
        rows.append(normalize_character({
            "name": name,
            "role": "주인공" if index == 0 else "조연",
            "relation": "시놉시스에서 추정된 관계 정보입니다. 실제 설정에 맞게 수정하세요.",
            "appearance": "",
            "detail": "자동 호출 없이 생성된 테스트용 캐릭터 설정입니다.",
            "source": "mock",
        }))
    return rows


def extract_characters(work: dict) -> list[dict]:
    system_prompt, user_prompt = character_extract_prompt(work)
    try:
        payload = request_json(system_prompt, user_prompt)
        items = payload.get("characters") or []
        rows = []
        seen = set()
        for item in items[:CHARACTER_LIMIT_PER_WORK]:
            row = normalize_character(item)
            if not row["name"] or row["name"] in seen:
                continue
            seen.add(row["name"])
            rows.append(row)
        return rows
    except Exception as exc:
        st.warning(f"AI 추출 대신 테스트용 후보를 만들었습니다. ({exc})")
        return fallback_characters(work)


def build_cover_prompt(work: dict, characters: list[dict], target_country: str, extra_prompt: str) -> str:
    character_text = "\n".join(
        [
            (
                f"- {c.get('name')}: role={c.get('role') or '-'}, gender={c.get('gender') or '-'}, "
                f"age={c.get('age') or '-'}, appearance={c.get('appearance') or '-'}, "
                f"detail={c.get('detail') or '-'}, relation={c.get('relation') or '-'}"
            )
            for c in characters[:5]
        ]
    )
    return f"""
Create a vertical commercial web novel cover illustration.

Work title: {work["title"]}
Genre: {work["genre"]}
Target market: {COUNTRY_GUIDE.get(target_country, "global web novel market")}
Synopsis: {work["synopsis"][:1200] or "No synopsis provided."}

Character settings:
{character_text or "- No character settings registered yet. Use synopsis and genre only."}

Additional user request:
{extra_prompt.strip() or "No additional request."}

Requirements:
- Use the registered character settings as the primary source.
- Make one clear focal composition suitable for a cover thumbnail.
- Family-friendly, non-sexual, safe-for-all-ages.
- No generated text, logos, signatures, or watermarks.
- Avoid real public figure resemblance.
""".strip()


def generate_image(prompt: str) -> dict:
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY 또는 openai 패키지가 없어 이미지 생성을 실행할 수 없습니다.")

    response = client.images.generate(
        model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        prompt=prompt,
        size=os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"),
        n=1,
    )
    item = response.data[0]
    b64_json = getattr(item, "b64_json", None)
    image_url = getattr(item, "url", None)

    if b64_json:
        filename = f"cover_{uuid4().hex}.png"
        path = IMAGE_DIR / filename
        path.write_bytes(base64.b64decode(b64_json))
        return {"type": "file", "path": str(path), "created_at": now_text()}

    if image_url:
        return {"type": "url", "url": image_url, "created_at": now_text()}

    raise RuntimeError("이미지 생성 결과에서 이미지 데이터를 찾지 못했습니다.")


def relation_extract_prompt(work: dict, characters: list[dict]) -> tuple[str, str]:
    system_prompt = """
너는 캐릭터 설정집을 읽고 HTML 인물 관계도에 들어갈 요약 데이터를 만드는 분석가다.
관계도는 사용자가 직접 수정하지 않는 결과물이므로, 캐릭터 설정집에 적힌 정보만 근거로 삼는다.
반드시 JSON만 반환한다. 제공된 캐릭터 외 새 인물을 만들지 않는다.
동일 인물의 별칭/호칭으로 보이는 항목은 중복 노드로 만들지 않는다.
"""
    lines = []
    for index, c in enumerate(characters[:RELATION_CHARACTER_LIMIT], start=1):
        lines.append(
            f"[{index}] id={c.get('id')}\n"
            f"  이름: {c.get('name')}\n"
            f"  나이: {c.get('age') or '-'}\n"
            f"  성별: {c.get('gender') or '-'}\n"
            f"  역할: {c.get('role') or '-'}\n"
            f"  관계 원문: {c.get('relation') or '-'}\n"
            f"  외형: {c.get('appearance') or '-'}\n"
            f"  세부 설정: {c.get('detail') or '-'}"
        )
    user_prompt = f"""
[작품명]
{work["title"]}

[캐릭터 설정집]
{chr(10).join(lines)}

[반환 JSON 형식]
{{
  "work_title": "작품명",
  "main_character": "중심 인물 이름",
  "summary": "관계도 상단에 들어갈 2~3문장 요약",
  "characters": [
    {{
      "id": "캐릭터id",
      "name": "캐릭터명",
      "role": "관계도 카드에 표시할 역할",
      "description": "관계도 카드용 한 줄 설명",
      "is_main": true,
      "importance": 1,
      "image_path": ""
    }}
  ],
  "groups": [
    {{
      "id": "group_001",
      "name": "소속/조직/팀명",
      "group_type": "team",
      "members": ["캐릭터id"],
      "description": "그룹 설명",
      "importance": 1
    }}
  ],
  "relations": [
    {{
      "source": "출발 캐릭터id",
      "target": "도착 캐릭터id",
      "relation": "관계 라벨",
      "description": "관계도 하단 목록에 들어갈 관계 설명",
      "direction": "both",
      "style": "partnership",
      "importance": 1
    }}
  ],
  "warnings": ["추정 또는 제외 사유가 있을 때만 작성"]
}}

[규칙]
- characters는 제공된 캐릭터만 사용하고 최대 {RELATION_CHARACTER_LIMIT}명이다.
- characters의 id는 반드시 입력에 제공된 id를 그대로 사용한다.
- relations의 source/target은 characters의 id와 정확히 일치해야 한다.
- direction은 both 또는 one_way 중 하나만 사용한다.
- style은 romance, partnership, hierarchy, rivalry, mentorship, family, organization, neutral 중 하나를 권장한다.
- 관계 라벨은 짧게, 관계 설명은 1~2문장으로 요약한다.
- 관계도 내용은 캐릭터 설정집 기반 자동 요약 결과다. 사용자가 직접 관계도를 수정한다고 가정하지 않는다.
"""
    return system_prompt, user_prompt


def fallback_relation_data(characters: list[dict]) -> dict:
    selected = [c for c in characters[:RELATION_CHARACTER_LIMIT] if c.get("name")]
    relation_characters = [
        {
            "id": c.get("id") or f"char_{index:03d}",
            "name": c.get("name", ""),
            "role": c.get("role", ""),
            "description": (c.get("detail") or c.get("appearance") or c.get("relation") or "")[:180],
            "is_main": index == 1 or "주인공" in str(c.get("role", "")),
            "importance": index,
            "image_path": "",
        }
        for index, c in enumerate(selected, start=1)
    ]
    relations = []
    if len(relation_characters) >= 2:
        main = relation_characters[0]["id"]
        for item in relation_characters[1:]:
            relations.append({
                "source": main,
                "target": item["id"],
                "relation": "관계",
                "description": "캐릭터 설정집 기반 테스트 관계선입니다.",
                "direction": "both",
                "style": "neutral",
                "importance": 3,
            })
    return {
        "work_title": st.session_state["work"].get("title", "작품"),
        "main_character": relation_characters[0]["name"] if relation_characters else "",
        "summary": "캐릭터 설정집의 관계/세부 설정을 기반으로 만든 테스트용 관계도입니다.",
        "characters": relation_characters,
        "groups": [],
        "relations": relations,
        "warnings": ["OPENAI_API_KEY가 없거나 호출에 실패하여 테스트용 관계 데이터를 사용했습니다."],
    }


def normalize_relation_data(work: dict, payload: dict, characters: list[dict]) -> dict:
    valid_by_id = {c["id"]: c for c in characters if c.get("id")}
    valid_names = {c["name"]: c for c in characters if c.get("name")}
    normalized_characters = []
    seen_ids = set()

    for item in payload.get("characters") or []:
        raw_id = compact(item.get("id"))
        name = compact(item.get("name"))
        if raw_id not in valid_by_id and name in valid_names:
            raw_id = valid_names[name]["id"]
        source = valid_by_id.get(raw_id)
        if not source or raw_id in seen_ids:
            continue
        seen_ids.add(raw_id)
        normalized_characters.append({
            "id": raw_id,
            "name": source.get("name", ""),
            "role": cut(item.get("role") or source.get("role") or "인물", 40),
            "description": cut(item.get("description") or source.get("detail") or source.get("relation") or source.get("appearance"), 180),
            "is_main": bool(item.get("is_main", False)),
            "importance": int(item.get("importance") or 3),
            "image_path": compact(item.get("image_path")),
        })

    if not normalized_characters:
        return fallback_relation_data(characters)

    if not any(item["is_main"] for item in normalized_characters):
        normalized_characters[0]["is_main"] = True

    valid_ids = {item["id"] for item in normalized_characters}
    groups = []
    seen_groups = set()
    for index, group in enumerate(payload.get("groups") or [], start=1):
        name = cut(group.get("name"), 60)
        members = [member for member in (group.get("members") or []) if member in valid_ids]
        if not name or not members or name in seen_groups:
            continue
        seen_groups.add(name)
        groups.append({
            "id": compact(group.get("id")) or f"group_{index:03d}",
            "name": name,
            "group_type": cut(group.get("group_type") or "group", 30),
            "members": members,
            "description": cut(group.get("description"), 180),
            "importance": int(group.get("importance") or 3),
        })

    relations = []
    seen_relations = set()
    for relation in payload.get("relations") or []:
        source = compact(relation.get("source"))
        target = compact(relation.get("target"))
        label = cut(relation.get("relation") or "관계", 30)
        key = (source, target, label)
        if source not in valid_ids or target not in valid_ids or source == target or key in seen_relations:
            continue
        seen_relations.add(key)
        direction = compact(relation.get("direction"))
        relations.append({
            "source": source,
            "target": target,
            "relation": label,
            "description": cut(relation.get("description"), 220),
            "direction": "one_way" if direction == "one_way" else "both",
            "style": cut(relation.get("style") or "neutral", 30),
            "importance": int(relation.get("importance") or 3),
        })

    main_character = next((item["name"] for item in normalized_characters if item["is_main"]), normalized_characters[0]["name"])
    return {
        "work_title": compact(payload.get("work_title")) or work.get("title", "작품"),
        "main_character": main_character,
        "summary": cut(payload.get("summary") or f"{main_character}을 중심으로 캐릭터 설정집의 관계 정보를 요약한 인물 관계도입니다.", 350),
        "characters": normalized_characters[:RELATION_CHARACTER_LIMIT],
        "groups": groups,
        "relations": relations,
        "warnings": [cut(item, 180) for item in (payload.get("warnings") or []) if compact(item)],
    }


def extract_relation_data(work: dict, characters: list[dict]) -> dict:
    if not characters:
        raise ValueError("관계도 추출 전에 캐릭터 설정을 먼저 등록하세요.")

    system_prompt, user_prompt = relation_extract_prompt(work, characters)
    try:
        payload = request_json(system_prompt, user_prompt)
    except Exception as exc:
        st.warning(f"AI 관계 추출 대신 테스트용 관계 데이터를 만들었습니다. ({exc})")
        return fallback_relation_data(characters)

    return normalize_relation_data(work, payload, characters)


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


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


def build_relation_html(work: dict, relation_data: dict) -> str:
    title = esc(relation_data.get("work_title") or work.get("title", "작품"))
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

    cards = []
    for item in characters:
        x, y = positions.get(item["id"], (590.0, 380.0))
        class_name = "node main" if item.get("is_main") else "node"
        initial = esc((item.get("name") or "?")[:1])
        image_path = item.get("image_path") or ""
        avatar = f'<img class="avatar-img" src="{esc(image_path)}" alt="">' if image_path else f'<div class="avatar">{initial}</div>'
        cards.append(
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
    raw_json = esc(json.dumps(relation_data, ensure_ascii=False, indent=2))

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title} - 인물 관계도</title>
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
  <div class="header"><div><div class="kicker">HTML RELATION MAP</div><h1>{title}</h1><p class="summary">{summary}</p></div><div class="badge">중심 인물 <strong>{main_character}</strong></div></div>
  <section class="graph-card"><div class="graph-inner"><svg class="lines" viewBox="0 0 1180 760" aria-hidden="true"><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#b99b72" /></marker></defs>{''.join(edge_paths)}</svg>{''.join(cards)}</div></section>
  <div class="content-grid"><section class="panel"><h2>관계 목록</h2>{''.join(relation_items) or '<p class="notice">추출된 관계가 없습니다.</p>'}</section><section class="panel"><h2>그룹/소속</h2>{''.join(group_items) or '<p class="notice">추출된 그룹이 없습니다.</p>'}{warning_items}<p class="notice">관계도 내용은 캐릭터 설정집을 기반으로 자동 요약됩니다. 수정이 필요하면 캐릭터 설정집을 수정한 뒤 다시 생성하세요.</p></section></div>
  <details><summary>원본 JSON 보기</summary><pre>{raw_json}</pre></details>
</div>
</body>
</html>"""


def render_image_result(record: dict) -> None:
    result = record.get("result", {})
    if result.get("type") == "file" and Path(result.get("path", "")).exists():
        st.image(result["path"], use_container_width=True)
    elif result.get("type") == "url":
        st.image(result["url"], use_container_width=True)
    else:
        st.info("이미지 파일이 없습니다.")


def render_header() -> None:
    st.set_page_config(page_title="w.Lighter Visual Test", layout="wide")
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2.2rem; max-width: 1220px; }
        .small-note { color: #777; font-size: 0.9rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("w.Lighter 로컬 기능 테스트")
    st.caption("Django 붙이기 전 캐릭터 설정집, 이미지 생성, HTML 관계도 흐름만 빠르게 확인하는 Streamlit 앱")


def page_work() -> None:
    st.subheader("작품 입력")
    c1, c2 = st.columns([1.1, 0.9])
    with c1:
        st.session_state["work"]["title"] = st.text_input("작품 제목", st.session_state["work"]["title"])
        st.session_state["work"]["genre"] = st.text_input("장르", st.session_state["work"]["genre"])
    with c2:
        st.info("여기 입력값은 `data/*.json`에 저장되는 테스트 데이터입니다.")
    st.session_state["work"]["synopsis"] = st.text_area(
        "시놉시스",
        st.session_state["work"]["synopsis"],
        height=180,
        max_chars=10000,
    )


def page_characters() -> None:
    st.subheader("캐릭터 설정집")
    col_a, col_b, col_c = st.columns([1, 1, 1])
    if col_a.button("시놉시스로 캐릭터 설정 생성", type="primary", use_container_width=True):
        rows = extract_characters(st.session_state["work"])
        st.session_state["characters"] = rows
        save_characters()
        st.success(f"캐릭터 {len(rows)}명을 생성했습니다.")
    if col_b.button("캐릭터 설정 저장", use_container_width=True):
        save_characters()
        st.success("저장했습니다.")
    if col_c.button("캐릭터 전체 초기화", use_container_width=True):
        st.session_state["characters"] = []
        save_characters()
        st.warning("초기화했습니다.")

    edited = st.data_editor(
        st.session_state["characters"],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "id": st.column_config.TextColumn("id", disabled=True),
            "name": st.column_config.TextColumn("이름", max_chars=30, required=True),
            "age": st.column_config.TextColumn("나이", max_chars=10),
            "role": st.column_config.SelectboxColumn("역할", options=["주인공", "주요인물", "조연", "단역", ""]),
            "gender": st.column_config.TextColumn("성별", max_chars=5),
            "relation": st.column_config.TextColumn("관계", max_chars=500),
            "appearance": st.column_config.TextColumn("외형", max_chars=300),
            "detail": st.column_config.TextColumn("세부 설정", max_chars=1000),
            "source": st.column_config.TextColumn("source"),
            "updated_at": st.column_config.TextColumn("수정일", disabled=True),
        },
        hide_index=True,
    )

    normalized = []
    for row in edited[:CHARACTER_LIMIT_PER_WORK]:
        row = normalize_character(row)
        if row["name"]:
            normalized.append(row)
    st.session_state["characters"] = normalized
    st.caption(f"현재 {len(normalized)}명 / 최대 {CHARACTER_LIMIT_PER_WORK}명")


def page_image() -> None:
    st.subheader("표지 이미지 생성")
    left, right = st.columns([0.95, 1.05], gap="large")
    with left:
        target_country = st.selectbox(
            "대상 국가",
            list(COUNTRY_LABELS.keys()),
            format_func=lambda key: COUNTRY_LABELS[key],
        )
        extra_prompt = st.text_area("추가 요청 문구", max_chars=EXTRA_PROMPT_LIMIT, height=110)
        prompt = build_cover_prompt(
            st.session_state["work"],
            st.session_state["characters"],
            target_country,
            extra_prompt,
        )
        st.session_state["last_cover_prompt"] = prompt
        st.caption(f"{len(extra_prompt)} / {EXTRA_PROMPT_LIMIT}자 · 저장 가능 이미지 {len(st.session_state['images'])} / {COVER_IMAGE_LIMIT}")

        with st.expander("생성 프롬프트 확인", expanded=False):
            st.code(prompt)

        if st.button("이미지 생성 실행", type="primary", use_container_width=True):
            if len(st.session_state["images"]) >= COVER_IMAGE_LIMIT:
                st.error(f"작품당 표지 이미지는 최대 {COVER_IMAGE_LIMIT}장까지 저장할 수 있습니다.")
            else:
                try:
                    with st.spinner("이미지 생성 중..."):
                        result = generate_image(prompt)
                    record = {
                        "id": uuid4().hex[:12],
                        "target_country": target_country,
                        "prompt": prompt,
                        "result": result,
                        "created_at": now_text(),
                    }
                    st.session_state["images"].insert(0, record)
                    save_images()
                    st.success("이미지를 생성했습니다.")
                except Exception as exc:
                    st.error(str(exc))

    with right:
        st.markdown("#### 최근 이미지")
        if not st.session_state["images"]:
            st.info("아직 생성된 이미지가 없습니다. 키가 없으면 프롬프트 확인까지만 테스트하세요.")
        else:
            selected = st.selectbox(
                "이미지 기록",
                st.session_state["images"],
                format_func=lambda item: f"{COUNTRY_LABELS.get(item['target_country'], item['target_country'])} · {item['created_at']}",
            )
            render_image_result(selected)


def page_relation() -> None:
    st.subheader("관계도 추출 / HTML 생성")
    left, right = st.columns([0.9, 1.1], gap="large")

    with left:
        st.caption(f"관계도 표시 캐릭터: 최대 {RELATION_CHARACTER_LIMIT}명")
        st.info("관계도 문구는 캐릭터 설정집을 LLM이 요약해서 생성합니다. 내용 수정은 캐릭터 설정집에서 한 뒤 다시 생성하세요.")

        character_options = st.session_state["characters"]
        selected_ids = st.multiselect(
            "관계도 대상 인물",
            options=[item["id"] for item in character_options],
            default=[item["id"] for item in character_options[:RELATION_CHARACTER_LIMIT]],
            format_func=lambda item_id: next((item["name"] for item in character_options if item["id"] == item_id), item_id),
            max_selections=RELATION_CHARACTER_LIMIT,
        )
        selected_characters = [item for item in character_options if item["id"] in selected_ids]
        st.caption(f"선택 {len(selected_characters)} / {RELATION_CHARACTER_LIMIT}")

        if st.button("관계 데이터 추출", type="primary", use_container_width=True):
            try:
                data = extract_relation_data(st.session_state["work"], selected_characters)
                st.session_state["last_relation_data"] = data
                st.success("관계 데이터를 추출했습니다.")
            except Exception as exc:
                st.error(str(exc))

        relation_data = st.session_state.get("last_relation_data")
        if relation_data:
            st.markdown("##### 추출 결과")
            st.json(relation_data, expanded=False)
            st.caption("이 JSON은 확인용입니다. 실제 수정은 캐릭터 설정집 내용을 고친 뒤 다시 추출하는 흐름으로 보는 게 맞습니다.")

            if st.button("HTML 관계도 생성/저장", use_container_width=True):
                relation_html = build_relation_html(st.session_state["work"], relation_data)
                filename = f"relation_{uuid4().hex[:10]}.html"
                path = RELATION_DIR / filename
                path.write_text(relation_html, encoding="utf-8")
                record = {
                    "id": uuid4().hex[:12],
                    "title": f"{st.session_state['work']['title']} 관계도",
                    "path": str(path),
                    "relation_data": relation_data,
                    "created_at": now_text(),
                }
                st.session_state["relations"].insert(0, record)
                save_relations()
                st.success("HTML 관계도를 저장했습니다.")

    with right:
        st.markdown("#### 관계도 미리보기")
        if st.session_state["relations"]:
            selected = st.selectbox(
                "저장된 관계도",
                st.session_state["relations"],
                format_func=lambda item: f"{item['title']} · {item['created_at']}",
            )
            path = Path(selected["path"])
            if path.exists():
                relation_html = path.read_text(encoding="utf-8")
                components.html(relation_html, height=760, scrolling=True)
                st.download_button(
                    "HTML 다운로드",
                    data=relation_html,
                    file_name=path.name,
                    mime="text/html",
                    use_container_width=True,
                )
            else:
                st.warning("저장된 HTML 파일을 찾을 수 없습니다.")
        elif st.session_state.get("last_relation_data"):
            preview_html = build_relation_html(st.session_state["work"], st.session_state["last_relation_data"])
            components.html(preview_html, height=760, scrolling=True)
        else:
            st.info("관계 데이터를 먼저 추출하세요.")


def main() -> None:
    init_state()
    render_header()
    page_work()
    tab_char, tab_img, tab_rel, tab_data = st.tabs(["캐릭터 설정집", "이미지 생성", "관계도", "저장 데이터"])
    with tab_char:
        page_characters()
    with tab_img:
        page_image()
    with tab_rel:
        page_relation()
    with tab_data:
        st.subheader("로컬 저장 데이터")
        st.write(f"저장 위치: `{DATA_DIR}`")
        st.json({
            "work": st.session_state["work"],
            "characters": st.session_state["characters"],
            "images": st.session_state["images"],
            "relations": st.session_state["relations"],
        }, expanded=False)


if __name__ == "__main__":
    main()
