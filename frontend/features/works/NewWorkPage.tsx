"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { WorkspaceShell } from "@/components/WorkspaceShell";

const API_BASE = process.env.NEXT_PUBLIC_WLIGHTER_API_BASE || "http://127.0.0.1:8000";
const GENRES = ["근대 문학", "현대 소설", "판타지", "SF", "로맨스", "에세이", "기타"];

export function NewWorkFeaturePage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [penName, setPenName] = useState("");
  const [genre, setGenre] = useState("");
  const [desc, setDesc] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    if (!title.trim()) { setError("작품 제목을 입력해주세요."); return; }
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/works`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, pen_name: penName, genre, desc }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "오류가 발생했습니다.");
      window.dispatchEvent(new Event("works:changed"));
      router.push(`/works/${data.id}`);
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
        <span>새 작품 등록</span>
      </nav>
      <h1 className="upload-title">새 작품 등록</h1>
      <p className="upload-subtitle">작품 제목과 장르를 등록하면 회차를 추가하고 번역을 시작할 수 있습니다.</p>

      <div className="upload-grid">
        <div>
          <div className="upload-form">
            <div className="form-field">
              <label className="form-label">작품 제목 *</label>
              <input className="form-input" placeholder="작품 제목을 입력하세요 (최대 50자)" value={title} onChange={e => setTitle(e.target.value)} maxLength={50} />
            </div>
            <div className="form-field">
              <label className="form-label">필명</label>
              <input className="form-input" placeholder="필명을 입력하세요" value={penName} onChange={e => setPenName(e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-label">장르</label>
              <select className="form-input" value={genre} onChange={e => setGenre(e.target.value)}>
                <option value="">장르 선택</option>
                {GENRES.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label className="form-label">작품 설명</label>
              <textarea className="form-textarea" style={{ minHeight: "120px" }} placeholder="작품 소개 또는 현지화 참고 메모를 입력하세요." value={desc} onChange={e => setDesc(e.target.value)} />
            </div>
            {error && <p className="api-error">{error}</p>}
          </div>
          <div className="upload-action-bar">
            <Link href="/dashboard" className="secondary btn-cancel">취소</Link>
            <button className="primary" onClick={handleSubmit} disabled={loading}>
              {loading ? "저장 중..." : "작품 저장"}
            </button>
          </div>
        </div>

        <aside className="info-sidebar glass-card">
          <h4 className="info-title">등록 안내</h4>
          <ul className="info-items">
            <li className="info-item">작품 제목은 필수 입력 항목입니다.</li>
            <li className="info-item">저장 후 회차를 추가할 수 있습니다.</li>
            <li className="info-item">작품 정보는 언제든 수정할 수 있습니다.</li>
            <li className="info-item">회차를 등록하면 번역/검수를 바로 시작할 수 있습니다.</li>
          </ul>
        </aside>
      </div>
    </WorkspaceShell>
  );
}
