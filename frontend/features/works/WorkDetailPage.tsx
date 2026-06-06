"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { WorkspaceShell } from "@/components/WorkspaceShell";

const API_BASE = process.env.NEXT_PUBLIC_WLIGHTER_API_BASE || "http://127.0.0.1:8000";
const GENRES = ["근대 문학", "근대 드라마", "현대 로맨스", "현대 드라마", "현대 청춘", "현대 미스터리", "SF", "로맨스", "판타지"];

type Work = {
  id: number;
  title: string;
  genre: string;
  pen_name: string;
  desc: string;
  status: string;
  created_at: string;
};

type Episode = {
  id: number;
  work_id: number;
  title: string;
  body: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export function WorkDetailFeaturePage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [work, setWork] = useState<Work | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [error, setError] = useState("");
  const [episodeSort, setEpisodeSort] = useState<"desc" | "asc">("desc");
  const [episodeEdit, setEpisodeEdit] = useState<Episode | null>(null);
  const [episodeEditTitle, setEpisodeEditTitle] = useState("");
  const [episodeEditBody, setEpisodeEditBody] = useState("");
  const [episodeSaving, setEpisodeSaving] = useState(false);

  const [title, setTitle] = useState("");
  const [penName, setPenName] = useState("");
  const [genre, setGenre] = useState("");
  const [desc, setDesc] = useState("");

  const episodeCount = useMemo(() => episodes.length, [episodes]);
  const sortedEpisodes = useMemo(() => {
    return [...episodes].sort((a, b) => (episodeSort === "asc" ? a.id - b.id : b.id - a.id));
  }, [episodes, episodeSort]);
  const episodeNumberMap = useMemo(() => {
    const ordered = [...episodes].sort((a, b) => a.id - b.id);
    return new Map(ordered.map((ep, index) => [ep.id, index + 1]));
  }, [episodes]);
  const translatedCount = useMemo(
    () => episodes.filter(e => e.status === "번역 완료").length,
    [episodes]
  );

  function refreshAfterWorkChange() {
    window.dispatchEvent(new Event("works:changed"));
  }

  function goToTranslate(ep: Episode) {
    sessionStorage.setItem("episode_text", ep.body);
    sessionStorage.removeItem("open_source_editor");
    router.push("/workspace/translate");
  }

  function openEpisodeEdit(ep: Episode) {
    setEpisodeEdit(ep);
    setEpisodeEditTitle(ep.title);
    setEpisodeEditBody(ep.body);
    setError("");
  }

  async function saveEpisodeEdit() {
    if (!episodeEdit) return;
    if (!episodeEditTitle.trim()) { setError("Episode title is required."); return; }
    if (episodeEditTitle.trim().length > 30) { setError("Episode title must be 30 characters or fewer."); return; }
    if (!episodeEditBody.trim()) { setError("Episode body is required."); return; }
    if (episodeEditBody.trim().length > 8000) { setError("Episode body must be 8,000 characters or fewer."); return; }
    setEpisodeSaving(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/works/${params.id}/episodes/${episodeEdit.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: episodeEditTitle, body: episodeEditBody }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to update episode.");
      setEpisodes(prev => prev.map(ep => ep.id === data.id ? data : ep));
      setEpisodeEdit(null);
      refreshAfterWorkChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setEpisodeSaving(false);
    }
  }

  async function deleteEpisode(ep: Episode) {
    if (!window.confirm(`Delete episode "${ep.title}"? Related translation/chat records will also be removed.`)) return;
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/works/${params.id}/episodes/${ep.id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to delete episode.");
      setEpisodes(prev => prev.filter(row => row.id !== ep.id));
      refreshAfterWorkChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    Promise.all([
      fetch(`${API_BASE}/api/works/${params.id}`).then(r => r.json()),
      fetch(`${API_BASE}/api/works/${params.id}/episodes`).then(r => r.json()),
    ])
      .then(([wd, ed]) => {
        if (ignore) return;
        const nextWork = wd.work || null;
        setWork(nextWork);
        setEpisodes(ed.episodes || []);
      setTitle(nextWork?.title || "");
      setPenName(nextWork?.pen_name || "");
      setGenre(nextWork?.genre || "");
      setDesc(nextWork?.desc || "");
      setError("");
      setEditOpen(false);
      })
      .catch((e) => {
        if (!ignore) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [params.id]);

  async function saveWork() {
    if (!title.trim()) {
      setError("작품 제목을 입력해주세요.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/works/${params.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, pen_name: penName, genre, desc }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "작품 수정에 실패했습니다.");
      setWork(data);
      setTitle(data.title || "");
      setPenName(data.pen_name || "");
      setGenre(data.genre || "");
      setDesc(data.desc || "");
      setEditOpen(false);
      refreshAfterWorkChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function deleteWork() {
    const confirmed = window.confirm("이 작품을 삭제할까요? 회차도 함께 삭제됩니다.");
    if (!confirmed) return;
    setDeleting(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/works/${params.id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "작품 삭제에 실패했습니다.");
      refreshAfterWorkChange();
      router.push("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <WorkspaceShell active="/dashboard" showWorkCard={false}>
        <div className="assistant-empty">불러오는 중...</div>
      </WorkspaceShell>
    );
  }

  return (
    <WorkspaceShell active="/dashboard" showWorkCard={false}>
      <nav className="breadcrumb">
        <Link href="/dashboard">내 작품</Link>
        <span>›</span>
        <span>{work?.title || "작품 상세"}</span>
      </nav>

      <div className="work-info-card glass-card">
        <div className="work-cover-img" />
        <div className="work-info-body">
          <div className="work-info-header">
            <h2>{work?.title || "작품 없음"}</h2>
            <span className="work-badge badge-active">{work?.status || "상태 없음"}</span>
          </div>
          <div className="work-info-meta">
            <span>장르 {work?.genre || "미선택"}</span>
            <span>필명 {work?.pen_name || "미설정"}</span>
            <span>등록일 {work?.created_at || "-"}</span>
          </div>
          <p className="work-description">{work?.desc || "작품 소개가 없습니다."}</p>
          <div className="work-info-actions">
            <Link className="primary" href={`/works/${params.id}/episodes/new`}>새 회차 추가</Link>
            <button className="secondary" onClick={() => setEditOpen(true)}>
              작품 정보 수정
            </button>
            <button className="secondary" onClick={deleteWork} disabled={deleting} style={{ color: "#c026d3" }}>
              {deleting ? "삭제 중..." : "작품 삭제"}
            </button>
          </div>
        </div>
        <div className="work-stat-group">
          <div className="work-stat-card">
            <span className="work-stat-label">전체 회차</span>
            <b className="work-stat-val">{episodeCount}</b>
            <span className="work-stat-sub">등록된 회차 수</span>
          </div>
          <div className="work-stat-card">
            <span className="work-stat-label">번역 완료</span>
            <b className="work-stat-val">{translatedCount}</b>
            <span className="work-stat-sub">번역이 끝난 회차 수</span>
          </div>
        </div>
      </div>

      {error && <p className="api-error" style={{ marginTop: "1rem" }}>{error}</p>}

      <section className="glass-card" style={{ marginTop: "1rem" }}>
          <div className="episode-header">
            <h3 className="section-heading">회차 목록</h3>
            <div className="episode-header-actions">
              <select
                className="episode-sort-select"
                value={episodeSort}
                onChange={(e) => setEpisodeSort(e.target.value as "desc" | "asc")}
              >
                <option value="desc">최신순</option>
                <option value="asc">오래된 순</option>
              </select>
              <Link href={`/works/${params.id}/episodes/new`} className="primary">새 회차 등록</Link>
            </div>
          </div>
          <table className="episode-table">
            <thead>
              <tr>
                <th>회차</th>
                <th>제목</th>
                <th>상태</th>
                <th>최근 수정</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {episodes.length === 0 ? (
                <tr className="episode-empty-row">
                  <td colSpan={5}>
                    회차가 아직 없습니다.{" "}
                    <Link href={`/works/${params.id}/episodes/new`} style={{ color: "var(--violet)", fontWeight: 900 }}>
                      첫 회차를 추가해보세요
                    </Link>
                  </td>
                </tr>
              ) : (
                sortedEpisodes.map((ep, idx) => (
                  <tr key={ep.id}>
                    <td>{episodeNumberMap.get(ep.id) || idx + 1}화</td>
                    <td>{ep.title}</td>
                    <td><span className="work-badge badge-ready">{ep.status}</span></td>
                    <td>{ep.updated_at}</td>
                    <td>
                      <div className="episode-actions">
                        <button
                          className="ep-action-link"
                          style={{ background: "none", border: "none", cursor: "pointer", padding: 0, font: "inherit" }}
                          onClick={() => goToTranslate(ep)}
                        >
                          번역/검수
                        </button>
                        <span className="ep-divider">|</span>
                        <button
                          className="ep-action-link"
                          style={{ background: "none", border: "none", cursor: "pointer", padding: 0, font: "inherit" }}
                          onClick={() => openEpisodeEdit(ep)}
                        >
                          원문 수정
                        </button>
                        <span className="ep-divider">|</span>
                        <button
                          className="ep-action-link"
                          style={{ background: "none", border: "none", cursor: "pointer", padding: 0, font: "inherit", color: "#be123c" }}
                          onClick={() => deleteEpisode(ep)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
      </section>

      {editOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setEditOpen(false)}>
          <div className="modal-card glass-card" role="dialog" aria-modal="true" aria-label="작품 정보 수정" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="section-heading">작품 정보 수정</h3>
                <p className="modal-subtitle">수정 후 저장하면 작품 정보만 갱신됩니다.</p>
              </div>
              <button className="secondary compact" onClick={() => setEditOpen(false)}>닫기</button>
            </div>
            <div className="upload-form">
              <div className="form-field">
                <label className="form-label">작품 제목 *</label>
                <input className="form-input" value={title} onChange={e => setTitle(e.target.value)} maxLength={80} />
              </div>
              <div className="form-field">
                <label className="form-label">필명</label>
                <input className="form-input" value={penName} onChange={e => setPenName(e.target.value)} />
              </div>
              <div className="form-field">
                <label className="form-label">장르</label>
                <select className="form-input" value={genre} onChange={e => setGenre(e.target.value)}>
                  <option value="">장르 선택</option>
                  {GENRES.map(g => (
                    <option key={g} value={g}>{g}</option>
                  ))}
                </select>
              </div>
              <div className="form-field">
                <label className="form-label">작품 소개</label>
                <textarea
                  className="form-textarea"
                  style={{ minHeight: "140px" }}
                  value={desc}
                  onChange={e => setDesc(e.target.value)}
                />
              </div>
            </div>
            <div className="modal-actions">
              <button className="secondary" onClick={() => setEditOpen(false)}>취소</button>
              <button className="primary" onClick={saveWork} disabled={saving}>
                {saving ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        </div>
      )}

      {episodeEdit && (
        <div className="modal-backdrop" role="presentation" onClick={() => setEpisodeEdit(null)}>
          <div className="modal-card glass-card" role="dialog" aria-modal="true" aria-label="Episode source edit" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="section-heading">?? ?? ??</h3>
                <p className="modal-subtitle">??? ??? ???? ?? ??? ??? ??? ?????.</p>
              </div>
              <button className="secondary compact" onClick={() => setEpisodeEdit(null)}>??</button>
            </div>
            <div className="upload-form">
              <div className="form-field">
                <label className="form-label">Episode title</label>
                <input className="form-input" value={episodeEditTitle} onChange={e => setEpisodeEditTitle(e.target.value)} maxLength={30} />
                <p className="form-helper">{episodeEditTitle.length}/30</p>
              </div>
              <div className="form-field">
                <label className="form-label">Episode body</label>
                <textarea className="form-textarea" value={episodeEditBody} onChange={e => setEpisodeEditBody(e.target.value)} />
                <p className="char-count">{episodeEditBody.length.toLocaleString()} / 8,000</p>
              </div>
            </div>
            <div className="modal-actions">
              <button className="secondary" onClick={() => setEpisodeEdit(null)}>Cancel</button>
              <button className="primary" onClick={saveEpisodeEdit} disabled={episodeSaving}>
                {episodeSaving ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

    </WorkspaceShell>
  );
}
