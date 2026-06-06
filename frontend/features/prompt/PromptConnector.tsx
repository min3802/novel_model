"use client";

import { useState } from "react";
import { postJson } from "@/features/shared/api";

export function PromptConnector({ kind }: { kind: "cover" | "relation" }) {
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError("");
    try {
      const data = await postJson<{ prompt: string }>(
        kind === "cover" ? "/api/cover-prompt" : "/api/relation-prompt",
        { workTitle: "?묓뭹", extraPrompt: "vertical web novel cover, title-safe composition" }
      );
      setPrompt(data.prompt);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="connector-card">
      <button className="primary" onClick={run} disabled={loading}>
        {loading ? "?앹꽦 以?.." : kind === "cover" ? "?쒖? ?꾨＼?꾪듃 ?앹꽦" : "愿怨꾨룄 ?꾨＼?꾪듃 ?앹꽦"}
      </button>
      {error && <p className="api-error">{error}</p>}
      {prompt && (
        <div className="api-result">
          <b>?앹꽦???꾨＼?꾪듃</b>
          <p>{prompt}</p>
        </div>
      )}
    </div>
  );
}
