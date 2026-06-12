"use client";

export type TranslationDeliveryStatus = "deliverable" | "blocked_translation_safety";

export type TranslationUserVisibleErrorCode = "translation_safety_failed" | null;

export type TranslationSafetyMetadata = {
  residual_hangul_status?: string;
  proper_noun_transliteration_status?: string;
  source_copy_status?: string;
  locale_adherence_status?: string;
};

export type TranslationDisplayState = "result" | "qa_warning" | "blocked" | "error";

export type TranslationResponseLike = {
  finalTranslation?: string;
  deliveryStatus?: TranslationDeliveryStatus | string;
  userVisibleErrorCode?: TranslationUserVisibleErrorCode | string | null;
  message?: string;
  qaReport?: unknown;
  userVisibleQaReport?: Record<string, unknown>;
  metadata?: {
    translation_safety?: TranslationSafetyMetadata;
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

function hasWarn(metadata: TranslationSafetyMetadata | undefined): boolean {
  if (!metadata) return false;
  return [metadata.residual_hangul_status, metadata.proper_noun_transliteration_status].some(status => {
    const value = String(status || "").toLowerCase();
    return value === "warn" || value === "unchecked";
  });
}

export function isBlockedTranslationSafety(response: TranslationResponseLike | null | undefined): boolean {
  return response?.deliveryStatus === "blocked_translation_safety" || response?.userVisibleErrorCode === "translation_safety_failed";
}

export function isDeliverableTranslation(response: TranslationResponseLike | null | undefined): boolean {
  return response?.deliveryStatus === "deliverable" && Boolean((response?.finalTranslation || "").trim());
}

export function getTranslationDisplayState(response: TranslationResponseLike | null | undefined): TranslationDisplayState {
  if (!response) return "error";
  if (isBlockedTranslationSafety(response)) return "blocked";

  const finalTranslation = (response.finalTranslation || "").trim();
  if (!finalTranslation) return "error";

  const metadata = response.metadata?.translation_safety;
  if (hasWarn(metadata)) return "qa_warning";
  return "result";
}

export function getBlockedMessage(response: TranslationResponseLike | null | undefined): string {
  if (isBlockedTranslationSafety(response)) return "대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요.";
  return response?.message || "";
}
