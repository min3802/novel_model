import unittest

from app.translation.text_processing.terminology import (
    TERMINOLOGY_POLICY_REVIEW,
    extract_noun_terminology_candidates,
    merge_terminology,
    render_terminology_context,
)


def ko(value: str) -> str:
    try:
        return value.encode("ascii").decode("unicode_escape")
    except UnicodeEncodeError:
        return value


class TerminologyTest(unittest.TestCase):
    def test_candidate_extraction_focuses_on_nouns_not_adjectives(self):
        text = ko('김철수는 빨갛고 붉은 부적을 사랑 약국에서 발견했다.')
        rows = extract_noun_terminology_candidates(text)
        sources = [row["source"] for row in rows]

        self.assertIn(ko('사랑 약국'), sources)
        self.assertNotIn(ko('빨갛고'), sources)
        self.assertNotIn(ko('붉은'), sources)
        self.assertNotIn(ko('번역되어'), sources)
        self.assertNotIn(ko('이름'), sources)

    def test_merge_keeps_existing_confirmed_rows_and_adds_new_candidates(self):
        existing = [
            {
                "source": ko('김철수'),
                "target": "Kim Cheolsu",
                "policy": "locked",
                "status": "confirmed",
            }
        ]
        merged = merge_terminology(existing, [{"source": ko('사랑 약국'), "policy": "locked", "status": "suggested"}])
        context = render_terminology_context(merged, "ko_en_us", source_text=ko('김철수는 사랑 약국에 갔다.'))

        self.assertTrue(any(row["source"] == ko('사랑 약국') for row in merged))
        self.assertIn("Kim Cheolsu", context)
        self.assertIn("choose one translation/transliteration", context)

    def test_common_nouns_time_and_derived_words_are_not_person_names(self):
        text = (
            '노트북과 오른팔, 성공적 성과와 오래전 기억, 안경과 전화, 허공과 배트, 맥주컵이 보였다. '
            '유니폼과 스마트폰, 비타민제, 스포츠 음료도 있었다.'
        )
        rows = extract_noun_terminology_candidates(text)
        banned = {'노트북', '오른팔', '성공적', '오래전', '안경', '전화', '허공', '배트', '맥주컵'}

        for row in rows:
            self.assertFalse(row["source"] in banned and row["type"] in {"person_name", "person_name_alias"})
            self.assertFalse(row["source"] in banned and row["policy"] == "locked")

    def test_people_names_are_kept_and_suggested_candidates_are_review_policy(self):
        text = (
            '강현우는 마운드에 올랐다. 현우는 이를 악물었다. [연주:] 오늘 경기 멋있었어. '
            '한연주는 잠시 숨을 골랐다. 민재는 소리쳤다. 포수 주형은 사인을 냈다. '
            '타자 최태성이 들어섰고, 태성이 형은 덕아웃에서 웃었다. 연주는 다시 현우를 바라봤다.'
        )
        rows = extract_noun_terminology_candidates(text)
        by_source = {}
        for row in rows:
            by_source.setdefault(row["source"], []).append(row)

        expected = {
            '민재': {"person_name_alias", "person_name"},
            '강현우': {"person_name"},
            '현우': {"person_name_alias", "person_name"},
            '한연주': {"person_name"},
            '연주': {"person_name_alias", "person_name"},
            '최태성': {"person_name"},
            '태성': {"person_name_alias", "person_name"},
            '태성이 형': {"person_name_alias"},
            '주형': {"person_name_alias", "person_name"},
        }

        for source, allowed_types in expected.items():
            self.assertIn(source, by_source, msg=source)
            self.assertTrue(any(row["type"] in allowed_types for row in by_source[source]), msg=source)
            self.assertTrue(all(row["policy"] == TERMINOLOGY_POLICY_REVIEW for row in by_source[source]))
            self.assertTrue(all(row["status"] == "suggested" for row in by_source[source]))

    def test_team_company_place_and_league_are_not_person_names(self):
        text = (
            '제우스 킹즈와 네오 타이탄즈, 서울 네오 타이탄즈가 맞붙었다. '
            '넥스트랩의 대표가 잠실야구장 근처 청담동으로 향했다. KBO 관계자도 있었다.'
        )
        rows = extract_noun_terminology_candidates(text)
        types = {(row["source"], row["type"]) for row in rows}
        person_like = {(row["source"], row["type"]) for row in rows if row["type"] in {"person_name", "person_name_alias"}}

        self.assertIn(('제우스 킹즈', "team_name"), types)
        self.assertIn(('네오 타이탄즈', "team_name"), types)
        self.assertIn(('서울 네오 타이탄즈', "team_name"), types)
        self.assertIn(('넥스트랩', "company_name"), types)
        self.assertIn(('잠실야구장', "place_name"), types)
        self.assertIn(('청담동', "place_name"), types)
        self.assertIn(("KBO", "league_name"), types)

        for source in {'제우스 킹즈', '네오 타이탄즈', '서울 네오 타이탄즈', '넥스트랩', '잠실야구장', '청담동', "KBO"}:
            self.assertFalse(any(row_source == source for row_source, _ in person_like), msg=source)


if __name__ == "__main__":
    unittest.main()
