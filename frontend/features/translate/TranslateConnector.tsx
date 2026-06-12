"use client";

import { useEffect, useState } from "react";
import { sampleTranslation } from "@/components/data";
import { postJson } from "@/features/shared/api";
import { getBlockedMessage, getTranslationDisplayState, type TranslationResponseLike } from "@/features/translate/translationDisplay";

type ConsistencyIssue = { type: string; source: string; expected: string; actual: string; severity: string; message: string };
type ConsistencyCheck = { status: string; checked?: { source: string; expected?: string; allowed?: string[]; found?: string; policy?: string; type?: string; status?: string }[]; skipped?: { source: string; policy: string; reason: string }[]; issues?: ConsistencyIssue[]; summary?: string };
type TranslateWorkflow = { consistency?: ConsistencyCheck };
type TranslateResult = {
  finalTranslation: string;
  reviewSummary: string;
  retrievalCount: number;
  deliveryStatus?: "deliverable" | "blocked_translation_safety" | string;
  userVisibleErrorCode?: "translation_safety_failed" | string | null;
  message?: string;
  metadata?: Record<string, unknown>;
  qaReport?: unknown;
  userVisibleQaReport?: Record<string, unknown>;
  workflow?: TranslateWorkflow;
};

function renderTranslationStateCard(result: TranslationResponseLike | null, onRetry?: () => void) {
  const state = getTranslationDisplayState(result);
  if (state === "blocked") {
    return (
      <div className="blocked-card" style={{ marginBottom: "0.75rem" }}>
        <h4>번역 검증 실패</h4>
        <p>{getBlockedMessage(result)}</p>
        <button className="secondary compact" type="button" onClick={onRetry}>다시 시도</button>
      </div>
    );
  }
  if (state === "qa_warning") {
    return (
      <div className="qa-warning-card" style={{ marginBottom: "0.75rem" }}>
        <h4>QA 경고</h4>
        <p>번역은 표시되지만 검토가 필요한 항목이 있습니다. QA 카드로 확인하세요.</p>
      </div>
    );
  }
  if (state === "error") {
    return (
      <div className="api-error" style={{ marginBottom: "0.75rem" }}>
        번역 결과를 확인할 수 없습니다.
      </div>
    );
  }
  return null;
}

export function TranslateConnector() {
  const [country, setCountry] = useState("");
  const [sourceText, setSourceText] = useState(sampleTranslation);
  const [result, setResult] = useState<TranslateResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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

  const displayState = getTranslationDisplayState(result);

  return (
    <div className="connector-card">
      <div className="connector-controls">
        <select value={country} onChange={e => setCountry(e.target.value)}>
          <option value="">언어 선택</option>
          <option>일본</option><option>미국</option><option>중국</option><option>태국</option>
        </select>
        <button className="primary" onClick={run} disabled={loading || !country}>
          {loading ? "번역 중..." : "AI 번역 실행"}
        </button>
      </div>
      <textarea value={sourceText} onChange={e => setSourceText(e.target.value)} placeholder="원문을 입력하세요." />
      {error && <p className="api-error">{error}</p>}
      {result && (
        <div className="api-result">
          <b>Translation Result</b>
          {renderTranslationStateCard(result, () => void run())}
          {displayState !== "blocked" && result.finalTranslation.trim() && <p>{result.finalTranslation}</p>}
          {displayState === "result" && !result.finalTranslation.trim() && (
            <p style={{ color: "#b0a8c0" }}>번역 결과가 없습니다. 결과를 다시 확인하세요.</p>
          )}
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
