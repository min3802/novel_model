"""이미지 기능 추출·생성·파이프라인 단위 테스트 (mock 모드 — 네트워크/LLM 불필요).

표지/관계도는 별개 플로우다. 각 플로우의 추출→생성, 안전검사, 파이프라인을 검증한다.
실제 end-to-end(mock=False)는 tests/check_image_extraction.py 를
OPENAI_API_KEY 가 있는 로컬 환경에서 실행해 확인한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("WLIGHTER_MOCK_MODE", "true")


# ----------------------------- 표지 추출 -----------------------------
def test_cover_extract_has_arc_and_key_moments():
    from app.image import CoverCharacter, CoverExtractor, CoverExtractionResult

    result = CoverExtractor().extract("스물여섯 살에 음대 교수가 된 톱스타 이야기.")
    assert isinstance(result, CoverExtractionResult)
    assert result.characters
    c = result.characters[0]
    assert isinstance(c, CoverCharacter)
    assert c.arc_summary
    assert isinstance(c.key_moments, list)
    assert isinstance(c.appearance, list)


def test_cover_protagonist_prefers_main_role():
    from app.image import CoverExtractor
    result = CoverExtractor().extract("원문")
    assert result.protagonist() is not None
    assert result.protagonist().role.startswith("주")


def test_cover_episode_limit_caps_at_10(monkeypatch):
    from app.image import CoverExtractor, ImageConfig
    from app.image.infra import _extract_base
    captured = {}
    orig = _extract_base.join_episodes

    def spy(eps, max_episodes):
        captured["max_episodes"] = max_episodes
        return orig(eps, max_episodes)

    monkeypatch.setattr("app.image.extract.cover_extractor.join_episodes", spy)
    CoverExtractor(ImageConfig()).extract([f"{i}화" for i in range(30)])
    assert captured["max_episodes"] == 10


# ----------------------------- 관계도 추출 -----------------------------
def test_relation_extract_nodes_and_relations():
    from app.image import Relation, RelationExtractionResult, RelationExtractor, RelationNode

    result = RelationExtractor().extract("소년과 소녀가 만난다.")
    assert isinstance(result, RelationExtractionResult)
    assert result.nodes and all(isinstance(n, RelationNode) for n in result.nodes)
    for r in result.relations:
        assert isinstance(r, Relation)
        assert isinstance(r.directed, bool)
        assert r.from_ and r.to and r.relation_type


def test_relation_to_dict_shape():
    from app.image import RelationExtractor
    d = RelationExtractor().extract("원문").to_dict()
    assert set(d.keys()) == {"nodes", "relations"}
    for r in d["relations"]:
        assert set(r.keys()) == {"from", "to", "relation_type", "directed", "evidence"}


def test_relation_episode_limit_caps_at_20(monkeypatch):
    from app.image import RelationExtractor, ImageConfig
    from app.image.infra import _extract_base
    captured = {}
    orig = _extract_base.join_episodes

    def spy(eps, max_episodes):
        captured["max_episodes"] = max_episodes
        return orig(eps, max_episodes)

    monkeypatch.setattr("app.image.extract.relation_extractor.join_episodes", spy)
    RelationExtractor(ImageConfig()).extract([f"{i}화" for i in range(40)])
    assert captured["max_episodes"] == 20


def test_join_episodes_no_char_truncation():
    """max_chars 절단 제거 확인: 아주 긴 화도 그대로 보존(화 경계 안 깨짐)."""
    from app.image.infra._extract_base import join_episodes
    long_ep = "가" * 100000
    out = join_episodes([long_ep], max_episodes=10)
    assert out.count("가") == 100000
    assert out.startswith("=== 1화 ===")


def test_empty_source_raises():
    from app.image import CoverExtractor, RelationExtractor
    with pytest.raises(ValueError):
        CoverExtractor().extract("   ")
    with pytest.raises(ValueError):
        RelationExtractor().extract("   ")


# ----------------------------- 표지 생성 + 안전검사 -----------------------------
def test_cover_generate_prompt_and_notice():
    from app.image import CoverExtractor, CoverGenerator
    extraction = CoverExtractor().extract("원문")
    out = CoverGenerator().generate(extraction, work_title="소나기", genre="첫사랑", extra_prompt="제목 공간 확보")
    assert out["type"] == "mock_image"
    assert out["notice"] == "AI 생성 이미지입니다."
    assert "vertical commercial web novel cover" in out["prompt"]
    assert "title-safe negative space" in out["prompt"]
    assert "Protagonist arc in these episodes" in out["prompt"]


def test_cover_safety_refusal_with_alternative():
    from app.image import CoverExtractor, CoverGenerator
    extraction = CoverExtractor().extract("원문")
    out = CoverGenerator().generate(extraction, extra_prompt="나체로 서 있음")
    assert out["type"] == "refusal"
    assert "생성해드릴 수 없습니다" in out["message"]
    assert "조정" in out["message"] or "대신" in out["message"]


# ----------------------------- 관계도 생성 -----------------------------
def test_relation_generate_prompt():
    from app.image import RelationExtractor, RelationGenerator
    extraction = RelationExtractor().extract("원문")
    out = RelationGenerator().generate(extraction, work_title="소나기")
    assert out["type"] == "mock_image"
    assert "relationship map" in out["prompt"]


# ----------------------------- 파이프라인 (오케스트레이터) -----------------------------
def test_cover_pipeline_run():
    from app.image import CoverPipeline, CoverResult
    result = CoverPipeline().run(["1화", "2화"], work_title="작품", genre="음악")
    assert isinstance(result, CoverResult)
    assert result.extraction.characters
    assert result.image["type"] == "mock_image"
    assert result.refused is False
    d = result.to_dict()
    assert set(d.keys()) == {"extraction", "image"}


def test_cover_pipeline_refusal():
    from app.image import CoverPipeline
    result = CoverPipeline().run("원문", extra_prompt="나체로 서 있음")
    assert result.refused is True
    assert result.image["type"] == "refusal"


def test_relation_pipeline_run():
    from app.image import RelationPipeline, RelationResult
    result = RelationPipeline().run(["1화", "2화"], work_title="작품")
    assert isinstance(result, RelationResult)
    assert result.extraction.nodes
    assert result.image["type"] == "mock_image"


# ----------------------------- 안전검사 사전필터 -----------------------------
def test_unsafe_prefilter():
    from app.image import is_unsafe_visual_request
    assert is_unsafe_visual_request("나체로 서 있음")
    assert is_unsafe_visual_request("fully naked pose")
    assert not is_unsafe_visual_request("비에 젖은 채 서 있음")
