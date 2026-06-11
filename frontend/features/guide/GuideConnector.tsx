"use client";

import { useEffect, useRef, useState } from "react";
import { postJson } from "@/features/shared/api";

const API_BASE = process.env.NEXT_PUBLIC_WLIGHTER_API_BASE || "http://127.0.0.1:8000";

type GuideSection = { title: string; items: string[] };
type GuideEvidence = {
  platform: string;
  collection: string;
  rank: number;
  title: string;
  genre?: string | null;
  tags?: string[];
  source_url?: string | null;
  reason?: string;
};
type GuideRecommendation = {
  country: string;
  score: number;
  reasons: string[];
};
type GuideCountryOption = {
  country: string;
  display?: string;
  displayCountry?: string;
};
type GuideOptions = {
  countries?: { country: string; topGenres?: [string, number][]; topTags?: [string, number][]; platforms?: string[] }[];
  genres?: string[];
};
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
type GuideResult = {
  mode: "needs_country_and_genre_selection" | "country_genre_guide" | "synopsis_country_recommendation" | string;
  requiresSelection?: boolean;
  message?: string;
  availableOptions?: GuideOptions;
  title?: string;
  targetCountry?: string;
  targetCountryDisplay?: string;
  country?: string;
  displayCountry?: string;
  genre?: string;
  synopsis?: string;
  generationMode?: string;
  generation_mode?: string;
  recommendedCountries?: GuideRecommendation[];
  recommended_country?: string;
  recommended_country_display?: string;
  recommendation_reasons?: string[];
  limitation_notice?: string;
  available_countries?: GuideCountryOption[];
  htmlReport?: string;
  guide_html?: string;
  sections?: Record<string, GuideSection>;
  evidenceUsed?: GuideEvidence[];
  modelPromptPayload?: unknown;
  createdAt?: string;
  storageNotice?: { guideLimit?: number; removedGuideIds?: number[]; message?: string };
  summary_text?: string;
  id?: number;
  work_id?: number | null;
  guideRecord?: GuideRecord;
  translation_profile?: {
    tone?: string;
    dialogue_style?: string;
    narration_style?: string;
    localization_level?: string;
    proper_noun_policy?: string;
    culture_policy?: string;
    do_not?: string[];
  };
};
type GuideRecord = {
  id: number;
  work_id?: number | null;
  payload: Record<string, unknown>;
  guide: GuideResult;
  created_at: string;
  storage_notice?: GuideResult["storageNotice"];
};
type GuideResponse = GuideResult & { guideRecord?: GuideRecord };
type GuideHistoryItem = GuideResult & { id?: number; work_id?: number | null; savedAt: string };
type WorksResponse = { works?: Work[]; error?: string };

const GUIDE_SECTION_ORDER = [
  "market_trend_fit",
  "genre_trope_alignment",
  "title_synopsis_localization",
  "terminology_glossary_risks",
  "content_rating_sensitivity",
  "adaptation_checklist",
  "evidence_used",
];

const DEFAULT_COUNTRY_OPTIONS: GuideCountryOption[] = [
  { country: "Japan", display: "일본" },
  { country: "China", display: "중국" },
  { country: "US/global English", display: "미국" },
  { country: "Thailand", display: "태국" },
];

function displayCountryName(value?: string | null) {
  switch ((value || "").trim()) {
    case "Japan":
      return "일본";
    case "China":
      return "중국";
    case "US/global English":
      return "미국";
    case "Thailand":
      return "태국";
    case "영어권":
      return "미국";
    default:
      return value?.trim() || "미선택";
  }
}

function toCountryLabel(option: GuideCountryOption) {
  return option.display || option.displayCountry || displayCountryName(option.country);
}

function guideDisplayTitle(result: GuideResult) {
  if (result.title) return result.title;
  if (result.requiresSelection) {
    return result.synopsis
      ? "추천 국가를 먼저 확인해 주세요"
      : "시놉시스가 없어 대상 국가를 직접 선택해 주세요";
  }
  return `${displayCountryName(result.targetCountry || result.country)} 현지화 기준서`;
}

function guideMetaItems(result: GuideResult) {
  const modeLabel =
    result.mode === "synopsis_country_recommendation"
      ? "추천 단계"
      : result.mode === "country_genre_guide"
        ? "가이드 단계"
        : "검토 단계";
  const countryLabel = displayCountryName(
    result.targetCountryDisplay || result.displayCountry || result.targetCountry || result.country || result.recommended_country,
  );

  return [
    modeLabel,
    result.genre || "장르 미지정",
    countryLabel,
    result.createdAt || "",
  ].filter(Boolean);
}

function safeFilename(value: string) {
  return value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, "_")
    .slice(0, 80) || "localization-guide";
}

function guideToMarkdown(result: GuideResult) {
  const lines: string[] = [];
  lines.push(`# ${guideDisplayTitle(result)}`);
  lines.push("");
  lines.push(`- Mode: ${result.mode}`);
  lines.push(`- Target country: ${displayCountryName(result.targetCountry || result.country)}`);
  lines.push(`- Genre: ${result.genre || "미지정"}`);
  if (result.createdAt) lines.push(`- Created at: ${result.createdAt}`);
  if (result.synopsis) {
    lines.push("");
    lines.push("## Synopsis");
    lines.push(result.synopsis);
  }
  if (result.summary_text) {
    lines.push("");
    lines.push(`Summary: ${result.summary_text}`);
  }
  if (result.recommended_country) {
    lines.push("");
    lines.push(`- Recommended country: ${displayCountryName(result.recommended_country_display || result.recommended_country)}`);
  }
  if (result.recommendation_reasons?.length) {
    lines.push("");
    lines.push("## Recommendation reasons");
    result.recommendation_reasons.forEach(reason => lines.push(`- ${reason}`));
  }
  if (result.limitation_notice) {
    lines.push("");
    lines.push(`- Limitation: ${result.limitation_notice}`);
  }
  if (result.translation_profile) {
    lines.push("");
    lines.push("## Translation profile");
    if (result.translation_profile.tone) lines.push(`- Tone: ${result.translation_profile.tone}`);
    if (result.translation_profile.dialogue_style) lines.push(`- Dialogue style: ${result.translation_profile.dialogue_style}`);
    if (result.translation_profile.narration_style) lines.push(`- Narration style: ${result.translation_profile.narration_style}`);
    if (result.translation_profile.localization_level) lines.push(`- Localization level: ${result.translation_profile.localization_level}`);
    if (result.translation_profile.proper_noun_policy) lines.push(`- Proper noun policy: ${result.translation_profile.proper_noun_policy}`);
    if (result.translation_profile.culture_policy) lines.push(`- Culture policy: ${result.translation_profile.culture_policy}`);
    if (result.translation_profile.do_not?.length) lines.push(`- Do not: ${result.translation_profile.do_not.join("; ")}`);
  }
  if (result.recommendedCountries?.length) {
    lines.push("");
    lines.push("## Recommended countries");
    result.recommendedCountries.forEach(rec => {
      lines.push(`- ${displayCountryName(rec.country)} (${rec.score}): ${rec.reasons.join("; ")}`);
    });
  }
  if (result.sections) {
    const ordered = [
      ...GUIDE_SECTION_ORDER.flatMap(key => result.sections?.[key] ? [[key, result.sections[key]] as const] : []),
      ...Object.entries(result.sections).filter(([key]) => !GUIDE_SECTION_ORDER.includes(key)),
    ];
    ordered.forEach(([key, section]) => {
      lines.push("");
      lines.push(`## ${section.title || key}`);
      (section.items || []).forEach(item => lines.push(`- ${item}`));
    });
  }
  if (result.evidenceUsed?.length) {
    lines.push("");
    lines.push("## Evidence used");
    result.evidenceUsed.forEach(ev => {
      lines.push(`- ${ev.platform} / ${ev.collection} rank ${ev.rank}: ${ev.title}${ev.genre ? ` (${ev.genre})` : ""}`);
      if (ev.reason) lines.push(`  - Reason: ${ev.reason}`);
      if (ev.tags?.length) lines.push(`  - Tags: ${ev.tags.slice(0, 12).join(", ")}`);
      if (ev.source_url) lines.push(`  - Source: ${ev.source_url}`);
    });
  }
  lines.push("");
  lines.push("---");
  lines.push("Evidence boundary: platform trend metadata only; not national readership certainty.");
  return lines.join("\n");
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadGuide(result: GuideResult, format: "md" | "json") {
  const base = safeFilename(`${guideDisplayTitle(result)}-${result.targetCountry || result.country || "country"}-${result.genre || "genre"}`);
  if (format === "json") {
    downloadText(`${base}.json`, JSON.stringify(result, null, 2), "application/json;charset=utf-8");
    return;
  }
  downloadText(`${base}.md`, guideToMarkdown(result), "text/markdown;charset=utf-8");
}

async function downloadGuidePdf(result: GuideResult) {
  const id = guideId(result);
  if (!id) {
    throw new Error("PDF 다운로드 가능한 저장된 가이드가 아닙니다.");
  }
  const response = await fetch(`${API_BASE}/api/localization-guides/${id}/pdf`);
  if (!response.ok) {
    const data = await response.json().catch(() => ({} as { error?: string }));
    throw new Error(data.error || "PDF 다운로드에 실패했습니다.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${safeFilename(`${guideDisplayTitle(result)}-${result.targetCountry || result.country || "country"}-${result.genre || "genre"}`)}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function firstAvailableCountry(options: GuideCountryOption[]) {
  return options[0]?.country || "";
}

function guideId(result: GuideResult | GuideHistoryItem) {
  return result.guideRecord?.id || result.id || null;
}

export function GuideConnector() {
  const [works, setWorks] = useState<Work[]>([]);
  const [worksLoading, setWorksLoading] = useState(false);
  const [selectedWorkId, setSelectedWorkId] = useState("");
  const [genre, setGenre] = useState("로판");
  const [synopsis, setSynopsis] = useState("");
  const [selectedCountry, setSelectedCountry] = useState("");
  const [recommendationResult, setRecommendationResult] = useState<GuideResult | null>(null);
  const [guideResult, setGuideResult] = useState<GuideResult | null>(null);
  const [history, setHistory] = useState<GuideHistoryItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingAction, setLoadingAction] = useState<"recommend" | "generate" | null>(null);
  const [progress, setProgress] = useState(0);
  const [loadingText, setLoadingText] = useState("현지화 기준서를 준비하는 중입니다...");
  const loadingTargetRef = useRef(1800);
  const loadingTimerRef = useRef<number | null>(null);
  const loadingRef = useRef(false);

  const hasSynopsis = synopsis.trim().length > 0;
  const countryOptions = recommendationResult?.available_countries?.length
    ? recommendationResult.available_countries
    : DEFAULT_COUNTRY_OPTIONS;
  const recommendedCountry = recommendationResult?.recommended_country || "";
  const recommendedCountryLabel = displayCountryName(
    recommendationResult?.recommended_country_display || recommendationResult?.recommended_country || "",
  );
  const activePreview = guideResult || recommendationResult;
  const selectedWork = works.find(work => String(work.id) === selectedWorkId) || null;

  async function loadWorks() {
    setWorksLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/works`);
      const data = await res.json() as WorksResponse;
      if (!res.ok) throw new Error(data.error || "작품 목록을 불러오지 못했습니다.");
      setWorks(data.works || []);
    } catch (e) {
      setWorks([]);
    } finally {
      setWorksLoading(false);
    }
  }

  async function loadHistory() {
    try {
      const res = await fetch(`${API_BASE}/api/localization-guides`);
      const data = await res.json() as { guides?: GuideRecord[]; error?: string };
      if (!res.ok) throw new Error(data.error || "가이드 기록을 불러오지 못했습니다.");
      setHistory((data.guides || []).map(record => ({
        ...record.guide,
        storageNotice: record.storage_notice ?? record.guide.storageNotice,
        id: record.id,
        work_id: record.work_id ?? null,
        savedAt: record.created_at,
      })));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void loadWorks();
    void loadHistory();
  }, []);

  useEffect(() => {
    loadingRef.current = loading;
  }, [loading]);

  useEffect(() => {
    if (loadingRef.current) return;
    setRecommendationResult(null);
    setGuideResult(null);
    setError("");
  }, [genre, synopsis]);

  useEffect(() => {
    const nextWork = works.find(work => String(work.id) === selectedWorkId);
    if (!nextWork) return;
    setGenre(nextWork.genre && nextWork.genre !== "미선택" ? nextWork.genre : "");
    setSynopsis(nextWork.desc || "");
    setRecommendationResult(null);
    setGuideResult(null);
    setSelectedCountry("");
    setError("");
  }, [selectedWorkId, works]);

  useEffect(() => {
    if (!loading) {
      setProgress(0);
      if (loadingTimerRef.current) {
        window.clearInterval(loadingTimerRef.current);
        loadingTimerRef.current = null;
      }
      return;
    }

    const start = Date.now();
    const target = loadingTargetRef.current;
    const messages = loadingAction === "recommend"
      ? [
          "추천 가능한 국가 조합을 확인하는 중입니다...",
          "장르와 시놉시스 신호를 비교하는 중입니다...",
          "추천 사유와 제한 안내를 정리하는 중입니다...",
        ]
      : [
          "선택한 국가 기준으로 가이드를 준비하는 중입니다...",
          "번역/표현 방향을 정리하는 중입니다...",
          "가이드 섹션과 근거를 마무리하는 중입니다...",
        ];

    loadingTimerRef.current = window.setInterval(() => {
      const elapsed = Date.now() - start;
      const pct = Math.min(97, Math.round((elapsed / target) * 100));
      setProgress(pct);
      setLoadingText(messages[Math.min(messages.length - 1, Math.floor(elapsed / 700))]);
    }, 120);

    return () => {
      if (loadingTimerRef.current) {
        window.clearInterval(loadingTimerRef.current);
        loadingTimerRef.current = null;
      }
    };
  }, [loading, loadingAction]);

  function saveHistory(next: GuideResponse) {
    if (next.requiresSelection) return;
    const item: GuideHistoryItem = {
      ...next,
      id: next.guideRecord?.id,
      work_id: next.guideRecord?.work_id ?? next.work_id ?? null,
      savedAt: next.guideRecord?.created_at || new Date().toISOString(),
    };
    setHistory(prev => [
      item,
      ...prev.filter(entry => item.id ? entry.id !== item.id : guideDisplayTitle(entry) !== guideDisplayTitle(item) || entry.targetCountry !== item.targetCountry),
    ]);
  }

  async function removeHistory(item: GuideHistoryItem) {
    if (item.id) {
      const res = await fetch(`${API_BASE}/api/localization-guides/${item.id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || "가이드 삭제에 실패했습니다.");
        return;
      }
    }
    setHistory(prev => prev.filter(entry => item.id ? entry.id !== item.id : entry.savedAt !== item.savedAt));
  }

  function syncRecommendationSelection(nextResult: GuideResult) {
    setRecommendationResult(nextResult);
    setGuideResult(null);

    const nextCountry = nextResult.recommended_country
      || nextResult.targetCountry
      || firstAvailableCountry(nextResult.available_countries || [])
      || firstAvailableCountry(DEFAULT_COUNTRY_OPTIONS);
    setSelectedCountry(nextCountry);
  }

  async function getGuideCountForWork(workId: number) {
    const res = await fetch(`${API_BASE}/api/localization-guides?workId=${workId}`);
    const data = await res.json() as { guides?: GuideRecord[]; error?: string };
    if (!res.ok) throw new Error(data.error || "작품별 가이드 수를 확인하지 못했습니다.");
    return data.guides || [];
  }

  async function requestRecommendation() {
    const targetMs = 1200 + Math.floor(Math.random() * 900);
    loadingTargetRef.current = targetMs;
    setLoadingAction("recommend");
    setLoading(true);
    setError("");

    try {
      const workId = selectedWork ? selectedWork.id : undefined;
      const payload = {
        workId,
        title: selectedWork?.title || undefined,
        workTitle: selectedWork?.title || undefined,
        genre: genre.trim() || undefined,
        synopsis: synopsis.trim() || undefined,
      };
      const [guide] = await Promise.all([
        postJson<GuideResponse>("/api/guide", payload),
        new Promise(resolve => setTimeout(resolve, targetMs)),
      ]);

      if (guide.requiresSelection) {
        syncRecommendationSelection(guide);
        return;
      }

      // 추천 요청이었더라도 백엔드가 바로 가이드를 반환하면 가이드 상태로 저장한다.
      setGuideResult(guide);
      setSelectedCountry(guide.targetCountry || guide.country || "");
      saveHistory(guide);
      void loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setLoadingAction(null);
    }
  }

  async function confirmStorageBeforeGenerate() {
    if (!selectedWork) return true;
    try {
      const guides = await getGuideCountForWork(selectedWork.id);
      if (guides.length < 5) return true;
      return window.confirm(
        `이 작품에는 이미 가이드가 ${guides.length}개 있습니다.\n가이드 보관 한도는 5개이며, 새로 생성하면 가장 오래된 가이드가 삭제됩니다.\n계속 진행하시겠습니까?`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    }
  }

  async function requestGuide(nextCountry = selectedCountry || recommendedCountry) {
    if (!nextCountry) {
      setError("대상 국가를 먼저 선택해 주세요.");
      return;
    }

    const targetMs = 1200 + Math.floor(Math.random() * 900);
    loadingTargetRef.current = targetMs;
    setLoadingAction("generate");
    setLoading(true);
    setError("");

    try {
      const payload = {
        workId: selectedWork ? selectedWork.id : undefined,
        title: selectedWork?.title || undefined,
        workTitle: selectedWork?.title || undefined,
        targetCountry: nextCountry,
        genre: genre.trim() || undefined,
        synopsis: synopsis.trim() || undefined,
      };
      const [guide] = await Promise.all([
        postJson<GuideResponse>("/api/guide", payload),
        new Promise(resolve => setTimeout(resolve, targetMs)),
      ]);

      if (guide.requiresSelection) {
        syncRecommendationSelection(guide);
        return;
      }

      setGuideResult(guide);
      setSelectedCountry(guide.targetCountry || guide.country || nextCountry);
      saveHistory(guide);
      void loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setLoadingAction(null);
    }
  }

  function handlePrimaryAction() {
    if (loading) return;
    if (!genre.trim()) {
      setError("장르를 입력해 주세요.");
      return;
    }
    if (hasSynopsis && !recommendationResult) {
      void requestRecommendation();
      return;
    }
    if (selectedWork) {
      void (async () => {
        const confirmed = await confirmStorageBeforeGenerate();
        if (!confirmed) return;
        await requestGuide(selectedCountry || recommendationResult?.recommended_country || "");
      })();
      return;
    }
    void requestGuide(selectedCountry || recommendationResult?.recommended_country || "");
  }

  function selectCountry(nextCountry: string) {
    setSelectedCountry(nextCountry);
    setError("");
  }

  function selectWork(nextWorkId: string) {
    setSelectedWorkId(nextWorkId);
    setError("");
  }

  async function handlePdfDownload(result: GuideResult) {
    try {
      await downloadGuidePdf(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function openHistoryItem(item: GuideHistoryItem) {
    setRecommendationResult(null);
    setGuideResult(item);
    setSelectedCountry(item.targetCountry || item.country || "");
    setError("");
  }

  const orderedSections = guideResult?.sections
    ? GUIDE_SECTION_ORDER.flatMap(key => guideResult.sections?.[key] ? [[key, guideResult.sections[key]] as const] : [])
    : [];
  const extraSections = guideResult?.sections
    ? Object.entries(guideResult.sections).filter(([key]) => !GUIDE_SECTION_ORDER.includes(key))
    : [];
  const allSections = [...orderedSections, ...extraSections];

  const primaryButtonLabel = loading
    ? loadingText
    : hasSynopsis && !recommendationResult
      ? "현지화 적합 국가 추천 받기"
      : "선택한 국가로 가이드 생성";
  const primaryButtonDisabled = loading || !genre.trim() || (!hasSynopsis && !selectedCountry && !recommendedCountry);
  const selectionNotice = hasSynopsis
    ? recommendationResult
      ? "추천 국가는 기본 선택값입니다. 다른 국가를 눌러도 바로 생성되지는 않으며, 아래 버튼을 눌러야 가이드가 생성됩니다."
      : "시놉시스가 있으면 먼저 추천을 받고, 그다음 선택한 국가로 가이드를 생성합니다."
    : "시놉시스가 없어 국가 추천은 제공되지 않습니다. 일본/중국/미국/태국 중 대상 국가를 직접 선택해 주세요.";

  return (
    <section className="guide-grid">
      <div className="glass-card guide-panel">
        <h3>현지화 가이드</h3>
        <p className="guide-form-help">
          시놉시스가 있으면 먼저 국가 추천을 받고, 추천 국가는 기본값으로 둔 채 다른 국가로 바꿀 수 있습니다.
          국가를 선택하는 동작과 가이드 생성 동작은 분리되어 있습니다.
        </p>
        <div className="connector-controls guide-controls">
          <div className="guide-work-picker">
            <div className="guide-work-picker-head">
              <span className="guide-country-picker-label">작품 선택</span>
              <span className="guide-work-picker-note">선택한 작품의 장르와 시놉시스를 우선 사용합니다.</span>
            </div>
            <select
              className="guide-work-select"
              value={selectedWorkId}
              onChange={e => selectWork(e.target.value)}
              disabled={worksLoading || works.length === 0}
            >
              <option value="">{worksLoading ? "작품 목록을 불러오는 중..." : works.length > 0 ? "작품을 선택해 주세요" : "작품 목록이 없어 직접 입력합니다"}</option>
              {works.map(work => {
                const hasSynopsis = work.desc.trim().length > 0;
                const genreLabel = work.genre && work.genre !== "미선택" ? work.genre : "장르 미지정";
                return (
                  <option key={work.id} value={String(work.id)}>
                    {work.title} · {genreLabel} · 시놉시스 {hasSynopsis ? "있음" : "없음"}
                  </option>
                );
              })}
            </select>
            {selectedWork ? (
              <div className="guide-work-summary">
                <b>{selectedWork.title}</b>
                <p>
                  장르: {selectedWork.genre && selectedWork.genre !== "미선택" ? selectedWork.genre : "미지정"} · 시놉시스 등록: {selectedWork.desc.trim().length > 0 ? "있음" : "없음"}
                </p>
                <small>{selectedWork.status} · {selectedWork.created_at}</small>
              </div>
            ) : (
              <p className="guide-work-help">
                작품을 선택하면 장르와 시놉시스를 자동으로 사용합니다. 작품 목록이 없거나 연결되지 않은 경우 아래 직접 입력으로 진행할 수 있습니다.
              </p>
            )}
          </div>
          <div className="guide-dev-input">
            <span className="guide-country-picker-label">개발용 직접 입력</span>
            <input
              value={genre}
              onChange={e => setGenre(e.target.value)}
              placeholder="예: 로판, 현대 판타지, LitRPG"
            />
            <textarea
              className="guide-synopsis-input"
              value={synopsis}
              onChange={e => setSynopsis(e.target.value)}
              placeholder="시놉시스가 있으면 붙여 넣어 주세요. 있으면 먼저 추천을 받고, 없으면 국가를 직접 선택합니다."
            />
          </div>
          <div className="guide-country-picker">
            <span className="guide-country-picker-label">대상 국가</span>
            <div className="guide-country-list">
              {countryOptions.map(option => {
                const isSelected = selectedCountry === option.country;
                const isRecommended = recommendationResult?.recommended_country === option.country;
                return (
                  <button
                    key={option.country}
                    type="button"
                    className={`guide-country-option${isSelected ? " active" : ""}${isRecommended ? " recommended" : ""}`}
                    onClick={() => selectCountry(option.country)}
                  >
                    <span>{toCountryLabel(option)}</span>
                    {isRecommended && <small className="guide-country-badge">추천</small>}
                  </button>
                );
              })}
            </div>
          </div>
          <button className="primary" onClick={handlePrimaryAction} disabled={primaryButtonDisabled}>
            {primaryButtonLabel}
          </button>
          <p className="guide-action-note">{selectionNotice}</p>
        </div>
        {error && <p className="api-error">{error}</p>}

        {recommendationResult && (
          <div className="guide-selection-box">
            <b>추천 결과</b>
            <p className="guide-selection-summary">
              추천 국가: <strong>{recommendedCountryLabel}</strong>
              {recommendationResult.recommendation_reasons?.length ? ` · ${recommendationResult.recommendation_reasons.join(" / ")}` : ""}
            </p>
            {recommendationResult.limitation_notice && <p className="guide-note">{recommendationResult.limitation_notice}</p>}
            <div className="guide-selection-hint">
              국가를 바꾸는 것만으로는 가이드가 생성되지 않습니다. 아래 버튼을 눌러 선택한 국가 기준으로 가이드를 생성해 주세요.
            </div>
          </div>
        )}

        <div className="guide-history">
          <div className="guide-history-head">
            <b>가이드 기록</b>
            <span>{history.length} saved</span>
          </div>
          {history.length > 0 ? (
            <div className="guide-history-list">
              {history.map((item) => (
                <div key={`${guideDisplayTitle(item)}-${item.savedAt}`} className="guide-history-item">
                  <button type="button" className="guide-history-open" onClick={() => openHistoryItem(item)}>
                    <strong>{guideDisplayTitle(item)}</strong>
                    <span>{guideMetaItems(item).slice(0, 2).join(" · ")}</span>
                    <small>{item.savedAt.slice(0, 16).replace("T", " ")}</small>
                  </button>
                  <button type="button" className="secondary compact guide-history-delete" onClick={() => removeHistory(item)}>
                    삭제
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="guide-history-empty">아직 저장된 가이드가 없습니다.</div>
          )}
        </div>
      </div>

      <article className="glass-card guide-doc">
        {loading ? (
          <div className="guide-loading">
            <div className="guide-spinner" />
            <b>{loadingText}</b>
            <p>API와 모델 응답을 기다리는 동안 잠시만 기다려 주세요.</p>
            <div className="guide-progress">
              <span style={{ width: `${progress}%` }} />
            </div>
          </div>
        ) : guideResult ? (
          <>
            <div className="guide-doc-top">
              <div>
                <b>{guideDisplayTitle(guideResult)}</b>
                <p>
                  {guideResult.synopsis
                    ? "시놉시스 기반 추천을 반영한 가이드입니다."
                    : "시놉시스가 없어 선택한 국가를 기준으로 만든 가이드입니다."}
                </p>
              </div>
              <div className="guide-doc-meta">
                {guideMetaItems(guideResult).map(item => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </div>
            {guideResult.storageNotice && (
              <div className="guide-storage-notice">
                <b>보관 안내</b>
                <p>{guideResult.storageNotice.message || "작품 단위 가이드 보관 한도에 따라 오래된 결과가 정리될 수 있습니다."}</p>
                {guideResult.storageNotice.guideLimit && (
                  <small>작품당 최대 {guideResult.storageNotice.guideLimit}개 보관</small>
                )}
              </div>
            )}
            <div className="visual-result-actions guide-download-actions">
              <button type="button" className="secondary compact" onClick={() => void handlePdfDownload(guideResult)}>PDF 다운로드</button>
              <button type="button" className="secondary compact" onClick={() => downloadGuide(guideResult, "md")}>Markdown 다운로드</button>
              <button type="button" className="secondary compact" onClick={() => downloadGuide(guideResult, "json")}>JSON 다운로드</button>
            </div>

            {allSections.length > 0 && (
              <div className="guide-section-list">
                {allSections.map(([key, section], index) => (
                  <section key={key} className="guide-section">
                    <div className="guide-section-header">
                      <span className="guide-section-num">{index + 1}</span>
                      <span className="guide-section-title">{section.title || key}</span>
                    </div>
                    <ul className="guide-list">
                      {(section.items || []).map((item, itemIndex) => (
                        <li key={`${key}-${itemIndex}`}>{item}</li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            )}

            {guideResult.evidenceUsed && guideResult.evidenceUsed.length > 0 && (
              <section className="guide-evidence-panel">
                <div className="guide-section-header">
                  <span className="guide-section-title">사용 근거</span>
                </div>
                <div className="guide-evidence-list">
                  {guideResult.evidenceUsed.slice(0, 8).map((ev, index) => (
                    <article key={`${ev.platform}-${ev.collection}-${ev.rank}-${index}`} className="guide-evidence-item">
                      <b>{ev.platform} / {ev.collection} · rank {ev.rank}</b>
                      <span>{ev.title}</span>
                      <small>{ev.genre || "genre unknown"}{ev.reason ? ` · ${ev.reason}` : ""}</small>
                      {ev.tags && ev.tags.length > 0 && <p>{ev.tags.slice(0, 6).join(" · ")}</p>}
                    </article>
                  ))}
                </div>
              </section>
            )}

            {(guideResult.guide_html || guideResult.htmlReport) && (
              <details className="guide-html-preview">
                <summary>HTML 미리보기</summary>
                <div className="guide-html" dangerouslySetInnerHTML={{ __html: guideResult.guide_html || guideResult.htmlReport || "" }} />
              </details>
            )}
          </>
        ) : activePreview ? (
          <div className="guide-recommend-preview">
            <div className="guide-doc-top">
              <div>
                <b>{guideDisplayTitle(activePreview)}</b>
                <p>
                  {hasSynopsis
                    ? "추천 결과입니다. 선택한 국가로 가이드를 생성하려면 아래 버튼을 눌러 주세요."
                    : "시놉시스가 없어 추천을 제공하지 못했습니다. 국가를 직접 선택한 뒤 가이드를 생성해 주세요."}
                </p>
              </div>
              <div className="guide-doc-meta">
                {guideMetaItems(activePreview).map(item => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </div>
            {recommendationResult ? (
              <div className="guide-recommend-summary">
                <div className="guide-recommend-title-row">
                  <b>
                    추천 국가: {recommendedCountryLabel}
                  </b>
                  <span className="guide-country-badge guide-country-badge-inline">추천</span>
                </div>
                {(recommendationResult.recommendation_reasons || []).length > 0 && (
                  <ul className="guide-list guide-recommend-reasons">
                    {(recommendationResult.recommendation_reasons || []).map((reason, index) => (
                      <li key={`${reason}-${index}`}>{reason}</li>
                    ))}
                  </ul>
                )}
                {recommendationResult.limitation_notice && (
                  <p className="guide-note">
                    {recommendationResult.limitation_notice}
                  </p>
                )}
                <p className="guide-selection-hint">
                  국가 선택은 상태만 바꾸고, 실제 가이드는 아래 버튼을 눌러야 생성됩니다.
                </p>
              </div>
            ) : (
              <p className="guide-selection-hint">
                시놉시스가 없어 국가 추천을 제공할 수 없습니다. 일본/중국/미국/태국 중 대상 국가를 직접 선택해 주세요.
              </p>
            )}
          </div>
        ) : (
          <div className="assistant-empty guide-empty">
            아직 결과가 없습니다.<br />
            시놉시스가 있으면 먼저 추천을 받고, 없으면 국가를 직접 선택한 뒤 가이드를 생성하세요.
          </div>
        )}
      </article>
    </section>
  );
}
