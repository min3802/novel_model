"use client";

import { useEffect, useRef, useState } from "react";
import { postJson } from "@/features/shared/api";

const API_BASE = process.env.NEXT_PUBLIC_WLIGHTER_API_BASE || "http://127.0.0.1:8000";

type GuideSection = { title: string; items: string[] };
type GuideEvidence = {
  platform: string;
  collection: string;
  rank: number;
  title: string;
  genre?: string | null;
  tags?: string[];
  source_url?: string | null;
  reason?: string;
};
type GuideRecommendation = {
  country: string;
  score: number;
  reasons: string[];
};
type GuideOptions = {
  countries?: { country: string; topGenres?: [string, number][]; topTags?: [string, number][]; platforms?: string[] }[];
  genres?: string[];
};
type GuideResult = {
  mode: "needs_country_and_genre_selection" | "country_genre_guide" | "synopsis_country_recommendation" | string;
  requiresSelection?: boolean;
  message?: string;
  availableOptions?: GuideOptions;
  title?: string;
  targetCountry?: string;
  country?: string;
  genre?: string;
  synopsis?: string;
  recommendedCountries?: GuideRecommendation[];
  htmlReport?: string;
  sections?: Record<string, GuideSection>;
  evidenceUsed?: GuideEvidence[];
  modelPromptPayload?: unknown;
  createdAt?: string;
};
type GuideRecord = { id: number; work_id?: number | null; payload: Record<string, unknown>; guide: GuideResult; created_at: string };
type GuideResponse = GuideResult & { guideRecord?: GuideRecord };
type GuideHistoryItem = GuideResult & { id?: number; savedAt: string };

const GUIDE_SECTION_ORDER = [
  "market_trend_fit",
  "genre_trope_alignment",
  "title_synopsis_localization",
  "terminology_glossary_risks",
  "content_rating_sensitivity",
  "adaptation_checklist",
  "evidence_used",
];

const COUNTRY_OPTIONS = [
  { label: "??/???", value: "??" },
  { label: "??", value: "??" },
];

function guideDisplayTitle(result: GuideResult) {
  return result.title || `${result.targetCountry || result.country || "?? ??"} ??? ???`;
}

function guideMetaItems(result: GuideResult) {
  return [
    result.mode === "synopsis_country_recommendation" ? "???? ?? ??" : result.mode === "country_genre_guide" ? "??/?? ?? ??" : "?? ??",
    result.genre || "?? ???",
    result.targetCountry || result.country || "?? ???",
    result.createdAt || "",
  ].filter(Boolean);
}

function safeFilename(value: string) {
  return value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, "_")
    .slice(0, 80) || "localization-guide";
}

function guideToMarkdown(result: GuideResult) {
  const lines: string[] = [];
  lines.push(`# ${guideDisplayTitle(result)}`);
  lines.push("");
  lines.push(`- Mode: ${result.mode}`);
  lines.push(`- Country: ${result.targetCountry || result.country || "Not selected"}`);
  lines.push(`- Genre: ${result.genre || "Not provided"}`);
  if (result.createdAt) lines.push(`- Created at: ${result.createdAt}`);
  if (result.synopsis) {
    lines.push("");
    lines.push("## Synopsis");
    lines.push(result.synopsis);
  }
  if (result.recommendedCountries?.length) {
    lines.push("");
    lines.push("## Recommended countries");
    result.recommendedCountries.forEach(rec => {
      lines.push(`- ${rec.country} (${rec.score}): ${rec.reasons.join("; ")}`);
    });
  }
  if (result.sections) {
    const ordered = [
      ...GUIDE_SECTION_ORDER.flatMap(key => result.sections?.[key] ? [[key, result.sections[key]] as const] : []),
      ...Object.entries(result.sections).filter(([key]) => !GUIDE_SECTION_ORDER.includes(key)),
    ];
    ordered.forEach(([key, section]) => {
      lines.push("");
      lines.push(`## ${section.title || key}`);
      (section.items || []).forEach(item => lines.push(`- ${item}`));
    });
  }
  if (result.evidenceUsed?.length) {
    lines.push("");
    lines.push("## Evidence used");
    result.evidenceUsed.forEach(ev => {
      lines.push(`- ${ev.platform} / ${ev.collection} rank ${ev.rank}: ${ev.title}${ev.genre ? ` (${ev.genre})` : ""}`);
      if (ev.reason) lines.push(`  - Reason: ${ev.reason}`);
      if (ev.tags?.length) lines.push(`  - Tags: ${ev.tags.slice(0, 12).join(", ")}`);
      if (ev.source_url) lines.push(`  - Source: ${ev.source_url}`);
    });
  }
  lines.push("");
  lines.push("---");
  lines.push("Evidence boundary: platform trend metadata only; not national readership certainty.");
  return lines.join("\n");
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadGuide(result: GuideResult, format: "md" | "json") {
  const base = safeFilename(`${guideDisplayTitle(result)}-${result.targetCountry || result.country || "country"}-${result.genre || "genre"}`);
  if (format === "json") {
    downloadText(`${base}.json`, JSON.stringify(result, null, 2), "application/json;charset=utf-8");
    return;
  }
  downloadText(`${base}.md`, guideToMarkdown(result), "text/markdown;charset=utf-8");
}

export function GuideConnector() {
  const [country, setCountry] = useState("");
  const [genre, setGenre] = useState("濡쒕㎤???먰?吏");
  const [synopsis, setSynopsis] = useState("");
  const [result, setResult] = useState<GuideResult | null>(null);
  const [history, setHistory] = useState<GuideHistoryItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [loadingText, setLoadingText] = useState("?뚮옯???몃젋??洹쇨굅瑜??뺣━?섎뒗 以?..");
  const loadingTargetRef = useRef(1800);
  const loadingTimerRef = useRef<number | null>(null);

  async function loadHistory() {
    try {
      const res = await fetch(`${API_BASE}/api/localization-guides`);
      const data = await res.json() as { guides?: GuideRecord[]; error?: string };
      if (!res.ok) throw new Error(data.error || "Failed to load localization guide history.");
      setHistory((data.guides || []).map(record => ({ ...record.guide, id: record.id, savedAt: record.created_at })));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  useEffect(() => {
    if (!loading) {
      setProgress(0);
      if (loadingTimerRef.current) {
        window.clearInterval(loadingTimerRef.current);
        loadingTimerRef.current = null;
      }
      return;
    }

    const start = Date.now();
    const target = loadingTargetRef.current;
    loadingTimerRef.current = window.setInterval(() => {
      const elapsed = Date.now() - start;
      const pct = Math.min(97, Math.round((elapsed / target) * 100));
      setProgress(pct);
      const messages = [
        "援??/?λⅤ 議곌굔???뺤씤?섎뒗 以?..",
        "?뚮옯???몃젋??利앷굅瑜?留ㅼ묶?섎뒗 以?..",
        "7媛?媛?대뱶 ?뱀뀡??援ъ꽦?섎뒗 以?..",
      ];
      setLoadingText(messages[Math.min(messages.length - 1, Math.floor(elapsed / 700))]);
    }, 120);

    return () => {
      if (loadingTimerRef.current) {
        window.clearInterval(loadingTimerRef.current);
        loadingTimerRef.current = null;
      }
    };
  }, [loading]);

  function saveHistory(next: GuideResponse) {
    if (next.requiresSelection) return;
    const item: GuideHistoryItem = {
      ...next,
      id: next.guideRecord?.id,
      savedAt: next.guideRecord?.created_at || new Date().toISOString(),
    };
    setHistory(prev => [
      item,
      ...prev.filter(entry => item.id ? entry.id !== item.id : guideDisplayTitle(entry) !== guideDisplayTitle(item) || entry.targetCountry !== item.targetCountry),
    ].slice(0, 5));
  }

  async function removeHistory(item: GuideHistoryItem) {
    if (item.id) {
      const res = await fetch(`${API_BASE}/api/localization-guides/${item.id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { setError(data.error || "Failed to delete localization guide."); return; }
    }
    setHistory(prev => prev.filter(entry => item.id ? entry.id !== item.id : entry.savedAt !== item.savedAt));
  }

  async function run(nextCountry = country) {
    const targetMs = 1200 + Math.floor(Math.random() * 900);
    loadingTargetRef.current = targetMs;
    setLoading(true);
    setError("");
    try {
      const payload = {
        targetCountry: nextCountry || undefined,
        genre: genre || undefined,
        synopsis: synopsis.trim() || undefined,
      };
      const [guide] = await Promise.all([
        postJson<GuideResponse>("/api/guide", payload),
        new Promise(resolve => setTimeout(resolve, targetMs)),
      ]);
      setResult(guide);
      saveHistory(guide);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function selectCountryAndRun(nextCountry: string) {
    setCountry(nextCountry);
    void run(nextCountry);
  }

  const orderedSections = result?.sections
    ? GUIDE_SECTION_ORDER.flatMap(key => result.sections?.[key] ? [[key, result.sections[key]] as const] : [])
    : [];
  const extraSections = result?.sections
    ? Object.entries(result.sections).filter(([key]) => !GUIDE_SECTION_ORDER.includes(key))
    : [];
  const allSections = [...orderedSections, ...extraSections];

  return (
    <section className="guide-grid">
      <div className="glass-card guide-panel">
        <h3>媛?대뱶 ?앹꽦 議곌굔</h3>
        <p className="guide-form-help">
          ?쒕냹?쒖뒪媛 ?놁쑝硫?援??? ?λⅤ 湲곗??쇰줈 ?앹꽦?섍퀬, ?쒕냹?쒖뒪媛 ?덉쑝硫?媛??留욌뒗 援??瑜?異붿쿇????媛?대뱶瑜??앹꽦?⑸땲??
        </p>
        <div className="connector-controls guide-controls">
          <select value={country} onChange={e => setCountry(e.target.value)}>
            <option value="">Country not selected</option>
            {COUNTRY_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <input value={genre} onChange={e => setGenre(e.target.value)} placeholder="?λⅤ ?낅젰 ?? 濡쒗뙋, LitRPG" />
          <textarea
            className="guide-synopsis-input"
            value={synopsis}
            onChange={e => setSynopsis(e.target.value)}
            placeholder="?쒕냹?쒖뒪 ?좏깮 ?낅젰: ?낅젰?섎㈃ 援?? 異붿쿇 ?먮쫫?쇰줈 ?숈옉?⑸땲??"
          />
          <button className="primary" onClick={() => run()} disabled={loading || !genre.trim()}>
            {loading ? "?앹꽦 以?.." : synopsis.trim() ? "援?? 異붿쿇 + 媛?대뱶 ?앹꽦" : "媛?대뱶 ?앹꽦"}
          </button>
        </div>
        {error && <p className="api-error">{error}</p>}

        {result?.requiresSelection && (
          <div className="guide-selection-box">
            <b>Country selection is required.</b>
            <p>{result.message || "?쒕냹?쒖뒪媛 ?놁쑝硫?援??? ?λⅤ瑜?癒쇱? ?좏깮?댁빞 ?⑸땲??"}</p>
            <div className="guide-option-list">
              {(result.availableOptions?.countries || []).map(option => (
                <button key={option.country} type="button" className="secondary" onClick={() => selectCountryAndRun(option.country)}>
                  {option.country}
                </button>
              ))}
            </div>
          </div>
        )}

        {result?.recommendedCountries && result.recommendedCountries.length > 0 && !result.requiresSelection && (
          <div className="guide-recommend-box">
            <b>異붿쿇 援?? ?꾨낫</b>
            {result.recommendedCountries.map(rec => (
              <button key={rec.country} type="button" className={rec.country === result.targetCountry ? "guide-rec active" : "guide-rec"} onClick={() => selectCountryAndRun(rec.country)}>
                <span>{rec.country}</span>
                <small>score {rec.score}</small>
              </button>
            ))}
          </div>
        )}

        <div className="guide-history">
          <div className="guide-history-head">
            <b>媛?대뱶 湲곕줉</b>
            <span>{history.length} saved</span>
          </div>
          {history.length > 0 ? (
            <div className="guide-history-list">
              {history.map((item) => (
                <div key={`${guideDisplayTitle(item)}-${item.savedAt}`} className="guide-history-item">
                  <button type="button" className="guide-history-open" onClick={() => setResult(item)}>
                    <strong>{guideDisplayTitle(item)}</strong>
                    <span>{guideMetaItems(item).slice(0, 2).join(" 쨌 ")}</span>
                    <small>{item.savedAt.slice(0, 16).replace("T", " ")}</small>
                  </button>
                  <button type="button" className="secondary compact guide-history-delete" onClick={() => removeHistory(item)}>
                    ??젣
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="guide-history-empty">?꾩쭅 ??λ맂 媛?대뱶媛 ?놁뒿?덈떎.</div>
          )}
        </div>
      </div>

      <article className="glass-card guide-doc">
        {loading ? (
          <div className="guide-loading">
            <div className="guide-spinner" />
            <b>{loadingText}</b>
            <p>API/model 媛?대뱶 ?묐떟??遺덈윭?ㅺ퀬 ?덉뒿?덈떎.</p>
            <div className="guide-progress">
              <span style={{ width: `${progress}%` }} />
            </div>
          </div>
        ) : result && !result.requiresSelection ? (
          <>
            <div className="guide-doc-top">
              <div>
                <b>{guideDisplayTitle(result)}</b>
                <p>{result.mode === "synopsis_country_recommendation" ? "?쒕냹?쒖뒪 湲곕컲 援?? 異붿쿇 寃곌낵" : "援??/?λⅤ ?좏깮 湲곕컲 媛?대뱶"}</p>
              </div>
              <div className="guide-doc-meta">
                {guideMetaItems(result).map(item => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </div>
            <div className="visual-result-actions guide-download-actions">
              <button type="button" className="secondary compact" onClick={() => downloadGuide(result, "md")}>Download Markdown</button>
              <button type="button" className="secondary compact" onClick={() => downloadGuide(result, "json")}>Download JSON</button>
            </div>

            {allSections.length > 0 && (
              <div className="guide-section-list">
                {allSections.map(([key, section], index) => (
                  <section key={key} className="guide-section">
                    <div className="guide-section-header">
                      <span className="guide-section-num">{index + 1}</span>
                      <span className="guide-section-title">{section.title || key}</span>
                    </div>
                    <ul className="guide-list">
                      {(section.items || []).map((item, itemIndex) => (
                        <li key={`${key}-${itemIndex}`}>{item}</li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            )}

            {result.evidenceUsed && result.evidenceUsed.length > 0 && (
              <section className="guide-evidence-panel">
                <div className="guide-section-header">
                  <span className="guide-section-title">洹쇨굅 ?덊띁?곗뒪</span>
                </div>
                <div className="guide-evidence-list">
                  {result.evidenceUsed.slice(0, 8).map((ev, index) => (
                    <article key={`${ev.platform}-${ev.collection}-${ev.rank}-${index}`} className="guide-evidence-item">
                      <b>{ev.platform} / {ev.collection} 쨌 rank {ev.rank}</b>
                      <span>{ev.title}</span>
                      <small>{ev.genre || "genre unknown"}{ev.reason ? ` 쨌 ${ev.reason}` : ""}</small>
                      {ev.tags && ev.tags.length > 0 && <p>{ev.tags.slice(0, 6).join(" 쨌 ")}</p>}
                    </article>
                  ))}
                </div>
              </section>
            )}

            {result.htmlReport && (
              <details className="guide-html-preview">
                <summary>湲곗〈 HTML 由ы룷??誘몃━蹂닿린</summary>
                <div className="guide-html" dangerouslySetInnerHTML={{ __html: result.htmlReport }} />
              </details>
            )}
          </>
        ) : (
          <div className="assistant-empty guide-empty">
            ?λⅤ留??낅젰?섎㈃ 援?? ?좏깮 ?듭뀡??癒쇱? 諛쏄퀬,<br />?쒕냹?쒖뒪瑜??낅젰?섎㈃ 異붿쿇 援??? 媛?대뱶瑜??④퍡 ?뺤씤?????덉뒿?덈떎.
          </div>
        )}
      </article>
    </section>
  );
}
