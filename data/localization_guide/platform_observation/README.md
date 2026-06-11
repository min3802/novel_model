# Platform Observation Market Signals

This directory stores public platform-listing samples for localization market observation.

## Purpose

The data is for aggregate market observation only. It must not be used to recommend specific works, compare a user story to individual popular works, copy synopsis content, or steer creative direction from a single title.

## Pipeline

Run collection and legacy compatibility summary generation:

```powershell
C:\Users\kwonm\anaconda3\python.exe scripts\collect_market_observations.py
```

Rebuild legacy summary artifacts from existing raw files without network requests:

```powershell
C:\Users\kwonm\anaconda3\python.exe scripts\collect_market_observations.py --from-raw
```

Build country/market-specific Korean context packs from existing raw files:

```powershell
C:\Users\kwonm\anaconda3\python.exe scripts\build_platform_observation_context_packs.py
```

Collect a subset:

```powershell
C:\Users\kwonm\anaconda3\python.exe scripts\collect_market_observations.py --target "Royal Road"
C:\Users\kwonm\anaconda3\python.exe scripts\collect_market_observations.py --target ReadAWrite
```

## Storage layout

- `raw/<group>/<platform>_<signal_type>.json`: minimal raw listing samples.
- `processed/`: normalized observation records plus aggregate context-pack inputs.
- `processed/context_packs/*_observation_context_ko.md`: Korean prompt-ready context packs by market.
- `platform_trends_current.json`: legacy compatibility dataset for existing guide/advisor code.

## Context pack usage

Use context packs before adding RAG. The default localization-analysis prompt should include:

1. `processed/context_packs/global_observation_overview_ko.md`
2. exactly one target-market pack, such as `japan_observation_context_ko.md`
3. the target country's regulation/regulatory context when available
4. the work being analyzed

Do not put every market pack into a single-country analysis. Multi-market packs should be included only when the user explicitly asks for a comparison, and the output must stay parallel/descriptive rather than recommending one market over another.

Context pack constraints:

- Use only as public ranking/listing observation summaries.
- Do not use for recommendations, performance prediction, market-fit scoring, or creative-direction advice.
- Phrase findings as "observed in the sample", "sample frequency", or "review reference".
- Do not directly compare public metrics across platforms.
- WebNovel is excluded from context packs because its `Global` market does not cleanly map to country-level regulation data.
- Royal Road `trending` is excluded from context packs to reduce duplicate signal-type weight; Royal Road `weekly_popular` is retained.

## Raw schema

Raw records intentionally keep only minimal market-observation fields:

```json
{
  "market": "US",
  "language_market": "English",
  "raw_language": "en",
  "platform": "Royal Road",
  "signal_type": "weekly_popular",
  "rank": 1,
  "title": "...",
  "labels": ["Fantasy", "LitRPG"],
  "synopsis": "public listing synopsis only",
  "public_metrics": {"views": 1234}
}
```

Do not add authors, source URLs, chapter/body text, locked content, comments, images, or login-only fields to RAG-facing data.

## Current target status

Ranking observation now follows the collection-overview platform set first, then keeps non-overview sources only as proxy/comparison signals.

### Overview-aligned ranking targets

- US: Wattpad `hot_fantasy` 100/100 ok; Tapas `popular_novels` 100/100 ok; WebNovel `power_ranking` 100/100 ok and `trending` 50/50 ok.
- JP: Syosetu `weekly_ranking` 100/100 ok and `monthly_ranking` 100/100 ok; Kakuyomu `weekly_ranking` 100/100 ok; Alphapolis `hot_24h` 40/100 partial because the public first page exposes 40 items.
- CN: JJWXC `monthly_rank` 100/100 ok. Qidian was tested but not added because ranking pages returned 202/empty challenge-like HTML or reset connections. Fanqie was tested but not added because public rank text uses custom font/glyph substitution, making title/synopsis unsuitable without a decoder.
- TH: ReadAWrite `popular` 100/100 ok; Dek-D `popular` 20/100 partial because the public list exposes 20 unique items; Joylada `homepage_ranking` 15/100 partial because the homepage exposes three ranking boxes with five public items each.

### Proxy/comparison targets retained

- Royal Road `weekly_popular`: 100/100 ok
- Royal Road `trending`: 50/50 ok
- Scribble Hub `weekly_popular`: 100/100 ok
- Scribble Hub `rising`: 50/50 ok
- Zongheng `monthly_ticket`: 36/50 partial; kept as CN proxy because Qidian/Fanqie are not cleanly collectible through public listing HTML
- Honeyfeed historical raw files may still appear as `error` if present from earlier runs, but Honeyfeed is no longer an overview-aligned target.

The summary file records each target as `ok`, `partial`, `empty`, or `error`.

## Retrieval note

Do not add RAG by default for this dataset. Current localization-analysis work should use the small market-specific context packs first. If a later phase reintroduces retrieval, keep it aggregate-only and preserve the current no-recommendation/no-performance-prediction constraints.
