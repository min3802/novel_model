from textwrap import dedent


SYSTEM_PROMPT = dedent(
    """
    너는 캐릭터 설정집을 읽고 HTML 인물 관계도에 들어갈 요약 데이터를 만드는 분석가다.
    관계도는 캐릭터 설정집에 적힌 정보만 근거로 삼는다.
    반드시 JSON만 반환한다.
    제공된 캐릭터 외 새 인물을 만들지 않는다.
    동일 인물의 별칭/호칭으로 보이는 항목은 중복 노드로 만들지 않는다.
    """
).strip()


def build_relation_extract_prompt(*, work_title, characters, limit):
    character_blocks = []
    for index, character in enumerate(characters, start=1):
        character_blocks.append(
            "\n".join(
                [
                    f"[{index}] id=char_{character.id}",
                    f"이름: {character.name}",
                    f"나이: {character.age or '-'}",
                    f"성별: {character.gender or '-'}",
                    f"역할: {character.role or '-'}",
                    f"관계 요약: {character.relation or '-'}",
                    f"외형: {character.appearance or '-'}",
                    f"성격: {character.personality or '-'}",
                    f"설명: {character.description or '-'}",
                ]
            )
        )

    return dedent(
        f"""
        [작품명]
        {work_title or '작품'}

        [캐릭터 설정집]
        {chr(10).join(character_blocks)}

        [반환 JSON 형식]
        {{
          "work_title": "작품명",
          "main_character": "중심 인물 이름",
          "summary": "관계도 상단에 들어갈 2~3문장 요약",
          "characters": [
            {{
              "id": "char_캐릭터DBID",
              "name": "캐릭터명",
              "role": "관계도 카드에 표시할 역할",
              "description": "관계도 카드용 한 줄 설명",
              "is_main": true,
              "importance": 1
            }}
          ],
          "groups": [
            {{
              "id": "group_001",
              "name": "소속/조직/팀명",
              "group_type": "team",
              "members": ["char_캐릭터DBID"],
              "description": "그룹 설명",
              "importance": 1
            }}
          ],
          "relations": [
            {{
              "source": "char_출발캐릭터DBID",
              "target": "char_도착캐릭터DBID",
              "relation": "관계 라벨",
              "description": "관계 설명",
              "direction": "both",
              "style": "partnership",
              "importance": 1
            }}
          ],
          "warnings": ["추정 또는 제외 사유가 있을 때만 작성"]
        }}

        [규칙]
        - characters는 제공된 캐릭터만 사용하고 최대 {limit}명이다.
        - 캐릭터 id는 반드시 입력에 제공된 char_DBID 형식을 유지한다.
        - relations의 source/target은 characters의 id와 정확히 일치해야 한다.
        - direction은 both 또는 one_way 중 하나만 사용한다.
        - style은 romance, partnership, hierarchy, rivalry, mentorship, family, organization, neutral 중 하나를 권장한다.
        - 관계 라벨은 짧게, 관계 설명은 1~2문장으로 요약한다.
        """
    ).strip()
