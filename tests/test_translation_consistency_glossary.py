from __future__ import annotations

import os
import unittest

import api_server
from ko_locale_pipeline.consistency_checker import check_translation_consistency
from ko_locale_pipeline.terminology import (
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


SARANG_PHARMACY = ko("\uc0ac\ub791 \uc57d\uad6d")
DONGSOMUN_MARKET = ko("\ub3d9\uc18c\ubb38 \uc2dc\uc7a5")
PHARMACY = ko("\uc57d\uad6d")
KIM_CHEOMJI = ko("\uae40\ucca8\uc9c0")
THAILAND = ko("\ud0dc\uad6d")


class TranslationConsistencyGlossaryTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["WLIGHTER_MOCK_MODE"] = "true"

    def test_named_business_phrase_is_locked_before_common_noun(self) -> None:
        text = ko("\uae40\ucca8\uc9c0\ub294 \uc0ac\ub791 \uc57d\uad6d \uc55e\uc5d0\uc11c \ub3d9\uc18c\ubb38 \uc2dc\uc7a5 \ucabd\uc744 \ubc14\ub77c\ubd24\ub2e4. \uadfc\ucc98 \uc57d\uad6d\uc740 \uc774\ubbf8 \ubb38\uc744 \ub2eb\uc558\ub2e4.")
        candidates = extract_noun_terminology_candidates(text)
        sources = [row["source"] for row in candidates]

        self.assertIn(SARANG_PHARMACY, sources)
        self.assertIn(DONGSOMUN_MARKET, sources)
        self.assertIn(PHARMACY, sources)
        self.assertNotIn(ko("\uc55e\uc5d0\uc11c \ub3d9"), sources)
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
        source = ko("\uc0ac\ub791 \uc57d\uad6d\uc5d0\uc11c \uc57d\uc744 \uc0ac\uace0 \uadfc\ucc98 \uc57d\uad6d\uc73c\ub85c \uac14\ub2e4.")
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
        context = render_terminology_context(terminology, "ko_en_us", source_text=ko("\uc0ac\ub791 \uc57d\uad6d\uc5d0 \uac14\ub2e4."))

        self.assertIn("LOCKED", context)
        self.assertIn(SARANG_PHARMACY, context)
        self.assertIn("Sarang Pharmacy", context)
        self.assertIn("do not freeze verbs", context)

    def test_translate_accepts_explicit_terminology_without_legacy_memory(self) -> None:
        work = api_server.work_create({"title": ko("\uc6b4\uc218 \uc88b\uc740 \ub0a0"), "genre": ko("\ud604\ub300\ubb38\ud559")})
        result = api_server.translate(
            {
                "workId": work["id"],
                "sourceText": ko("\uae40\ucca8\uc9c0\ub294 \uc0ac\ub791 \uc57d\uad6d \uc55e\uc5d0\uc11c \ub3d9\uc18c\ubb38 \uc2dc\uc7a5\uc744 \ubc14\ub77c\ubd24\ub2e4."),
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
