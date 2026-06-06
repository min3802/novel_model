"use client";

import { ChangeEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { WorkspaceShell } from "@/components/WorkspaceShell";

const API_BASE = process.env.NEXT_PUBLIC_WLIGHTER_API_BASE || "http://127.0.0.1:8000";

const infoItems = [
  "TXT, DOCX 파일을 지원합니다.",
  "원문 또는 입력한 원문은 바로 번역 검수 창으로 반영됩니다.",
  "저장 후에도 원문 내용을 자유롭게 수정할 수 있습니다.",
  "저장된 원문은 추후 목록에서 확인할 수 있습니다.",
];

export function NewEpisodeFeaturePage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [tab, setTab] = useState<"direct" | "upload">("direct");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [uploadInfo, setUploadInfo] = useState("");



  async function handleFileUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    if (files.length > 5) {
      setError("? ?? ?? 5? ????? ??? ? ????.");
      return;
    }
    setError("");
    const file = files[0];
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".txt") && !lower.endsWith(".docx")) {
      setError("TXT or DOCX files only.");
      return;
    }
    if (lower.endsWith(".docx")) {
      setError("DOCX ?? ??? ?? ?? ?? ?? ????. ??? TXT ?? ?? ??? ??? ???.");
      return;
    }
    const text = await file.text();
    const trimmed = text.trim();
    if (!trimmed) {
      setError("???? ??? ?? ?????.");
      return;
    }
    if (trimmed.length > 8000) {
      setError("?? ??? ?? 8,000??? ??? ? ????.");
      return;
    }
    setContent(trimmed);
    if (!title.trim()) {
      setTitle(file.name.replace(/\.txt$/i, "").slice(0, 30));
    }
    setUploadInfo(`${file.name}?? ${trimmed.length.toLocaleString()}?? ??????.`);
    setTab("direct");
  }

  async function handleSave(goToTranslate: boolean) {
    if (!title.trim()) { setError("회차 제목을 입력해주세요."); return; }
    if (!content.trim()) { setError("회차 원문을 입력해주세요."); return; }
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/works/${params.id}/episodes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, body: content }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "오류가 발생했습니다.");
      window.dispatchEvent(new Event("works:changed"));
      if (goToTranslate) {
        sessionStorage.setItem("episode_text", content);
        router.push("/workspace/translate");
      } else {
        router.push(`/works/${params.id}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
    }
  }

  return (
    <WorkspaceShell active="/dashboard" showWorkCard={false}>
      <nav className="breadcrumb">
        <Link href="/dashboard">내 작품</Link>
        <span>›</span>
        <Link href={`/works/${params.id}`}>작품</Link>
        <span>›</span>
        <span>새 회차 추가</span>
      </nav>

      <h1 className="upload-title">회차 등록 / 원문 업로드</h1>
      <p className="upload-subtitle">원문을 직접 입력하거나 파일을 업로드하면, 번역/검수 단계로 바로 이동할 수 있습니다.</p>

      <div className="upload-grid">
        <div>
          <div className="upload-tabs">
            <button className={tab === "direct" ? "active" : ""} onClick={() => setTab("direct")}>직접 입력</button>
            <button className={tab === "upload" ? "active" : ""} onClick={() => setTab("upload")}>파일 업로드</button>
          </div>

          <div className="upload-form">
            {tab === "direct" && (
              <>
                <div className="form-field">
                  <label className="form-label">회차 제목</label>
                  <input className="form-input" placeholder="예) 눈 내리는 거리" value={title} onChange={e => setTitle(e.target.value)} />
                  <p className="form-helper">독자가 한눈에 이해할 수 있는 제목을 입력해주세요.</p>
                </div>
                <div className="form-field">
                  <label className="form-label">회차 원문</label>
                  <textarea className="form-textarea" placeholder="회차의 전체 원문을 입력해주세요." value={content} onChange={e => setContent(e.target.value)} />
                  <p className="char-count">{content.length.toLocaleString()} 자</p>
                </div>
              </>
            )}
            {tab === "upload" && (
              <div className="file-drop-area">
                <p>Upload TXT files to fill the episode body. DOCX extraction is listed but not connected yet.</p>
                <label className="secondary" style={{ display: "inline-flex", cursor: "pointer" }}>
                  Select file
                  <input
                    type="file"
                    accept=".txt,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    multiple
                    style={{ display: "none" }}
                    onChange={handleFileUpload}
                  />
                </label>
                {uploadInfo && <p className="form-helper">{uploadInfo}</p>}
              </div>
            )}
            {error && <p className="api-error">{error}</p>}
          </div>

          <div className="upload-action-bar">
            <Link href={`/works/${params.id}`} className="secondary btn-cancel">취소</Link>
            <button className="secondary" onClick={() => handleSave(false)} disabled={loading}>임시 저장</button>
            <button className="primary" onClick={() => handleSave(true)} disabled={loading}>
              {loading ? "저장 중..." : "저장 후 번역/검수로 이동 →"}
            </button>
          </div>
        </div>

        <aside className="info-sidebar glass-card">
          <h4 className="info-title">입력 안내</h4>
          <ul className="info-items">
            {infoItems.map(item => <li className="info-item" key={item}>{item}</li>)}
          </ul>
          <div className="goto-card">
            <div className="goto-icon">✦</div>
            <div>
              <b>저장 후 이동</b>
              <p>저장 후 번역/검수 workspace로 바로 이동하여 번역 및 검수를 시작할 수 있습니다.</p>
            </div>
          </div>
        </aside>
      </div>
    </WorkspaceShell>
  );
}
