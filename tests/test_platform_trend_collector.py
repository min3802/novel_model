
import unittest
from unittest.mock import Mock

from scripts.collect_platform_trends import (
    ROYALROAD_TRENDING,
    SYOSSETU_WEEKLY,
    TAPAS_POPULAR_NOVELS,
    build_rag_documents,
    collect_royalroad,
    collect_syosetu,
    collect_tapas,
    summarize,
)


class FakeResponse:
    def __init__(self, text="", data=None):
        self.text = text
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class PlatformTrendCollectorTests(unittest.TestCase):
    def test_collect_royalroad_parses_public_listing_fields(self):
        html = """
        <div class="fiction-list-item row">
          <h2 class="fiction-title"><a href="/fiction/1/test-title">Test Title</a></h2>
          <span class="label bg-blue-hoki">Original</span><span class="label bg-blue-hoki">ONGOING</span>
          <a class="fiction-tag">Progression</a><a class="fiction-tag">Magic</a>
          <div class="stats">
            <span>1,234 Followers</span><span>456 Pages</span><span>78,900 Views</span><span>12 Chapters</span>
            <div aria-label="Rating: 4.25 out of 5"></div><time datetime="2026-06-04T00:00:00Z">Jun 04, 2026</time>
          </div>
          <div id="description-1"><p>Public synopsis only.</p></div>
        </div>
        """
        session = Mock()
        session.get.return_value = FakeResponse(text=html)

        rows = collect_royalroad(ROYALROAD_TRENDING, limit=1, session=session)

        self.assertEqual(rows[0]["title"], "Test Title")
        self.assertEqual(rows[0]["genre"], "Original")
        self.assertEqual(rows[0]["tags"], ["Progression", "Magic"])
        self.assertEqual(rows[0]["public_metrics"]["followers"], 1234)
        self.assertEqual(rows[0]["public_metrics"]["views"], 78900)
        self.assertEqual(rows[0]["synopsis"], "Public synopsis only.")

    def test_collect_tapas_uses_public_landing_api_description_and_metrics(self):
        session = Mock()
        session.get.return_value = FakeResponse(
            data={
                "data": {
                    "items": [
                        {
                            "seriesId": 260446,
                            "category": {"key": "NOVEL", "value": "Novels"},
                            "mainGenre": {"key": "DRAMA", "value": "Drama"},
                            "genreList": [{"key": "DRAMA", "value": "Drama"}],
                            "title": "Debut or Die!",
                            "authorList": ["DS.Back"],
                            "publisher": "Kevin Kang",
                            "description": "Idol survival synopsis.",
                            "bmType": "WAIT_UNTIL_FREE",
                            "languageCode": "EN",
                            "issueStatus": "ON_GOING",
                            "lastEpisodeAddedDt": "2026-06-03T16:00:00Z",
                            "serviceProperty": {"viewCount": 10, "subscriberCount": 20, "likeCount": 30, "rank": 1},
                        }
                    ]
                }
            }
        )

        rows = collect_tapas(TAPAS_POPULAR_NOVELS, limit=1, session=session)

        self.assertEqual(rows[0]["title"], "Debut or Die!")
        self.assertEqual(rows[0]["genre"], "Drama")
        self.assertEqual(rows[0]["public_metrics"]["subscribers"], 20)
        self.assertEqual(rows[0]["source_url"], "https://tapas.io/series/260446")
        self.assertEqual(rows[0]["synopsis"], "Idol survival synopsis.")

    def test_collect_syosetu_parses_weekly_ranking_card(self):
        html = """
        <div class="p-ranklist-item c-card">
          <div class="p-ranklist-item__place"><span class="c-rank-place__num">51</span></div>
          <div class="p-ranklist-item__title"><a href="https://ncode.syosetu.com/n1234aa/">&#x8ee2;&#x751f;&#x30c6;&#x30b9;&#x30c8;</a></div>
          <div class="p-ranklist-item__author">&#x4f5c;&#x8005;&#x540d;</div>
          <div class="p-ranklist-item__points">1,234pt</div>
          <div class="p-ranklist-item__infomation">&#x9023;&#x8f09;&#x4e2d;(&#x5168;26&#x30a8;&#x30d4;&#x30bd;&#x30fc;&#x30c9;) 71,520&#x6587;&#x5b57; &#x7570;&#x4e16;&#x754c;&#x3014;&#x604b;&#x611b;&#x3015; &#x6700;&#x7d42;&#x66f4;&#x65b0;&#x65e5;&#xff1a;2026/06/04 19:00</div>
          <div class="p-ranklist-item__synopsis">&#x516c;&#x958b;&#x3042;&#x3089;&#x3059;&#x3058;&#x3002;</div>
          <div class="p-ranklist-item__keyword">&#x7570;&#x4e16;&#x754c;&#x8ee2;&#x751f; &#x5973;&#x4e3b;&#x4eba;&#x516c; &#x9b54;&#x6cd5;</div>
        </div>
        """
        session = Mock()
        session.get.return_value = FakeResponse(text=html)

        rows = collect_syosetu(SYOSSETU_WEEKLY, limit=1, session=session)

        self.assertEqual(rows[0]["rank"], 51)
        self.assertEqual(rows[0]["genre"], "\u7570\u4e16\u754c\u3014\u604b\u611b\u3015")
        self.assertEqual(rows[0]["public_metrics"]["weekly_points"], 1234)
        self.assertEqual(rows[0]["public_metrics"]["episodes"], 26)
        self.assertEqual(rows[0]["tags"], ["\u7570\u4e16\u754c\u8ee2\u751f", "\u5973\u4e3b\u4eba\u516c", "\u9b54\u6cd5"])

    def test_summarize_and_rag_documents_capture_localization_inputs(self):
        rows = [
            {"country": "Japan", "platform": "X", "collection": "Weekly", "ranking_basis": "weekly", "rank": 1, "title": "A", "genres": ["Romance"], "genre": "Romance", "tags": ["regression"], "synopsis": "hook", "public_metrics": {"views": 1}, "source_url": "https://x/a"},
            {"country": "Japan", "platform": "X", "collection": "Weekly", "ranking_basis": "weekly", "rank": 2, "title": "B", "genres": ["Romance"], "genre": "Romance", "tags": ["magic"], "synopsis": "hook2", "public_metrics": {}, "source_url": "https://x/b"},
        ]
        self.assertEqual(summarize(rows)["top_genres"][0], ("Romance", 2))
        docs = build_rag_documents(rows)
        self.assertIn("Rank 1: A", docs[0]["context_text"])
        self.assertEqual(docs[0]["metadata"]["ranking_basis"], "weekly")


if __name__ == "__main__":
    unittest.main()
