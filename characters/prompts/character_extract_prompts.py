from textwrap import dedent


SYSTEM_PROMPT = dedent(
    """
    너는 한국어 웹소설의 시놉시스를 읽고 작품 관리용 캐릭터 설정집을 만드는 분석가다.
    반드시 JSON만 반환한다.
    원문 근거가 부족한 값은 빈 문자열로 둔다.
    """
).strip()


def build_character_extract_prompt(*, work_title, genre, synopsis, limit):
    return dedent(
        f"""
        [작품 정보]
        제목: {work_title or '작품'}
        장르: {genre or '장르 미입력'}

        [시놉시스]
        {synopsis}

        [반환 JSON 형식]
        {{
          "characters": [
            {{
              "name": "필수, 50자 이내",
              "age": "선택, 20자 이내",
              "role": "주연/주요인물/조연/단역 중 하나 권장, 30자 이내",
              "gender": "선택, 20자 이내",
              "relation": "다른 인물과의 관계 요약",
              "appearance": "외형 정보",
              "personality": "성격, 말투, 행동 방식",
              "description": "직업/소속/서사 역할 등 세부 설정"
            }}
          ]
        }}

        [규칙]
        - 최대 {limit}명까지만 추출한다.
        - 이름이 없는 항목은 만들지 않는다.
        - 작품 속 인물이 아닌 추상 개념은 캐릭터로 만들지 않는다.
        - 내용은 모두 한국어로 작성한다.
        - 과장해서 새 설정을 만들지 말고 시놉시스에서 확인 가능한 내용만 정리한다.
        """
    ).strip()
