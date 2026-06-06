"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { WorkspaceShell } from "@/components/WorkspaceShell";

const API_BASE = process.env.NEXT_PUBLIC_WLIGHTER_API_BASE || "http://127.0.0.1:8000";

type Work = {
  id: number;
  title: string;
  genre: string;
  pen_name: string;
  desc: string;
  status: string;
  created_at: string;
  episode_count?: number;
};

type DashboardSummary = {
  workCount: number;
  episodeCount: number;
  guideCount: number;
};

const COVER_GRADIENTS = [
  "linear-gradient(135deg,#2b2142,#7c3aed)",
  "linear-gradient(135deg,#1a1a4e,#4f46e5)",
  "linear-gradient(135deg,#3b1f6e,#9333ea)",
  "linear-gradient(135deg,#1e3a5f,#2563eb)",
  "linear-gradient(135deg,#4a1942,#db2777)",
  "linear-gradient(135deg,#1f4a3b,#059669)",
];

export function DashboardFeaturePage() {
  const [works, setWorks] = useState<Work[]>([]);
  const [summary, setSummary] = useState<DashboardSummary>({ workCount: 0, episodeCount: 0, guideCount: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/works`).then(r => r.json()),
      fetch(`${API_BASE}/api/dashboard-summary`).then(r => r.json()).catch(() => null),
    ])
      .then(([worksData, summaryData]) => {
        const nextWorks = worksData.works || [];
        setWorks(nextWorks);
        setSummary(summaryData || {
          workCount: nextWorks.length,
          episodeCount: nextWorks.reduce((sum: number, work: Work) => sum + (work.episode_count || 0), 0),
          guideCount: 0,
        });
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <WorkspaceShell active="/dashboard" showWorkCard={false}>
      <div className="dashboard-hero glass-card">
        <div className="hero-greeting">
          <h2>안녕하세요 👋</h2>
          <p>이야기의 시작부터 글로벌 현지화까지,<br />모든 과정을 w.LIGHTER 하나의 공간에서 관리하세요.</p>
          <div className="hero-btn-row">
            <Link className="primary" href="/works/new">＋ 새 작품 만들기</Link>
            <button className="secondary">가져오기</button>
          </div>
        </div>
        <div className="hero-stat-group">
          {[
            { label: "작품", sub: "전체 작품 수", val: summary.workCount || works.length },
            { label: "회차", sub: "전체 회차 수", val: summary.episodeCount },
            { label: "가이드", sub: "저장된 가이드 수", val: summary.guideCount },
          ].map(({ label, sub, val }) => (
            <div className="hero-stat" key={label}>
              <span className="stat-label">{label}</span>
              <b className="stat-val">{val}</b>
              <span className="stat-sub">{sub}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="dashboard-body">
        <section className="works-section">
          <h3 className="section-heading">내 작품</h3>
          <div className="works-filter-bar">
            <div className="search-wrap">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input placeholder="작품 제목 검색" readOnly />
            </div>
            <select className="filter-select"><option>장르 전체</option></select>
            <select className="filter-select"><option>상태 전체</option></select>
            <select className="filter-select"><option>최근 수정순</option></select>
          </div>

          {loading ? (
            <div className="works-empty"><p>불러오는 중...</p></div>
          ) : works.length === 0 ? (
            <div className="works-empty">
              <p>아직 등록된 작품이 없습니다.</p>
              <Link className="primary" href="/works/new">＋ 첫 작품 만들기</Link>
            </div>
          ) : (
            <div className="work-cards-grid">
              {works.map((work, i) => (
                <Link href={`/works/${work.id}`} className="work-card" key={work.id}>
                  <div className="work-cover" style={{ background: COVER_GRADIENTS[i % COVER_GRADIENTS.length] }} />
                  <div className="work-card-body">
                    <div className="work-title-row">
                      <b>{work.title}</b>
                      <span className="work-badge badge-active">{work.status}</span>
                    </div>
                    <div className="work-meta">{work.genre} · {work.pen_name}</div>
                    <div className="work-counts">
                      <span className="work-count-pill">회차 {work.episode_count || 0}</span>
                    </div>
                    <div className="work-meta">{work.created_at} 등록</div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>

        <aside className="activity-sidebar glass-card">
          <div className="activity-head">
            <b>최근 작업</b>
            <span className="view-all">전체 보기 ›</span>
          </div>
          <div className="activity-empty">최근 작업 내역이 없습니다.</div>
          <button className="activity-more">작업 내역 더 보기</button>
        </aside>
      </div>
    </WorkspaceShell>
  );
}
