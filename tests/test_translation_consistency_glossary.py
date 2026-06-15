from __future__ import annotations

import os
import unittest

import api_server
from app.translation.text_processing.consistency_checker import check_translation_consistency
from app.translation.text_processing.terminology import (
    TERMINOLOGY_POLICY_LOCKED,
    TERMINOLOGY_POLICY_PREFERRED,
    extract_noun_terminology_candidates,
    render_terminology_context,
)


def ko(value: str) -> str:
    try:
        return value.encode("ascii").decode("unicode_escape")
    except UnicodeEncodeError:
        return value


SARANG_PHARMACY = ko('사랑 약국')
DONGSOMUN_MARKET = ko('동소문 시장')
PHARMACY = ko('약국')
KIM_CHEOMJI = ko('김첨지')
THAILAND = ko('태국')


class TranslationConsistencyGlossaryTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["WLIGHTER_MOCK_MODE"] = "true"

    def test_named_business_phrase_is_locked_before_common_noun(self) -> None:
        text = ko('김첨지는 사랑 약국 앞에서 동소문 시장 쪽을 바라봤다. 근처 약국은 이미 문을 닫았다.')
        candidates = extract_noun_terminology_candidates(text)
        sources = [row["source"] for row in candidates]

        self.assertIn(SARANG_PHARMACY, sources)
        self.assertIn(DONGSOMUN_MARKET, sources)
        self.assertIn(PHARMACY, sources)
        self.assertNotIn(ko('앞에서 동'), sources)
        self.assertLess(sources.index(SARANG_PHARMACY), sources.index(PHARMACY))
        locked = next(row for row in candidates if row["source"] == SARANG_PHARMACY)
        self.assertEqual(locked["policy"], TERMINOLOGY_POLICY_LOCKED)
        self.assertEqual(locked["type"], "business_name")
        common = next(row for row in candidates if row["source"] == PHARMACY)
        self.assertEqual(common["policy"], TERMINOLOGY_POLICY_PREFERRED)
        self.assertIn("drugstore", common["allowedTranslations"])

    def test_locked_phrase_flags_variant_but_preferred_common_noun_accepts_variant(self) -> None:
        terminology = [
            {
                "source": SARANG_PHARMACY,
                "target": "Sarang Pharmacy",
                "allowedTranslations": [],
                "policy": "locked",
                "type": "business_name",
                "status": "confirmed",
            },
            {
                "source": PHARMACY,
                "target": "pharmacy",
                "allowedTranslations": ["pharmacy", "drugstore"],
                "policy": "preferred",
                "type": "common_noun",
                "status": "confirmed",
            },
        ]
        source = ko('사랑 약국에서 약을 사고 근처 약국으로 갔다.')
        ok = check_translation_consistency(
            source_text=source,
            translated_text="He bought medicine at Sarang Pharmacy and then went to a drugstore nearby.",
            locale="ko_en_us",
            terminology=terminology,
        )
        bad = check_translation_consistency(
            source_text=source,
            translated_text="He bought medicine at Sarang Drugstore and then went to a drugstore nearby.",
            locale="ko_en_us",
            terminology=terminology,
        )

        self.assertEqual(ok["status"], "pass")
        self.assertEqual(bad["status"], "warning")
        self.assertEqual(bad["issues"][0]["type"], "terminology_mismatch")
        self.assertEqual(bad["issues"][0]["source"], SARANG_PHARMACY)

    def test_render_terminology_context_includes_noun_only_rules(self) -> None:
        terminology = [
            {
                "source": SARANG_PHARMACY,
                "target": "Sarang Pharmacy",
                "policy": "locked",
                "type": "business_name",
                "status": "confirmed",
            }
        ]
        context = render_terminology_context(terminology, "ko_en_us", source_text=ko('사랑 약국에 갔다.'))

        self.assertIn("LOCKED", context)
        self.assertIn(SARANG_PHARMACY, context)
        self.assertIn("Sarang Pharmacy", context)
        self.assertIn("do not freeze verbs", context)

    def test_translate_accepts_explicit_terminology_without_legacy_memory(self) -> None:
        work = api_server.work_create({"title": ko('운수 좋은 날'), "genre": ko('현대문학')})
        result = api_server.translate(
            {
                "workId": work["id"],
                "sourceText": ko('김첨지는 사랑 약국 앞에서 동소문 시장을 바라봤다.'),
                "targetCountry": THAILAND,
                "terminology": [
                    {
                        "source": KIM_CHEOMJI,
                        "target": "Kim Cheomji",
                        "policy": "locked",
                        "type": "person_name",
                        "status": "confirmed",
                    }
                ],
            }
        )

        self.assertIn("consistency", result["workflow"])
        self.assertIn("terminologyCandidates", result)
        self.assertIn("Terminology", result["workflow"]["terminology_context"])
        self.assertIsNone(result["memory"])


if __name__ == "__main__":
    unittest.main()
