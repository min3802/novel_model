from textwrap import dedent


SYSTEM_PROMPT = dedent(
    """
    너는 캐릭터 설정집을 읽고 인물 관계도 생성에 필요한 구조화 데이터를 만드는 분석가다.
    관계도 데이터는 캐릭터 설정집에 적힌 정보만 근거로 삼는다.
    반드시 지정된 JSON 형식만 반환한다.
    HTML, 마크다운, 설명 문장은 절대 반환하지 않는다.
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
                    f"이름: {character.char_name}",
                    f"나이: {character.age or '-'}",
                    f"성별: {character.gender or '-'}",
                    f"역할: {character.role or '-'}",
                    f"관계 요약: {character.relationships or '-'}",
                    f"외형: {character.appearance or '-'}",
                    f"세부 설정: {character.detail_setting or '-'}",
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
              "name": "소속/조직/가문명",
              "group_type": "family 또는 organization 또는 faction 또는 team",
              "members": ["char_캐릭터DBID"],
              "description": "그룹 설명",
              "importance": 1
            }}
          ],
          "relations": [
            {{
              "source": "char_출발캐릭터DBID",
              "target": "char_도착캐릭터DBID",
              "relation": "짧은 관계 라벨",
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
        - 제공되지 않은 인물, 조직, 별칭을 새 캐릭터로 만들지 않는다.
        - 내용은 모두 한국어로 작성한다.

        [관계 작성 기준]
        - relation은 그래프 선 위에 표시되므로 짧게 작성한다.
        - relation에는 사건 설명이나 괄호 설명을 넣지 않는다.
        - 자세한 맥락은 description에 작성한다.
        - 쌍방성이 강한 관계는 direction을 both로 작성한다.
        - 한쪽이 행동하고 다른 쪽이 영향을 받는 관계는 direction을 one_way로 작성한다.
        - one_way일 때 source는 행동하는 인물, target은 영향을 받는 인물이다.
        - description에는 누가 누구에게 어떤 행동을 하는지 명확히 작성한다.
        - description에서 A가 B를 협박/이용/후원/조종/감시/추적한다고 설명했다면 source는 반드시 A, target은 B다.
        - source/target 방향은 relation 라벨보다 description의 실제 행동 주체를 우선한다.

        [그룹 작성 기준]
        - groups는 실제 소속, 가문, 조직, 세력 관계가 명확한 경우에만 만든다.
        - 적대자, 추적자, 피해자, 거래 상대, 감시 대상은 group members에 넣지 않는다.
        - 소속이 불명확하면 groups에 넣지 말고 relations로만 표현한다.

        [style 작성 기준]
        - style은 romance, partnership, hierarchy, rivalry, mentorship, family, organization, neutral 중 하나만 사용한다.
        - 관계 성격이 명확하지 않으면 neutral을 사용한다.
        """
    ).strip()