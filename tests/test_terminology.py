import unittest

from app.translation.text_processing.terminology import extract_noun_terminology_candidates, merge_terminology, render_terminology_context


def ko(value: str) -> str:
    try:
        return value.encode("ascii").decode("unicode_escape")
    except UnicodeEncodeError:
        return value


class TerminologyTest(unittest.TestCase):
    def test_candidate_extraction_focuses_on_nouns_not_adjectives(self):
        text = ko("\uae40\ucca0\uc218\ub294 \ube68\uac1b\uace0 \ubd89\uc740 \ubd80\uc801\uc744 \uc0ac\ub791 \uc57d\uad6d\uc5d0\uc11c \ubc1c\uacac\ud588\ub2e4.")
        rows = extract_noun_terminology_candidates(text)
        sources = [row["source"] for row in rows]

        self.assertIn(ko("\uc0ac\ub791 \uc57d\uad6d"), sources)
        self.assertNotIn(ko("\ube68\uac1b\uace0"), sources)
        self.assertNotIn(ko("\ubd89\uc740"), sources)
        self.assertNotIn(ko("\ubc88\uc5ed\ub418\uc5b4"), sources)
        self.assertNotIn(ko("\uc774\ub984"), sources)

    def test_merge_keeps_existing_confirmed_rows_and_adds_new_candidates(self):
        existing = [
            {
                "source": ko("\uae40\ucca0\uc218"),
                "target": "Kim Cheolsu",
                "policy": "locked",
                "status": "confirmed",
            }
        ]
        merged = merge_terminology(existing, [{"source": ko("\uc0ac\ub791 \uc57d\uad6d"), "policy": "locked", "status": "suggested"}])
        context = render_terminology_context(merged, "ko_en_us", source_text=ko("\uae40\ucca0\uc218\ub294 \uc0ac\ub791 \uc57d\uad6d\uc5d0 \uac14\ub2e4."))

        self.assertTrue(any(row["source"] == ko("\uc0ac\ub791 \uc57d\uad6d") for row in merged))
        self.assertIn("Kim Cheolsu", context)
        self.assertIn("choose one translation/transliteration", context)


if __name__ == "__main__":
    unittest.main()
