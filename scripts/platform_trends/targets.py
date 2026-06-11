from __future__ import annotations

from scripts.platform_trends.schema import MarketTrendTarget

# Ranking-observation targets are aligned first to the policy/platform overview:
# US: Wattpad, Tapas, WebNovel; JP: Syosetu, Kakuyomu, Alphapolis;
# CN: Qidian/Fanqie/JJWXC where accessible; TH: ReadAWrite, Dek-D, Joylada.
# Non-overview proxy targets remain for comparison only and are grouped separately.
TARGETS: list[MarketTrendTarget] = [
    MarketTrendTarget("US", "English", "en", "Wattpad", "hot_fantasy", "https://www.wattpad.com/stories/fantasy/hot", 100, "english"),
    MarketTrendTarget("US", "English", "en", "Tapas", "popular_novels", "https://tapas.io/menu/3/subtab/24", 100, "english"),
    MarketTrendTarget("Global", "English/Chinese-global", "en", "WebNovel", "power_ranking", "https://www.webnovel.com/ranking/novel/annual/power_rank", 100, "english"),
    MarketTrendTarget("Global", "English/Chinese-global", "en", "WebNovel", "trending", "https://www.webnovel.com/ranking/hot", 50, "english"),
    MarketTrendTarget("Japan", "Japanese", "ja", "Syosetu", "weekly_ranking", "https://yomou.syosetu.com/rank/list/type/weekly_r/", 100, "japanese"),
    MarketTrendTarget("Japan", "Japanese", "ja", "Syosetu", "monthly_ranking", "https://yomou.syosetu.com/rank/list/type/monthly_r/", 100, "japanese"),
    MarketTrendTarget("Japan", "Japanese", "ja", "Kakuyomu", "weekly_ranking", "https://kakuyomu.jp/rankings/all/weekly?work_variation=long", 100, "japanese"),
    MarketTrendTarget("Japan", "Japanese", "ja", "Alphapolis", "hot_24h", "https://www.alphapolis.co.jp/novel/index?sort=24hpt", 100, "japanese"),
    MarketTrendTarget("China", "Chinese", "zh", "JJWXC", "monthly_rank", "https://m.jjwxc.net/rank/index", 100, "chinese"),
    MarketTrendTarget("China", "Chinese", "zh", "Zongheng", "monthly_ticket", "https://www.zongheng.com/rank", 50, "chinese_proxy"),
    MarketTrendTarget("Thailand", "Thai", "th", "ReadAWrite", "popular", "https://www.readawrite.com/", 100, "thai"),
    MarketTrendTarget("Thailand", "Thai", "th", "Dek-D", "popular", "https://www.dek-d.com/writer/feature/list/popular", 100, "thai"),
    MarketTrendTarget("Thailand", "Thai", "th", "Joylada", "homepage_ranking", "https://www.joylada.com/", 100, "thai"),
    MarketTrendTarget("US", "English", "en", "Royal Road", "weekly_popular", "https://www.royalroad.com/fictions/weekly-popular", 100, "english_proxy"),
    MarketTrendTarget("US", "English", "en", "Royal Road", "trending", "https://www.royalroad.com/fictions/trending", 50, "english_proxy"),
    MarketTrendTarget("US", "English", "en", "Scribble Hub", "weekly_popular", "https://www.scribblehub.com/series-ranking/?order=4&sort=1", 100, "english_proxy"),
    MarketTrendTarget("US", "English", "en", "Scribble Hub", "rising", "https://www.scribblehub.com/series-ranking/?order=1&sort=5", 50, "english_proxy"),
]


def target_by_key(key: str) -> MarketTrendTarget:
    for target in TARGETS:
        if target.key == key:
            return target
    raise KeyError(key)
