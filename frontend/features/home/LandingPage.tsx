import Link from "next/link";

const GlobeIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
);

const FileIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" /><line x1="8" y1="13" x2="16" y2="13" /><line x1="8" y1="17" x2="16" y2="17" />
  </svg>
);

const ImageIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" />
    <polyline points="21 15 16 10 5 21" />
  </svg>
);

const NetworkIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
  </svg>
);

const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

const SettingsIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

const SparkleIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

const DownloadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

const features = [
  { Icon: GlobeIcon, title: "현지화 가이드", text: "문화, 관습, 배경 지식을 체계적으로 정리합니다." },
  { Icon: FileIcon, title: "번역/검수", text: "AI 번역과 검수 흐름을 한 화면에서 제공합니다." },
  { Icon: ImageIcon, title: "표지 이미지 생성", text: "작품과 회차 내용을 바탕으로 웹소설 표지 방향을 시각화합니다." },
  { Icon: NetworkIcon, title: "관계도 생성", text: "등장인물 관계를 직관적으로 보여줍니다." },
];

const flows = [
  { Icon: UploadIcon, num: "01", title: "작품 업로드", text: "원고 또는 텍스트를 붙여넣어 작품을 등록합니다." },
  { Icon: SettingsIcon, num: "02", title: "국가·장르 설정", text: "번역 대상 국가와 작품 장르를 선택합니다." },
  { Icon: SparkleIcon, num: "03", title: "AI 분석·생성", text: "현지화 가이드, 번역, 이미지를 자동으로 생성합니다." },
  { Icon: DownloadIcon, num: "04", title: "결과 확인", text: "생성된 결과를 화면에서 확인하고 다음 작업으로 이어갑니다." },
];

export function LandingFeaturePage() {
  return (
    <div className="landing-page">
      <header className="landing-nav">
        <img src="/logo.png" alt="w.LiGHTER" />
        <nav>
          <a href="#service">서비스 소개</a>
          <a href="#features">주요 기능</a>
          <a href="#flow">이용 흐름</a>
        </nav>
        <Link className="primary" href="/dashboard">지금 시작하기 ＋</Link>
      </header>

      <section id="service" className="hero">
        <div className="hero-copy">
          <span>소설·웹소설 현지화 올인원 AI 플랫폼</span>
          <h1><span className="hero-title-line">당신의 이야기를</span><br />세계의 언어로<br />빛내다</h1>
          <p>현지화 가이드부터 번역·검수, 표지 이미지 생성, 관계도 생성까지 작가의 창작과 세계화를 지원합니다.</p>
          <div className="hero-actions">
            <Link className="primary" href="/dashboard">지금 시작하기 ＋</Link>
            <a className="secondary" href="#features">서비스 소개 보기 ›</a>
          </div>
          <div className="hero-badges">
            <span>작품·회차 관리</span>
            <span>번역/검수 연결</span>
            <span>이미지 생성 연결</span>
          </div>
        </div>

        <div className="hero-visual">
          <div className="hero-char-card">
            <div className="window-dots">● ● ●</div>
            <div className="hero-project-title">
              <small>프로젝트 미리보기</small>
              <b>표지 이미지</b>
            </div>
            <div className="hero-char-preview">
              <div className="hero-char-glow" />
              <img className="hero-character-image" src="/hero-character.png" alt="AI가 생성한 표지 이미지 미리보기" />
              <div className="hero-char-overlay">AI 표지 생성 완료</div>
            </div>
            <div className="hero-char-meta">
              <b>작품 등록 후 작업 공간에서 이어서 진행</b>
              <span>현지화 가이드 · 번역/검수 · 표지 · 관계도</span>
            </div>
            <div className="hero-char-tags">
              <span>현지화 가이드 완료</span>
              <span>번역/검수 대기</span>
              <span>이미지 생성 가능</span>
            </div>
            <div className="hero-mini-panels">
              <div>
                <small>현지화 키워드</small>
                <b>정서적 절제 · 시대 맥락</b>
              </div>
              <div>
                <small>관계도</small>
                <b>등장인물 관계 구성</b>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="feature-section">
        <h2>주요 기능</h2>
        <div className="feature-grid">
          {features.map(({ Icon, title, text }) => (
            <article key={title}>
              <div><Icon /></div>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="flow" className="flow-section">
        <h2>이용 흐름</h2>
        <div>
          {flows.map(({ Icon, num, title, text }) => (
            <article key={num}>
              <div className="flow-icon-wrap"><Icon /></div>
              <b>{num}</b>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <footer className="landing-footer">
        <img src="/logo.png" alt="w.LiGHTER" />
        <div className="footer-links">
          <a href="#service">서비스 소개</a>
          <a href="#features">주요 기능</a>
          <a href="#flow">이용 흐름</a>
        </div>
        <small>© 2024 w.LiGHTER. All rights reserved.</small>
      </footer>
    </div>
  );
}
