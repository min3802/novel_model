from __future__ import annotations

import unittest

from app.guide.localization_mvp_pipeline import build_localization_guide_mvp, build_policy_checkpoints
from app.guide.cultural_localization import _tokens
from app.guide.work_analysis import analyze_work
from backend.services.guide_service import guide


class LocalizationGuideMvpPipelineTests(unittest.TestCase):
    def test_cultural_tokenizer_keeps_korean_terms(self) -> None:
        self.assertIn("예비군", _tokens("\uc608\ube44\uad70 \ud55c\uad6d \uad70\ubcf5"))
        self.assertIn("한국", _tokens("\uc608\ube44\uad70 \ud55c\uad6d \uad70\ubcf5"))

    def test_work_analyzer_extracts_elements_and_cautions(self) -> None:
        work = analyze_work(
            {
                "targetCountry": "US",
                "title": "예비군 8년차는 비상소집을 거부한다",
                "genre": "현대 판타지",
                "synopsis": "서울에서 전역 후 살아가던 주인공이 예비군 비상소집과 괴물 습격에 휘말린다. 폭력 가능성이 있다.",
            }
        )

        self.assertEqual(work["mode"], "detailed")
        self.assertEqual(work["targetCountry"], "US")
        self.assertIn("예비군", work["confirmedElements"])
        self.assertIn("군 복무", work["confirmedElements"])
        self.assertIn("현대 한국 배경", work["confirmedElements"])
        self.assertIn("군사/국가 시스템", work["contentCautions"])
        self.assertIn("잔혹 묘사", work["contentCautions"])


    def test_work_analyzer_keeps_raw_input_signals_separate_from_confirmed_elements(self) -> None:
        work = analyze_work(
            {
                "targetCountry": "US",
                "title": "\ub7ec\ube0c \uc564 \ube14\ub7ec\ub4dc",
                "genre": "\ud604\ub300 \ub85c\ub9e8\uc2a4 / \uc791\uac00\ubb3c / \ud610\uad00 \ub85c\ub9e8\uc2a4 / \uc0c1\ucc98 \uce58\uc720",
                "synopsis": "\uc0c1\ucc98\ub97c \uc228\uae34 \uc791\uac00\uac00 \uacc4\uc57d \uad00\uacc4\ub85c \uc5bd\ud78c \uc0c1\ub300\uc640 \ud610\uad00 \ub85c\ub9e8\uc2a4\ub97c \uc2dc\uc791\ud55c\ub2e4. \uacfc\uac70 \uc0b4\uc778 \uc0ac\uac74\uacfc \ud2b8\ub77c\uc6b0\ub9c8\uac00 \ub450 \uc0ac\ub78c\uc758 \uac10\uc815 \uc131\uc7a5\uc744 \ud754\ub4e0\ub2e4.",
                "declaredSignals": [
                    "\uc791\uac00\uc640 \uc791\uac00",
                    "\uacc4\uc57d\uad00\uacc4",
                    "\ud610\uad00\uc5d0\uc11c \ub85c\ub9e8\uc2a4",
                    "\uc804\uc560\uc778 \ud2b8\ub77c\uc6b0\ub9c8",
                    "\uc0c1\ucc98\ub140",
                    "\uc131\uc7a5\ud615 \ub85c\ub9e8\uc2a4",
                    "\uac10\uc815 \uce58\uc720",
                    "\uba5c\ub85c \uacfc\uc678",
                ],
            }
        )

        elements = work["confirmedElements"]
        self.assertIn("\uc791\uac00\ubb3c", elements)
        self.assertIn("\uacc4\uc57d \uad00\uacc4", elements)
        self.assertIn("\ud610\uad00 \ub85c\ub9e8\uc2a4", elements)
        self.assertIn("\uc0c1\ucc98 \uce58\uc720", elements)
        self.assertNotIn("\uc791\uac00\uc640 \uc791\uac00", elements)
        self.assertNotIn("\ud610\uad00\uc5d0\uc11c \ub85c\ub9e8\uc2a4", elements)
        self.assertIn("\uc791\uac00\uc640 \uc791\uac00", work["supportingInputSignals"])
        self.assertIn("\uba5c\ub85c \uacfc\uc678", work["additionalInputSignals"])

    def test_modern_romance_genre_does_not_imply_korean_setting(self) -> None:
        work = analyze_work(
            {
                "targetCountry": "US",
                "genre": "현대 로맨스",
                "title": "Love Contract",
            }
        )

        self.assertEqual(work["mode"], "baseline")
        self.assertIn("로맨스 관계", work["confirmedElements"])
        self.assertNotIn("현대 한국 배경", work["confirmedElements"])

    def test_age_rating_and_sexual_violence_are_separate_cautions(self) -> None:
        work = analyze_work(
            {
                "targetCountry": "US",
                "title": "어두운 밤",
                "genre": "스릴러",
                "synopsis": "R15 등급으로 검토 중이며 성폭력 피해와 폭력 사건을 다룬다.",
            }
        )

        self.assertIn("연령 등급 표시", work["contentCautions"])
        self.assertIn("성폭력 소재", work["contentCautions"])
        self.assertIn("잔혹 묘사", work["contentCautions"])
        self.assertNotIn("성적 묘사", work["contentCautions"])

    def test_mvp_pipeline_builds_culture_policy_metadata_report(self) -> None:
        result = build_localization_guide_mvp(
            {
                "targetCountry": "US",
                "title": "예비군 8년차는 비상소집을 거부한다",
                "genre": "현대 판타지",
                "synopsis": "서울에서 전역 후 살아가던 주인공이 예비군 비상소집과 괴물 습격에 휘말린다.",
            }
        )

        self.assertEqual(result["pipelineVersion"], "localization_guide_mvp_v1")
        self.assertEqual(result["guideKind"], "metadata_culture_policy_localization_guide")
        self.assertIn("workProfile", result)
        self.assertIn("marketContext", result)
        self.assertIn("culturalLocalization", result)
        self.assertIn("policyCheck", result)
        self.assertIn("metadataPositioning", result)
        self.assertIn("finalGuard", result)
        self.assertTrue(result["localizationGuideMvp"]["cultureNotes"])
        self.assertTrue(result["localizationGuideMvp"]["metadataDirections"])
        self.assertIn("no_story_rewrite_instruction", result["finalGuard"]["overclaimPrevention"])
        self.assertTrue(
            any("성공 가능성" in item or "독자 선호" in item for item in result["localizationGuideMvp"]["limitations"])
        )

    def test_policy_checkpoints_use_work_cautions_not_raw_synopsis(self) -> None:
        payload = {
            "targetCountry": "Japan",
            "title": "평범한 공녀",
            "genre": "로맨스 판타지",
            "synopsis": "성적 묘사와 잔혹 묘사가 짙어 R18 표시를 검토해야 한다.",
        }
        work = analyze_work(payload)
        policy = build_policy_checkpoints(payload, work)

        self.assertEqual(policy["matchedFrom"], "work_profile.contentCautions")
        self.assertEqual(policy["contentCautions"], work["contentCautions"])
        self.assertTrue(policy["policyCheckpoints"])
        self.assertTrue(
            all(card["match_source"] == "direct_input" for card in policy["policyCheckpoints"]),
            "새 정책 체크는 원문 전체가 아니라 Work Analyzer의 contentCautions를 직접 입력으로 사용해야 한다.",
        )
        self.assertTrue(all("checkpoint" in card for card in policy["policyCheckpoints"]))
        self.assertTrue(
            any(card["card_title"] == "폭력/잔혹 묘사 수위 확인" for card in policy["policyCheckpoints"])
        )

    def test_culture_notes_avoid_unrelated_rag_but_keep_general_korean_source_guidance(self) -> None:
        result = build_localization_guide_mvp(
            {
                "targetCountry": "US",
                "title": "러브 앤 블러드",
                "genre": "현대 로맨스 / 작가물 / 혐관 로맨스 / 상처 치유",
                "synopsis": (
                    "상처를 숨긴 작가가 계약 관계로 얽힌 상대와 혐관 로맨스를 시작한다. "
                    "두 사람은 서로의 글과 감정을 배우며 오해를 풀고 성장한다. "
                    "출판사와 소설 작업을 둘러싼 갈등은 있지만 별도 제도나 의례 설명이 필요한 소재는 없다."
                ),
            }
        )

        self.assertEqual(result["reportMode"], "detailed")
        notes = result["culturalLocalization"]["cultureNotes"]
        self.assertTrue(notes)
        self.assertEqual(notes[0]["element"], "한국어 원문 관계 표현")
        self.assertFalse(
            any(note["element"] in {"한국 군복 패턴 구분", "학생 서열 문화", "교복 소비 서열 문화"} for note in notes)
        )
        self.assertEqual(result["culturalLocalization"]["evidence"]["kcultureCardCount"], 0)

    def test_guide_service_uses_new_criteria_flow_by_default(self) -> None:
        result = guide(
            {
                "targetCountry": "Japan",
                "title": "?????? ???????? ??? ?????",
                "genre": "??????????",
                "synopsis": "????????????? ????? ?????????????????????.",
            }
        )

        self.assertIn("recommendedCountries", result)
        self.assertIn("translation_profile", result)
        self.assertIn("summary_text", result)
        self.assertIn("htmlReport", result)
        self.assertIn("\ubc88\uc5ed \uc804 \ud604\uc9c0\ud654 \uae30\uc900\uc11c", result["htmlReport"])
        self.assertIn(result["generationMode"], {"recommended_country_selected", "manual_country_after_recommendation"})
        self.assertEqual(result["mode"], "country_genre_guide")
        self.assertNotIn("Localization Guide MVP", result["htmlReport"])
        self.assertNotIn("reportMode:", result["htmlReport"])
        self.assertIn("번역 전 현지화 기준서", result["htmlReport"])

    def test_guide_service_preserves_legacy_path_when_requested(self) -> None:
        result = guide(
            {
                "legacyGuide": True,
                "targetCountry": "Japan",
                "title": "버림받은 공녀는 다시 웃지 않는다",
                "genre": "로맨스 판타지",
                "synopsis": "가문에서 버림받은 공녀가 회귀해 자신의 자리를 되찾는다.",
            }
        )

        self.assertIn("contextPackBriefing", result)
        self.assertIn("policyAttentionCards", result)
        self.assertNotIn("pipelineVersion", result)


if __name__ == "__main__":
    unittest.main()
