"use client";

import { useEffect, useRef, useState } from "react";
import { WorkspaceShell, PageTitle } from "@/components/WorkspaceShell";
import {
  getBlockedMessage,
  getTranslationDisplayState,
  type TranslationResponseLike,
} from "@/features/translate/translationDisplay";

const API_BASE = process.env.NEXT_PUBLIC_WLIGHTER_API_BASE || "http://127.0.0.1:8000";
const TRANSLATE_STATE_KEY = "translate_workspace_state";

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
  workflow?: Record<string, unknown>;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  proposedTranslation?: string;
  changeSummary?: string;
  needsUserConfirmation?: boolean;
};

type ChatReply = {
  answer: string;
  proposedTranslation: string;
  changeSummary: string;
  needsUserConfirmation: boolean;
};

type SavedTranslateState = {
  country: string;
  sourceText: string;
  result: TranslateResult | null;
  chatMessages: ChatMessage[];
  tab: Tab;
  savedAt: string;
};

type Tab = "trans" | "source" | "report";

function renderReviewSummary(summary: string) {
  const sections = summary
    .split(/\n\s*\n/)
    .map(part => part.trim())
    .filter(Boolean);

  if (sections.length === 0) return null;

  return (
    <div className="report-summary">
      {sections.map((section, idx) => {
        const [first, ...rest] = section.split("\n");
        return (
          <section key={`${first}-${idx}`}>
            <h4>{first}</h4>
            <p>{rest.join("\n")}</p>
          </section>
        );
      })}
    </div>
  );
}

function renderTranslationStateCard(result: TranslationResponseLike | null, onRetry?: () => void) {
  const state = getTranslationDisplayState(result);
  if (state === "blocked") {
    const blockedMessage = getBlockedMessage(result);
    return (
      <div className="blocked-card">
        <h4>번역 검증 실패</h4>
        <p>{blockedMessage}</p>
        <button className="secondary compact" type="button" onClick={onRetry}>
          다시 시도
        </button>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="api-error" style={{ margin: 0 }}>
        번역 결과를 확인할 수 없습니다.
      </div>
    );
  }

  if (state === "qa_warning") {
    return (
      <div className="qa-warning-card">
        <h4>QA 경고</h4>
        <p>번역은 표시되지만 검토가 필요한 항목이 있습니다.</p>
      </div>
    );
  }

  return null;
}

export function TranslateWorkspace() {
  const [country, setCountry] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [sourceDraft, setSourceDraft] = useState("");
  const [sourceEditorOpen, setSourceEditorOpen] = useState(false);
  const [result, setResult] = useState<TranslateResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("source");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const loadedRef = useRef(false);
  const displayState = getTranslationDisplayState(result);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(TRANSLATE_STATE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as Partial<SavedTranslateState>;
        if (typeof saved.country === "string") setCountry(saved.country);
        if (typeof saved.sourceText === "string") setSourceText(saved.sourceText);
        if (saved.result) setResult(saved.result);
        if (Array.isArray(saved.chatMessages)) setChatMessages(saved.chatMessages as ChatMessage[]);
        if (saved.tab === "source" || saved.tab === "trans" || saved.tab === "report") setTab(saved.tab);
      }
    } catch {
      // ignore storage errors
    }

    const stored = sessionStorage.getItem("episode_text");
    const openEditor = sessionStorage.getItem("open_source_editor");
    if (stored) {
      setSourceText(stored);
      setSourceDraft(stored);
      sessionStorage.removeItem("episode_text");
    }
    if (openEditor === "true") {
      setSourceEditorOpen(true);
      sessionStorage.removeItem("open_source_editor");
    }

    loadedRef.current = true;
  }, []);

  useEffect(() => {
    setSourceDraft(sourceText);
  }, [sourceText]);

  useEffect(() => {
    if (!loadedRef.current) return;
    const snapshot: SavedTranslateState = {
      country,
      sourceText,
      result,
      chatMessages,
      tab,
      savedAt: new Date().toISOString(),
    };
    try {
      localStorage.setItem(TRANSLATE_STATE_KEY, JSON.stringify(snapshot));
    } catch {
      // ignore storage errors
    }
  }, [country, sourceText, result, chatMessages, tab]);

  async function run() {
    if (!country) {
      setError("국가를 선택해주세요.");
      return;
    }
    if (!sourceText.trim()) {
      setError("원문을 입력해주세요.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targetCountry: country, sourceText }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "번역 실패");
      setResult(data);
      setChatMessages([]);
      setChatInput("");
      setChatError("");
      setTab("trans");
      setSourceEditorOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function openSourceEditor() {
    setSourceDraft(sourceText);
    setSourceEditorOpen(true);
  }

  function applySourceEdit() {
    const next = sourceDraft.trim();
    if (!next) {
      setError("원문을 비워둘 수 없습니다.");
      return;
    }
    setSourceText(next);
    setResult(null);
    setChatMessages([]);
    setChatInput("");
    setChatError("");
    setError("");
    setTab("source");
    setSourceEditorOpen(false);
  }

  async function sendChat() {
    const question = chatInput.trim();
    if (!result) {
      setChatError("먼저 번역을 실행해주세요.");
      return;
    }
    if (!question) {
      setChatError("질문을 입력해주세요.");
      return;
    }

    const nextMessages: ChatMessage[] = [...chatMessages, { role: "user", content: question }];
    setChatMessages(nextMessages);
    setChatInput("");
    setChatError("");
    setChatLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/inspect-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          targetCountry: country,
          question,
          sourceText,
          currentTranslation: result.finalTranslation,
          reviewSummary: result.reviewSummary,
          workflow: result.workflow,
          chatHistory: nextMessages.map(m => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "챗봇 응답 실패");
      const reply = data as ChatReply;
      setChatMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: reply.changeSummary?.trim() ? reply.changeSummary : reply.answer,
          proposedTranslation: reply.proposedTranslation,
          changeSummary: reply.changeSummary,
          needsUserConfirmation: reply.needsUserConfirmation,
        },
      ]);
    } catch (e) {
      setChatError(e instanceof Error ? e.message : String(e));
      setChatMessages(nextMessages);
    } finally {
      setChatLoading(false);
    }
  }

  function applyProposedTranslation(text: string) {
    if (!result || !text.trim()) return;
    setResult({ ...result, finalTranslation: text });
    setTab("trans");
    setChatMessages(prev => [
      ...prev,
      { role: "assistant", content: "제안한 번역을 현재 번역본에 반영했습니다." },
    ]);
  }

  return (
    <WorkspaceShell active="/workspace/translate">
      <PageTitle
        eyebrow="Workspace · Inspection Assistant"
        title="번역/검수"
        text="원문을 입력하고 국가를 선택한 뒤 번역을 실행하세요. 원문은 왼쪽 버튼으로 수정할 수 있습니다."
      />

      <section className="workspace-grid">
        <div>
          <section className="control-bar translate-control-bar">
            <div className="field">
              <label>대상 국가</label>
              <select
                className="select-like"
                value={country}
                onChange={e => setCountry(e.target.value)}
                style={{ height: "46px", fontWeight: 850, color: "#4d425f" }}
              >
                <option value="">국가 선택</option>
                <option>일본</option>
                <option>미국</option>
                <option>중국</option>
                <option>태국</option>
              </select>
            </div>
            <div className="field">
              <label>원문 글자수</label>
              <div className="input-like">{sourceText.length > 0 ? `${sourceText.length.toLocaleString()}자` : "—"}</div>
            </div>
            <div className="field">
              <label>번역 상태</label>
              <div className="input-like">{result ? "번역 완료" : "대기 중"}</div>
            </div>
            <button className="secondary" onClick={openSourceEditor} disabled={loading || chatLoading}>
              원문 수정
            </button>
            <button className="primary" onClick={run} disabled={loading}>
              {loading ? "번역 중..." : "검수 + 번역 실행"}
            </button>
          </section>

          {error && <p className="api-error" style={{ margin: ".75rem 0 -.15rem" }}>{error}</p>}

          <div className="glass-card">
            <div className="doc-tabs">
              <span className={tab === "trans" ? "active" : ""} onClick={() => setTab("trans")} style={{ cursor: "pointer" }}>
                번역본
              </span>
              <span className={tab === "source" ? "active" : ""} onClick={() => setTab("source")} style={{ cursor: "pointer" }}>
                원문
              </span>
              <span className={tab === "report" ? "active" : ""} onClick={() => setTab("report")} style={{ cursor: "pointer" }}>
                번역 리포트
              </span>
            </div>

            {tab === "source" && (
              <div className="document-area" style={{ whiteSpace: "pre-wrap" }}>
                {sourceText || <span style={{ color: "#b0a8c0" }}>원문이 없습니다.</span>}
              </div>
            )}

            {tab === "trans" && (
              <div className="document-area" style={{ whiteSpace: "pre-wrap" }}>
                {renderTranslationStateCard(result, () => void run())}
                {displayState !== "blocked" && result && result.finalTranslation.trim() && (
                  <div className="translation-output" style={{ marginTop: "0.75rem" }}>
                    {result.finalTranslation}
                  </div>
                )}
                {displayState === "result" && result && !result.finalTranslation.trim() && (
                  <span style={{ color: "#b0a8c0" }}>?? ??? ????.</span>
                )}
                {!result && <span style={{ color: "#b0a8c0" }}>??? ???? ??? ?? ?????.</span>}
              </div>
            )}

            {tab === "report" && (
              <div className="document-area report-area">
                {result?.reviewSummary
                  ? renderReviewSummary(result.reviewSummary)
                  : <span style={{ color: "#b0a8c0" }}>번역 실행 후 검수 리포트가 표시됩니다.</span>}
              </div>
            )}
          </div>

        </div>

        <aside className="glass-card assistant-panel">
          <div className="assistant-head">
            <b><span className="assistant-orb">✦</span>Inspection Assistant</b>
            <small>대화 기록</small>
          </div>
          <div className="chat-thread">
            {!result && (
              <div className="assistant-empty">
                먼저 번역을 실행한 뒤, 번역 결과나 검수 기준에 대해 질문해보세요.
              </div>
            )}
            {result && chatMessages.length === 0 && (
              <div className="assistant-empty">
                번역 결과를 바탕으로 질문하거나, 수정 요청을 입력해보세요.
              </div>
            )}
            {chatMessages.map((msg, idx) => (
              <div className={`chat-bubble ${msg.role === "user" ? "user" : "ai"}`} key={`${msg.role}-${idx}`}>
                <p>{msg.content}</p>
                {msg.proposedTranslation && msg.proposedTranslation.trim() && msg.proposedTranslation !== result?.finalTranslation && (
                  <div className="proposed-translation">
                    <b>수정 제안</b>
                    <pre>{msg.proposedTranslation}</pre>
                    <button className="secondary" onClick={() => applyProposedTranslation(msg.proposedTranslation || "")}>
                      제안을 번역본에 반영
                    </button>
                  </div>
                )}
              </div>
            ))}
            {chatLoading && <div className="chat-bubble ai"><p>답변을 생성하는 중입니다...</p></div>}
          </div>

          {chatError && <p className="api-error chat-error">{chatError}</p>}

          <div className="chat-compose">
            <textarea
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (!chatLoading) void sendChat();
                }
              }}
              disabled={!result || chatLoading}
              placeholder={result ? "번역 결과나 표현에 대해 질문해보세요" : "번역을 먼저 실행해야 합니다"}
            />
            <button className="primary chat-send" onClick={sendChat} disabled={!result || chatLoading}>
              →
            </button>
          </div>
        </aside>
      </section>

      {sourceEditorOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setSourceEditorOpen(false)}>
          <div className="modal-card glass-card" role="dialog" aria-modal="true" aria-label="원문 수정" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="section-heading">원문 수정</h3>
                <p className="modal-subtitle">원문을 수정한 뒤 다시 번역을 실행하세요.</p>
              </div>
              <button className="secondary compact" onClick={() => setSourceEditorOpen(false)}>닫기</button>
            </div>
            <textarea
              className="form-textarea"
              style={{ minHeight: "320px", width: "100%" }}
              value={sourceDraft}
              onChange={e => setSourceDraft(e.target.value)}
            />
            <div className="modal-actions">
              <button className="secondary" onClick={() => setSourceEditorOpen(false)}>취소</button>
              <button className="primary" onClick={applySourceEdit}>적용</button>
            </div>
          </div>
        </div>
      )}
    </WorkspaceShell>
  );
}
