"use client";

import { useEffect, useState } from "react";
import { sampleTranslation } from "@/components/data";
import { postJson } from "@/features/shared/api";

type ConsistencyIssue = { type: string; source: string; expected: string; actual: string; severity: string; message: string };
type ConsistencyCheck = { status: string; checked?: { source: string; expected?: string; allowed?: string[]; found?: string; policy?: string; type?: string; status?: string }[]; skipped?: { source: string; policy: string; reason: string }[]; issues?: ConsistencyIssue[]; summary?: string };
type TranslateWorkflow = { consistency?: ConsistencyCheck };
type TranslateResult = { finalTranslation: string; reviewSummary: string; retrievalCount: number; workflow?: TranslateWorkflow };

export function TranslateConnector() {
  const [country, setCountry] = useState("");
  const [sourceText, setSourceText] = useState(sampleTranslation);
  const [result, setResult] = useState<TranslateResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Load episode text saved from the episode form
  useEffect(() => {
    const stored = sessionStorage.getItem("episode_text");
    if (stored) {
      setSourceText(stored);
      sessionStorage.removeItem("episode_text");
    }
  }, []);

  async function run() {
    setLoading(true);
    setError("");
    try {
      setResult(await postJson<TranslateResult>("/api/translate", { targetCountry: country, sourceText }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="connector-card">
      <div className="connector-controls">
        <select value={country} onChange={e => setCountry(e.target.value)}>
          <option value="">?? ??</option>
          <option>??</option><option>??</option><option>??</option><option>??</option>
        </select>
        <button className="primary" onClick={run} disabled={loading || !country}>
          {loading ? "?? ?..." : "AI ?? ??"}
        </button>
      </div>
      <textarea value={sourceText} onChange={e => setSourceText(e.target.value)} placeholder="??? ??? ??? ?????." />
      {error && <p className="api-error">{error}</p>}
      {result && (
        <div className="api-result">
          <b>Translation Result</b>
          <p>{result.finalTranslation}</p>
          <small>RAG {result.retrievalCount} references ? {result.reviewSummary || "No review summary"}</small>
          {result.workflow?.consistency && (
            <div className="consistency-panel">
              <b>Terminology consistency: {result.workflow.consistency.status.toUpperCase()}</b>
              <p>{result.workflow.consistency.summary}</p>
              {(result.workflow.consistency.checked || []).length > 0 && (
                <ul>
                  {(result.workflow.consistency.checked || []).slice(0, 8).map((row, index) => (
                    <li key={`${row.source}-${index}`}>
                      <strong>{row.source}</strong> ? {row.expected || "transliterate consistently"}
                      {row.found ? ` ? found: ${row.found}` : ""}
                      {row.status ? ` ? ${row.status}` : ""}
                    </li>
                  ))}
                </ul>
              )}
              {(result.workflow.consistency.issues || []).length > 0 && (
                <div className="api-error">
                  {(result.workflow.consistency.issues || []).map((issue, index) => (
                    <p key={`${issue.source}-${index}`}>{issue.severity}: {issue.message}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
