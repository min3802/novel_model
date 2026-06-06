"use client";

import { useEffect, useState } from "react";
import { WorkspaceShell, PageTitle } from "@/components/WorkspaceShell";

const API_BASE = process.env.NEXT_PUBLIC_WLIGHTER_API_BASE || "http://127.0.0.1:8000";
type Character = { name: string; description: string };
type Relation = { from: string; to: string; relation: string };
type ImageResult = { type: "base64" | "url" | "mock_image" | "refusal"; data?: string; model: string; notice?: string; message?: string; assetRecord?: GeneratedAsset };
type GeneratedAsset = { id: number; kind: "cover" | "relation"; work_id?: number | null; payload: Record<string, unknown>; result: ImageResult; created_at: string };
type SavedRelationImage = ImageResult & {
  id?: number;
  savedAt: string;
  workTitle: string;
  theme: string;
  extra: string;
  characters: Character[];
  relations: Relation[];
};

function asCharacters(value: unknown): Character[] {
  return Array.isArray(value) ? value.filter(Boolean).map((item) => ({
    name: String((item as Character).name || ""),
    description: String((item as Character).description || ""),
  })) : [];
}

function asRelations(value: unknown): Relation[] {
  return Array.isArray(value) ? value.filter(Boolean).map((item) => ({
    from: String((item as Relation).from || ""),
    to: String((item as Relation).to || ""),
    relation: String((item as Relation).relation || ""),
  })) : [];
}

function assetToSavedRelation(asset: GeneratedAsset): SavedRelationImage {
  const payload = asset.payload || {};
  return {
    ...asset.result,
    id: asset.id,
    savedAt: asset.created_at,
    workTitle: String(payload.workTitle || ""),
    theme: String(payload.theme || ""),
    extra: String(payload.extraPrompt || ""),
    characters: asCharacters(payload.characters),
    relations: asRelations(payload.relations),
  };
}

const DEFAULT_CHARS: Character[] = [
  { name: "", description: "" },
  { name: "", description: "" },
  { name: "", description: "" },
];

const DEFAULT_RELS: Relation[] = [
  { from: "", to: "", relation: "" },
  { from: "", to: "", relation: "" },
];

export function RelationWorkspace() {
  const [workTitle, setWorkTitle] = useState("");
  const [characters, setCharacters] = useState<Character[]>(DEFAULT_CHARS);
  const [relations, setRelations] = useState<Relation[]>(DEFAULT_RELS);
  const [theme, setTheme] = useState("");
  const [extra, setExtra] = useState("");
  const [result, setResult] = useState<ImageResult | null>(null);
  const [history, setHistory] = useState<SavedRelationImage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadHistory() {
    try {
      const res = await fetch(`${API_BASE}/api/generated-assets?kind=relation`);
      const data = await res.json() as { assets?: GeneratedAsset[]; error?: string };
      if (!res.ok) throw new Error(data.error || "Failed to load relation history.");
      const saved = (data.assets || []).map(assetToSavedRelation);
      setHistory(saved);
      if (saved[0]) setResult(prev => prev || saved[0]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  function saveImage(next: SavedRelationImage) {
    setHistory(prev => [next, ...prev.filter(item => item.id ? item.id !== next.id : item.savedAt !== next.savedAt)].slice(0, 6));
    setResult(next);
  }

  async function removeImage(item: SavedRelationImage) {
    if (item.id) {
      const res = await fetch(`${API_BASE}/api/generated-assets/${item.id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { setError(data.error || "Failed to delete relation image."); return; }
    }
    setHistory(prev => {
      const updated = prev.filter(row => item.id ? row.id !== item.id : row.savedAt !== item.savedAt);
      setResult(updated[0] || null);
      return updated;
    });
  }

  function updateChar(i: number, field: keyof Character, val: string) {
    setCharacters(prev => prev.map((c, idx) => idx === i ? { ...c, [field]: val } : c));
  }

  function updateRel(i: number, field: keyof Relation, val: string) {
    setRelations(prev => prev.map((r, idx) => idx === i ? { ...r, [field]: val } : r));
  }

  function addCharacter() {
    setCharacters(prev => [...prev, { name: "", description: "" }]);
  }

  function removeCharacter(i: number) {
    setCharacters(prev => prev.length <= 1 ? prev : prev.filter((_, idx) => idx !== i));
  }

  function addRelation() {
    setRelations(prev => [...prev, { from: "", to: "", relation: "" }]);
  }

  function removeRelation(i: number) {
    setRelations(prev => prev.length <= 1 ? prev : prev.filter((_, idx) => idx !== i));
  }

  async function generate() {
    const validChars = characters.filter(c => c.name.trim());
    if (validChars.length === 0) { setError("등장인물을 최소 1명 입력해주세요."); return; }
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/generate-relation-image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workTitle,
          characters: validChars,
          relations: relations.filter(r => r.from.trim() && r.to.trim()),
          theme,
          extraPrompt: extra,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "이미지 생성 실패");
      setResult(data);
      saveImage({
        ...data,
        id: data.assetRecord?.id,
        savedAt: data.assetRecord?.created_at || new Date().toISOString(),
        workTitle,
        theme,
        extra,
        characters,
        relations,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const imgSrc = result && result.data
    ? result.type === "base64" ? `data:image/png;base64,${result.data}` : result.type === "url" ? result.data : null
    : null;
  const validChars = characters.filter(c => c.name.trim());
  const validRelations = relations.filter(r => r.from.trim() && r.to.trim());

  return (
    <WorkspaceShell active="/workspace/relation">
      <PageTitle eyebrow="Workspace · Relation Map" title="관계도 생성" text="등장인물과 관계를 입력하면 AI가 관계도 이미지를 생성합니다." />

      <section className="visual-grid relation-grid">
        <div className="glass-card">
          <div className="visual-form-head">
            <div>
              <span>Relation Data</span>
              <h3>등장인물 / 관계 정보</h3>
            </div>
            <button className="primary compact" onClick={generate} disabled={loading}>
              {loading ? "생성 중..." : "관계도 생성"}
            </button>
          </div>

          <div className="field"><label className="form-label">작품 제목</label><input className="input-like" placeholder="작품 제목" value={workTitle} onChange={e => setWorkTitle(e.target.value)} /></div>
          <div className="visual-field-grid">
            <div className="field"><label className="form-label">주제/분위기</label><input className="input-like" placeholder="예) 인간 드라마, 가족 갈등" value={theme} onChange={e => setTheme(e.target.value)} /></div>
            <div className="field"><label className="form-label">추가 요청</label><input className="input-like" placeholder="스타일, 색감 등" value={extra} onChange={e => setExtra(e.target.value)} /></div>
          </div>

          <div className="section-row-title">
            <h3>등장인물</h3>
            <button className="secondary compact" type="button" onClick={addCharacter}>＋ 인물 추가</button>
          </div>
          {characters.map((c, i) => (
            <div className="relation-input-row character" key={i}>
              <input className="input-like" style={{ minHeight: "40px", fontSize: ".85rem" }} placeholder={`인물 ${i + 1} 이름`} value={c.name} onChange={e => updateChar(i, "name", e.target.value)} />
              <input className="input-like" style={{ minHeight: "40px", fontSize: ".85rem" }} placeholder="역할/설명" value={c.description} onChange={e => updateChar(i, "description", e.target.value)} />
              <button className="row-remove" type="button" onClick={() => removeCharacter(i)} disabled={characters.length <= 1}>×</button>
            </div>
          ))}

          <div className="section-row-title">
            <h3>관계</h3>
            <button className="secondary compact" type="button" onClick={addRelation}>＋ 관계 추가</button>
          </div>
          {relations.map((r, i) => (
            <div className="relation-input-row relation" key={i}>
              <input className="input-like" style={{ minHeight: "38px", fontSize: ".82rem" }} placeholder="인물 A" value={r.from} onChange={e => updateRel(i, "from", e.target.value)} />
              <span style={{ color: "var(--violet)", fontWeight: 900 }}>→</span>
              <input className="input-like" style={{ minHeight: "38px", fontSize: ".82rem" }} placeholder="인물 B" value={r.to} onChange={e => updateRel(i, "to", e.target.value)} />
              <input className="input-like" style={{ minHeight: "38px", fontSize: ".82rem" }} placeholder="관계 설명" value={r.relation} onChange={e => updateRel(i, "relation", e.target.value)} />
              <button className="row-remove" type="button" onClick={() => removeRelation(i)} disabled={relations.length <= 1}>×</button>
            </div>
          ))}
          {error && <p className="api-error">{error}</p>}
        </div>

        <div>
          <div className={`relation-map ${imgSrc ? "has-image" : ""}`}>
            {imgSrc ? (
              <img src={imgSrc} alt="generated relation map" className="generated-image absolute" />
            ) : validChars.length > 0 ? (
              <div className="local-relation-preview">
                <div className="local-node center"><b>{validChars[0].name}</b><span>{validChars[0].description || "중심 인물"}</span></div>
                {validChars.slice(1, 5).map((c, i) => (
                  <div className={`local-node pos-${i}`} key={`${c.name}-${i}`}>
                    <b>{c.name}</b><span>{c.description || "인물"}</span>
                  </div>
                ))}
                {validRelations.slice(0, 4).map((r, i) => (
                  <div className={`local-edge-label edge-${i}`} key={`${r.from}-${r.to}-${i}`}>{r.relation || `${r.from} → ${r.to}`}</div>
                ))}
              </div>
            ) : (
              <div className="relation-empty">
                {loading ? "관계도 이미지 생성 중..." : "등장인물을 입력하면 미리보기가 표시됩니다."}
              </div>
            )}
          </div>
          <div className="visual-result-actions">
            <button className="secondary" onClick={generate} disabled={loading || validChars.length === 0}>다시 생성</button>
            {imgSrc ? (
              <a className="secondary" href={imgSrc} download={`${workTitle || "relation-map"}.png`}>다운로드</a>
            ) : (
              <button className="secondary" disabled>다운로드</button>
            )}
          </div>
          {result && (
            <div className="result-info-card">
              <b>관계도 생성 완료</b>
              <span>모델: {result.model}</span>
            </div>
          )}

          <div className="guide-history image-history">
            <div className="guide-history-head">
              <b>관계도 이미지 기록</b>
              <span>{history.length}개 저장</span>
            </div>
            {history.length > 0 ? (
              <div className="image-history-list">
                {history.map(item => {
                  const historySrc = item.data ? (item.type === "base64" ? `data:image/png;base64,${item.data}` : item.type === "url" ? item.data : "") : "";
                  return (
                    <div key={item.savedAt} className="image-history-item">
                      <button type="button" className="image-history-open" onClick={() => setResult(item)}>
                        <img src={historySrc} alt={item.workTitle || "관계도"} />
                        <div>
                          <strong>{item.workTitle || "작품명 없음"}</strong>
                          <span>{item.theme || "주제 미지정"}</span>
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
              <div className="guide-history-empty">아직 저장된 관계도 이미지가 없습니다.</div>
            )}
          </div>
        </div>
      </section>
    </WorkspaceShell>
  );
}
