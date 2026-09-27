/**
 * Shared API types. These MIRROR backend/app/schemas/*.py — change both together and
 * document contract changes in docs/API.md first.
 */

export type UUID = string;
export type ISODateTime = string;

export const INTENT_TYPES = [
  "QUESTION_ANSWERING",
  "WHATS_NEW",
  "RECALL_HISTORY",
  "COMPARE",
  "RESOURCE_SEARCH",
  "SHOW_SOURCE",
  "FOLLOW_UP",
  "UNKNOWN",
] as const;
export type IntentType = (typeof INTENT_TYPES)[number];

export type EventType =
  | "VOICE_QUERY"
  | "TEXT_QUERY"
  | "RESOURCE_VIEW"
  | "SOURCE_OPEN"
  | "RESPONSE_GENERATED"
  | "FOLLOW_UP"
  | "RESOURCE_SAVED"
  | "SESSION_STARTED";

export type ResourceType =
  | "PRESCRIBING_INFORMATION"
  | "CLINICAL_STUDY"
  | "ACCESS_GUIDE"
  | "EDUCATIONAL_RESOURCE";

export type EntityType = "PRODUCT" | "CONDITION" | "BIOMARKER" | "TOPIC" | "POPULATION" | "RESOURCE";
export type InputMode = "voice" | "text";
export type ChangeType = "ADDED" | "REMOVED" | "UPDATED" | "UNCHANGED";
export type Importance = "HIGH" | "MEDIUM" | "LOW";

export interface HCP {
  id: UUID;
  external_id: string;
  name: string;
  specialty: string;
  organization: string | null;
  region: string | null;
}

export interface HCPPreference {
  key: string;
  value: string;
  weight: number;
}

export interface HCPInterest {
  entity: string;
  entity_type: EntityType;
  score: number;
  interaction_count: number;
  last_interaction_at: ISODateTime | null;
}

export interface HCPDetail extends HCP {
  preferences: HCPPreference[];
  interests: HCPInterest[];
}

export interface Resource {
  id: UUID;
  title: string;
  product: string;
  resource_type: ResourceType;
  version: string;
  published_at: ISODateTime;
  supersedes_resource_id: UUID | null;
  source_url: string | null;
  is_approved: boolean;
  metadata: Record<string, unknown>;
}

export interface ResourceChunk {
  id: UUID;
  resource_id: UUID;
  chunk_index: number;
  text: string;
  section: string | null;
  page: number | null;
}

export interface ResourceDetail extends Resource {
  chunks: ResourceChunk[];
}

export interface TimelineEntry {
  id: UUID;
  timestamp: ISODateTime;
  event_type: EventType;
  label: string;
  entity: string | null;
  topic: string | null;
  resource_id: UUID | null;
}

export interface ExtractedEntity {
  name: string;
  type: EntityType;
}

export interface ConversationContext {
  active_entity: string | null;
  active_topic: string | null;
  active_resource_id: UUID | null;
  last_intent: IntentType | null;
  last_evidence_resource_ids: UUID[];
  last_resolved_query: string | null;
  turn_count: number;
}

export interface EvidenceReference {
  id: string;
  resource_id: UUID;
  chunk_id: UUID;
  title: string;
  product: string;
  resource_type: ResourceType;
  version: string;
  section: string | null;
  page: number | null;
  published_at: ISODateTime;
  excerpt: string;
  source_url: string | null;
  is_new: boolean;
  score: number | null;
}

export interface SectionChange {
  topic: string;
  change_type: ChangeType;
  importance: Importance;
  summary: string;
  old_evidence: string | null;
  new_evidence: string | null;
}

export interface SemanticDiff {
  resource: string;
  old_version: string;
  new_version: string;
  changes: SectionChange[];
}

export interface EngagementSignal {
  hcp_id: UUID;
  entity: string;
  entity_type: EntityType;
  topic: string | null;
  intent: IntentType | null;
  event_type: EventType;
  weight: number;
  new_score: number | null;
  timestamp: ISODateTime | null;
}

export interface LepiusRequest {
  hcp_id: UUID;
  session_id?: UUID | null;
  query: string;
  input_mode?: InputMode;
}

export interface LepiusResponse {
  session_id: UUID;
  query: string;
  resolved_query: string;
  intent: IntentType;
  entities: ExtractedEntity[];
  response: { text: string; speech_text: string; insufficient_evidence: boolean };
  context: ConversationContext;
  evidence: EvidenceReference[];
  changes: SemanticDiff[];
  history: TimelineEntry[];
  suggested_followups: string[];
  signals_generated: EngagementSignal[];
  timings_ms: Record<string, number>;
}

export interface EngagementEventRequest {
  hcp_id: UUID;
  session_id?: UUID | null;
  event_type: EventType;
  resource_id?: UUID | null;
  entity?: string | null;
  topic?: string | null;
}

export interface TranscriptionResult {
  text: string;
  confidence: number | null;
  language: string | null;
  provider: string;
}

export interface SynthesizedSpeech {
  /** Object URL for an <audio> element, or null when the backend returned placeholder audio. */
  url: string | null;
  provider: string;
  isPlaceholder: boolean;
}

/** Response from POST /audio/speech — stream via GET /audio/speech/{speech_id}. */
export interface SpeechHandle {
  speech_id: string;
  provider: string;
  media_type: string;
  is_placeholder: boolean;
  expires_in_s: number;
}

export interface Recommendation {
  resource: Resource;
  reason: string;
  score: number;
}

export interface IntelligenceSignals {
  hcp_id: UUID;
  signals: EngagementSignal[];
  affinities: HCPInterest[];
}

export interface IntelligenceRecommendations {
  hcp_id: UUID;
  recommendations: Recommendation[];
}

export interface EngagementBucket {
  bucket: ISODateTime;
  topic: string;
  event_count: number;
}

export interface EngagementSeries {
  hcp_id: UUID;
  bucket: string;
  points: EngagementBucket[];
  top_entities: { entity: string; score: number; interaction_count: number }[];
}

export type TrendingWindow = "1 day" | "7 days" | "30 days" | "90 days";

export interface TrendingTopic {
  topic: string;
  event_count: number;
  hcp_count: number;
  last_seen: ISODateTime;
}

/** Cross-HCP topic activity in a trailing window. */
export interface TrendingTopics {
  window: TrendingWindow;
  topics: TrendingTopic[];
}

/** Everything one HCP did after `since`. */
export interface ActivitySince {
  hcp_id: UUID;
  since: ISODateTime;
  event_count: number;
  by_type: Partial<Record<EventType, number>>;
  events: TimelineEntry[];
}

export interface HealthStatus {
  status: "ok" | "degraded";
  database: string;
  timescaledb: boolean;
  pgvector: boolean;
  topic_cagg: boolean;
  ai_mode: string;
  voice_mode: string;
  gemini_model: string;
}

export type ApiErrorCode =
  | "GEMINI_UNAVAILABLE"
  | "ELEVENLABS_UNAVAILABLE"
  | "DATABASE_UNAVAILABLE"
  | "NO_EVIDENCE_FOUND"
  | "INVALID_HCP"
  | "INVALID_SESSION"
  | "INVALID_RESOURCE"
  | "AUDIO_TRANSCRIPTION_FAILED"
  | "VALIDATION_ERROR"
  | "INTERNAL_ERROR"
  | "NETWORK_ERROR";

/** Voice orb / interaction state machine states. */
export type OrbState =
  | "idle"
  | "requesting_permission"
  | "listening"
  | "transcribing"
  | "thinking"
  | "speaking"
  | "error";
