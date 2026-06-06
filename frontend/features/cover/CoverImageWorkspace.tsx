"use client";

import { useEffect, useState } from "react";
import { WorkspaceShell, PageTitle } from "@/components/WorkspaceShell";

const API_BASE = process.env.NEXT_PUBLIC_WLIGHTER_API_BASE || "http://127.0.0.1:8000";
type ImageResult = {
  type: "base64" | "url" | "mock_image" | "refusal";
  data?: string;
  model: string;
  notice?: string;
  message?: string;
  prompt?: string;
  assetRecord?: GeneratedAsset;
};

type GeneratedAsset = {
  id: number;
  kind: "cover" | "relation";
  work_id?: number | null;
  payload: Record<string, unknown>;
  result: ImageResult;
  created_at: string;
};

type SavedCoverImage = ImageResult & {
  id?: number;
  savedAt: string;
  workTitle: string;
  targetCountry: string;
  genre: string;
  protagonist: string;
  protagonistTraits: string;
  appearance: string;
  symbols: string;
  mood: string;
  episodeSummaries: string;
  extraPrompt: string;
};

const STYLE_PRESETS = [
  "vertical web novel cover",
  "strong thumbnail readability",
  "title-safe negative space",
  "one clear focal subject",
  "polished digital illustration",
];

function resultToImageSrc(result: ImageResult | null): string | null {
  if (!result || result.type === "mock_image" || result.type === "refusal" || !result.data) return null;
  return result.type === "base64" ? `data:image/png;base64,${result.data}` : result.data;
}

function assetToSavedCover(asset: GeneratedAsset): SavedCoverImage {
  const payload = asset.payload || {};
  return {
    ...asset.result,
    id: asset.id,
    savedAt: asset.created_at,
    workTitle: String(payload.workTitle || ""),
    targetCountry: String(payload.targetCountry || ""),
    genre: String(payload.genre || ""),
    protagonist: String(payload.protagonist || ""),
    protagonistTraits: String(payload.protagonistTraits || ""),
    appearance: String(payload.appearance || ""),
    symbols: Array.isArray(payload.symbols) ? payload.symbols.join(", ") : String(payload.symbols || ""),
    mood: Array.isArray(payload.mood) ? payload.mood.join(", ") : String(payload.mood || ""),
    episodeSummaries: Array.isArray(payload.episodeSummaries) ? payload.episodeSummaries.join("\n") : String(payload.episodeSummaries || ""),
    extraPrompt: String(payload.extraPrompt || ""),
  };
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);
}

function splitComma(value: string): string[] {
  return value
    .split(",")
    .map(item => item.trim())
    .filter(Boolean);
}

export function CoverImageWorkspace() {
  const [workTitle, setWorkTitle] = useState("");
  const [targetCountry, setTargetCountry] = useState("US");
  const [genre, setGenre] = useState("");
  const [protagonist, setProtagonist] = useState("");
  const [protagonistTraits, setProtagonistTraits] = useState("");
  const [appearance, setAppearance] = useState("");
  const [symbols, setSymbols] = useState("");
  const [mood, setMood] = useState("");
  const [episodeSummaries, setEpisodeSummaries] = useState("");
  const [extraPrompt, setExtraPrompt] = useState("");
  const [result, setResult] = useState<ImageResult | null>(null);
  const [history, setHistory] = useState<SavedCoverImage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadHistory() {
    try {
      const res = await fetch(`${API_BASE}/api/generated-assets?kind=cover`);
      const data = await res.json() as { assets?: GeneratedAsset[]; error?: string };
      if (!res.ok) throw new Error(data.error || "Failed to load cover history.");
      const saved = (data.assets || []).map(assetToSavedCover);
      setHistory(saved);
      if (saved[0]) setResult(prev => prev || saved[0]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  function saveImage(next: SavedCoverImage) {
    setHistory(prev => [next, ...prev.filter(item => item.id ? item.id !== next.id : item.savedAt !== next.savedAt)].slice(0, 8));
    setResult(next);
  }

  async function removeImage(item: SavedCoverImage) {
    if (item.id) {
      const res = await fetch(`${API_BASE}/api/generated-assets/${item.id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { setError(data.error || "Failed to delete cover image."); return; }
    }
    setHistory(prev => {
      const updated = prev.filter(row => item.id ? row.id !== item.id : row.savedAt !== item.savedAt);
      setResult(updated[0] || null);
      return updated;
    });
  }

  async function generate() {
    if (!workTitle.trim()) { setError("작품 제목을 입력해주세요."); return; }
    if (!genre.trim()) { setError("장르를 입력해주세요."); return; }
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/generate-cover-image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workTitle,
          targetCountry,
          genre,
          protagonist,
          protagonistTraits,
          appearance,
          episodeSummaries: splitLines(episodeSummaries),
          symbols: splitComma(symbols),
          mood: splitComma(mood),
          extraPrompt,
        }),
      });
      const data = await res.json() as ImageResult;
      if (!res.ok) throw new Error(data.message || "표지 이미지 생성에 실패했습니다.");
      if (data.type === "refusal") {
        setResult(data);
        setError(data.message || "안전 정책상 생성할 수 없는 요청입니다.");
        return;
      }
      saveImage({
        ...data,
        id: data.assetRecord?.id,
        savedAt: data.assetRecord?.created_at || new Date().toISOString(),
        workTitle,
        targetCountry,
        genre,
        protagonist,
        protagonistTraits,
        appearance,
        symbols,
        mood,
        episodeSummaries,
        extraPrompt,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function appendPreset(text: string) {
    setExtraPrompt(prev => prev.includes(text) ? prev : [prev, text].filter(Boolean).join(", "));
  }

  const imgSrc = resultToImageSrc(result);
  const isMock = result?.type === "mock_image";

  return (
    <WorkspaceShell active="/workspace/character">
      <PageTitle
        eyebrow="Workspace · Cover Studio"
        title="표지 이미지 생성"
        text="작품 정보와 시장 신호를 입력해 웹소설 표지 이미지를 생성합니다."
      />

      <section className="visual-grid">
        <div className="glass-card">
          <div className="visual-form-head">
            <div>
              <span>Cover Prompt</span>
              <h3>표지 브리프</h3>
            </div>
            <button className="primary compact" onClick={generate} disabled={loading}>
              {loading ? "생성 중..." : "표지 생성"}
            </button>
          </div>

          <div className="visual-field-grid">
            <div className="field">
              <label className="form-label">작품 제목 *</label>
              <input className="input-like" placeholder="작품 제목" value={workTitle} onChange={e => setWorkTitle(e.target.value)} />
            </div>
            <div className="field">
              <label className="form-label">대상 국가/시장</label>
              <input className="input-like" placeholder="US, JP, Thailand..." value={targetCountry} onChange={e => setTargetCountry(e.target.value)} />
            </div>
          </div>

          <div className="visual-field-grid">
            <div className="field">
              <label className="form-label">장르 *</label>
              <input className="input-like" placeholder="LitRPG, romance fantasy, isekai..." value={genre} onChange={e => setGenre(e.target.value)} />
            </div>
            <div className="field">
              <label className="form-label">주요 인물/피사체</label>
              <input className="input-like" placeholder="주인공, 커플, 파티, 상징물" value={protagonist} onChange={e => setProtagonist(e.target.value)} />
            </div>
          </div>

          <div className="field">
            <label className="form-label">주인공 특징</label>
            <textarea className="textarea-like" placeholder="성격, 욕망, 갈등, 성장 방향" value={protagonistTraits} onChange={e => setProtagonistTraits(e.target.value)} />
          </div>

          <div className="field">
            <label className="form-label">외형/분위기</label>
            <textarea className="textarea-like" placeholder="의상, 색감, 표정, 배경 분위기" value={appearance} onChange={e => setAppearance(e.target.value)} />
          </div>

          <div className="visual-field-grid">
            <div className="field">
              <label className="form-label">상징 요소</label>
              <input className="input-like" placeholder="검, 계약서, 시스템창" value={symbols} onChange={e => setSymbols(e.target.value)} />
            </div>
            <div className="field">
              <label className="form-label">무드</label>
              <input className="input-like" placeholder="commercial, emotional, action" value={mood} onChange={e => setMood(e.target.value)} />
            </div>
          </div>

          <div className="field">
            <label className="form-label">회차/시놉시스 요약</label>
            <textarea className="textarea-like" placeholder="한 줄에 하나씩 주요 장면이나 훅을 입력" value={episodeSummaries} onChange={e => setEpisodeSummaries(e.target.value)} />
          </div>

          <div className="field">
            <label className="form-label">추가 요청</label>
            <div className="preset-chips">
              {STYLE_PRESETS.map(item => <button type="button" key={item} onClick={() => appendPreset(item)}>{item}</button>)}
            </div>
            <textarea className="textarea-like" placeholder="예: 제목 공간을 크게 남기고 배경은 단순하게" value={extraPrompt} onChange={e => setExtraPrompt(e.target.value)} />
          </div>

          {error && <p className="api-error">{error}</p>}
        </div>

        <div>
          <div className={`character-preview ${imgSrc || isMock ? "has-image" : ""}`}>
            {imgSrc ? (
              <img src={imgSrc} alt={`${workTitle || "작품"} 표지 이미지`} className="generated-image" />
            ) : (
              <div className="visual-empty-state">
                <div className="visual-empty-icon">▣</div>
                <b>{loading ? "표지 생성 중..." : isMock ? "Mock 표지 생성 완료" : "생성 이미지 미리보기"}</b>
                <p>{isMock ? result?.notice || "Mock mode generated a cover prompt." : "작품 제목과 장르를 입력하면 표지 이미지를 생성합니다."}</p>
              </div>
            )}
          </div>

          <div className="visual-result-actions">
            <button className="secondary" onClick={generate} disabled={loading || !workTitle.trim() || !genre.trim()}>다시 생성</button>
            {imgSrc ? (
              <a className="secondary" href={imgSrc} download={`${workTitle || "cover"}.png`}>다운로드</a>
            ) : (
              <button className="secondary" disabled>다운로드</button>
            )}
          </div>

          {result && (
            <div className="result-info-card">
              <b>{result.type === "refusal" ? "생성 거절" : "생성 완료"}</b>
              <span>모델: {result.model}</span>
              {result.prompt && <small>{result.prompt.slice(0, 240)}{result.prompt.length > 240 ? "..." : ""}</small>}
            </div>
          )}

          <div className="guide-history image-history">
            <div className="guide-history-head">
              <b>표지 이미지 기록</b>
              <span>{history.length}개 저장</span>
            </div>
            {history.length > 0 ? (
              <div className="image-history-list">
                {history.map(item => {
                  const historySrc = resultToImageSrc(item);
                  return (
                    <div key={item.savedAt} className="image-history-item">
                      <button type="button" className="image-history-open" onClick={() => setResult(item)}>
                        {historySrc ? <img src={historySrc} alt={item.workTitle} /> : <span className="image-history-placeholder">Mock</span>}
                        <div>
                          <strong>{item.workTitle}</strong>
                          <span>{item.targetCountry} · {item.genre}</span>
                          <small>{item.savedAt.slice(0, 16).replace("T", " ")}</small>
                        </div>
                      </button>
                      <button type="button" className="secondary compact guide-history-delete" onClick={() => removeImage(item)}>
                        삭제
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="guide-history-empty">아직 저장된 표지 이미지가 없습니다.</div>
            )}
          </div>
        </div>
      </section>
    </WorkspaceShell>
  );
}
