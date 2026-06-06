"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { navItems } from "./data";

const API_BASE = process.env.NEXT_PUBLIC_WLIGHTER_API_BASE || "http://127.0.0.1:8000";

type SidebarWork = {
  id: number;
  title: string;
  genre?: string;
  pen_name?: string;
  status?: string;
  created_at?: string;
  recent_episode_at?: string;
  episode_count?: number;
};

export function WorkspaceShell({
  children,
  active,
  showWorkCard = true,
}: {
  children: React.ReactNode;
  active: string;
  showWorkCard?: boolean;
}) {
  const [recentWork, setRecentWork] = useState<SidebarWork | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!showWorkCard) return;
    let ignore = false;
    const load = () => {
      fetch(`${API_BASE}/api/works`)
        .then(r => r.json())
        .then(data => {
          if (ignore) return;
          const rows = (data.works || []) as SidebarWork[];
          const sorted = [...rows].sort((a, b) => {
            const aKey = a.recent_episode_at || a.created_at || "";
            const bKey = b.recent_episode_at || b.created_at || "";
            return bKey.localeCompare(aKey) || b.id - a.id;
          });
          setRecentWork(sorted[0] || null);
        })
        .catch(() => {
          if (!ignore) setRecentWork(null);
        })
        .finally(() => {
          if (!ignore) setLoaded(true);
        });
    };

    load();
    window.addEventListener("works:changed", load);
    return () => {
      ignore = true;
      window.removeEventListener("works:changed", load);
    };
  }, [showWorkCard]);

  return (
    <div className="app-shell">
      <aside className="workspace-sidebar">
        <img src="/logo.png" className="side-logo" alt="w.LiGHTER" />
        <section className="side-section">
          <div className="side-title"><span>내 작품</span><Link href="/dashboard" className="side-add-btn">＋</Link></div>
          {showWorkCard && recentWork && (
            <Link href={`/works/${recentWork.id}`} className="work-mini-card">
              <div className="cover-dot" />
              <div>
                <b>{recentWork.title}</b>
                <span>{recentWork.genre || "장르 미선택"} · 회차 {recentWork.episode_count || 0}</span>
              </div>
              <i />
            </Link>
          )}
          {showWorkCard && loaded && !recentWork && (
            <Link href="/works/new" className="work-mini-card empty">
              <div className="cover-dot empty" />
              <div><b>등록된 작품 없음</b><span>새 작품을 먼저 등록하세요</span></div>
              <i />
            </Link>
          )}
        </section>
        <nav className="side-nav">
          {navItems.map((item) => (
            <Link key={item.href} className={active === item.href ? "active" : ""} href={item.href}>
              <span>{item.icon}</span>{item.label}
            </Link>
          ))}
        </nav>
        <div className="side-banner">
          <small>Write, Light, Lighter</small>
          <b>당신의 이야기를<br />세계에 빛으로 비춰봐요</b>
        </div>
      </aside>
      <main className="workspace-main">
        <header className="topbar">
          <div />
          <div className="credit-pill">12,400 cr</div>
          <div className="profile-pill"><span>👤</span></div>
        </header>
        {children}
      </main>
    </div>
  );
}

export function PageTitle({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) {
  return (
    <div className="page-title">
      <span>{eyebrow}</span>
      <h1>{title}</h1>
      <p>{text}</p>
    </div>
  );
}
