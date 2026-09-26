import type { ApiErrorCode, OrbState, ResourceType } from "@/lib/types";

export const APP_NAME = "Impiricus Ambient";

export const ORB_STATE_LABEL: Record<OrbState, string> = {
  idle: 'Hold to ask · or say "hey Ambient"',
  requesting_permission: "Allow microphone access…",
  listening: "Listening… say your question",
  transcribing: "Transcribing…",
  thinking: "Finding approved evidence…",
  speaking: "Speaking",
  error: "Something went wrong — hold or say hey Ambient",
};

export const RESOURCE_TYPE_LABEL: Record<ResourceType, string> = {
  PRESCRIBING_INFORMATION: "Prescribing Information",
  CLINICAL_STUDY: "Clinical Study",
  ACCESS_GUIDE: "Access Guide",
  EDUCATIONAL_RESOURCE: "Education",
};

/** User-facing copy for normalized backend errors. */
export const ERROR_MESSAGE: Record<ApiErrorCode, string> = {
  GEMINI_UNAVAILABLE: "The AI service is unavailable right now. Try again in a moment.",
  ELEVENLABS_UNAVAILABLE: "Voice playback is unavailable — the answer is shown on screen.",
  DATABASE_UNAVAILABLE: "Can't reach the database. Is `make db-up` running?",
  NO_EVIDENCE_FOUND: "No approved resources cover that question.",
  INVALID_HCP: "That HCP profile no longer exists. Pick another profile.",
  INVALID_SESSION: "Your session expired. Starting a new one.",
  INVALID_RESOURCE: "That resource could not be found.",
  AUDIO_TRANSCRIPTION_FAILED: "I couldn't hear that. Try again or type your question.",
  VALIDATION_ERROR: "That request wasn't valid.",
  INTERNAL_ERROR: "Unexpected server error.",
  NETWORK_ERROR: "Can't reach the Ambient API. Is the backend running on :8000?",
};

export const SAMPLE_QUERIES = [
  "What's changed with Novara since I last looked at it?",
  "What about renal impairment?",
  "Show me the source.",
  "What did I look at last time?",
  "What's new with Novara?",
] as const;

export const SELECTED_HCP_STORAGE_KEY = "ambient.selectedHcpId";
