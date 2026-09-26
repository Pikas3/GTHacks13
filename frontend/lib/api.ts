/**
 * Typed client for the Ambient HTTP API (see docs/API.md).
 * Components never call fetch directly — they go through hooks that use `api`.
 */
import { env } from "@/lib/env";
import { createMockApi } from "@/lib/mockApi";
import type {
  AmbientRequest,
  AmbientResponse,
  ApiErrorCode,
  EngagementEventRequest,
  EngagementSeries,
  EngagementSignal,
  HCP,
  HCPDetail,
  HCPInterest,
  HealthStatus,
  IntelligenceRecommendations,
  IntelligenceSignals,
  Resource,
  ResourceDetail,
  SynthesizedSpeech,
  TimelineEntry,
  TranscriptionResult,
  UUID,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(
    public readonly code: ApiErrorCode,
    message: string,
    public readonly status: number = 0,
    public readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface AmbientApi {
  health(): Promise<HealthStatus>;
  listHcps(): Promise<HCP[]>;
  getHcp(hcpId: UUID): Promise<HCPDetail>;
  getTimeline(hcpId: UUID, limit?: number): Promise<TimelineEntry[]>;
  getInterests(hcpId: UUID): Promise<HCPInterest[]>;
  listResources(product?: string): Promise<Resource[]>;
  getResource(resourceId: UUID): Promise<ResourceDetail>;
  createSession(hcpId: UUID): Promise<{ id: UUID }>;
  query(body: AmbientRequest): Promise<AmbientResponse>;
  recordEvent(body: EngagementEventRequest): Promise<{ signals_generated: EngagementSignal[] }>;
  transcribe(audio: Blob): Promise<TranscriptionResult>;
  synthesize(text: string): Promise<SynthesizedSpeech>;
  getSignals(hcpId: UUID, limit?: number): Promise<IntelligenceSignals>;
  getRecommendations(hcpId: UUID): Promise<IntelligenceRecommendations>;
  getEngagement(hcpId: UUID, bucket?: "1 hour" | "1 day" | "1 week"): Promise<EngagementSeries>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await rawRequest(path, init);
  return (await res.json()) as T;
}

async function rawRequest(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${env.apiBaseUrl}/api${path}`, init);
  } catch {
    throw new ApiError("NETWORK_ERROR", "Network request failed");
  }
  if (!res.ok) {
    let code: ApiErrorCode = "INTERNAL_ERROR";
    let message = res.statusText;
    let requestId: string | null = null;
    try {
      const body = (await res.json()) as { error?: { code: ApiErrorCode; message: string; request_id?: string } };
      if (body.error) {
        code = body.error.code;
        message = body.error.message;
        requestId = body.error.request_id ?? null;
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(code, message, res.status, requestId);
  }
  return res;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const httpApi: AmbientApi = {
  health: () => request("/health"),
  listHcps: () => request("/hcps"),
  getHcp: (id) => request(`/hcps/${id}`),
  getTimeline: (id, limit = 30) => request(`/hcps/${id}/timeline?limit=${limit}`),
  getInterests: (id) => request(`/hcps/${id}/interests`),
  listResources: (product) => request(`/resources${product ? `?product=${encodeURIComponent(product)}` : ""}`),
  getResource: (id) => request(`/resources/${id}`),
  createSession: (hcpId) => request("/sessions", json({ hcp_id: hcpId })),
  query: (body) => request("/ambient/query", json(body)),
  recordEvent: (body) => request("/ambient/events", json(body)),
  async transcribe(audio) {
    const form = new FormData();
    const ext = audio.type.includes("mp4") ? "mp4" : audio.type.includes("ogg") ? "ogg" : "webm";
    form.append("audio", audio, `recording.${ext}`);
    return request("/audio/transcribe", { method: "POST", body: form });
  },
  async synthesize(text) {
    const res = await rawRequest("/audio/synthesize", json({ text }));
    const isPlaceholder = res.headers.get("x-tts-placeholder") === "true";
    const provider = res.headers.get("x-tts-provider") ?? "unknown";
    if (isPlaceholder) return { url: null, provider, isPlaceholder };
    return { url: URL.createObjectURL(await res.blob()), provider, isPlaceholder };
  },
  getSignals: (id, limit = 20) => request(`/intelligence/${id}/signals?limit=${limit}`),
  getRecommendations: (id) => request(`/intelligence/${id}/recommendations`),
  getEngagement: (id, bucket = "1 day") =>
    request(`/intelligence/${id}/engagement?bucket=${encodeURIComponent(bucket)}`),
};

/** The API implementation used by the app (HTTP by default, fixtures when NEXT_PUBLIC_USE_MOCK_API=true). */
export const api: AmbientApi = env.useMockApi ? createMockApi() : httpApi;
