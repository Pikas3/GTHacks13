/**
 * In-browser fixture implementation of AmbientApi (NEXT_PUBLIC_USE_MOCK_API=true).
 * Lets frontend work proceed with no backend, database, or API keys.
 * All data is SYNTHETIC; products are FICTIONAL.
 */
import type { AmbientApi } from "@/lib/api";
import type {
  AmbientResponse,
  EngagementSignal,
  EvidenceReference,
  HCPDetail,
  IntentType,
  Resource,
  TimelineEntry,
} from "@/lib/types";

const MORGAN = "e5f9bcd8-bb2e-5d76-9f3a-fdb3f848c8d8";

const RESOURCES: Resource[] = [
  mkResource("r-pi-v2", "Novara Prescribing Information", "PRESCRIBING_INFORMATION", "2.0", "2026-08-04"),
  mkResource("r-ltfu", "Novara Trial A Long-Term Follow-Up", "CLINICAL_STUDY", "1.0", "2026-09-10"),
  mkResource("r-access", "Novara Access Guide", "ACCESS_GUIDE", "1.0", "2026-07-01"),
];

function mkResource(id: string, title: string, type: Resource["resource_type"], version: string, date: string): Resource {
  return {
    id, title, product: "Novara", resource_type: type, version, published_at: `${date}T00:00:00Z`,
    supersedes_resource_id: null, source_url: null, is_approved: true, metadata: { synthetic: true },
  };
}

function evidence(id: string, r: Resource, section: string, excerpt: string): EvidenceReference {
  return {
    id, resource_id: r.id, chunk_id: `${r.id}-${section}`, title: r.title, product: r.product,
    resource_type: r.resource_type, version: r.version, section, page: null, published_at: r.published_at,
    excerpt, source_url: null, is_new: true, score: 0.8,
  };
}

const [PI_V2, LTFU] = RESOURCES as [Resource, Resource, Resource];
const RENAL = evidence("E1", PI_V2, "Renal Impairment",
  "Version 2.0 adds a dedicated renal impairment subsection. For the fictional \"moderate renal impairment\" cohort, the synthetic label describes using Regimen A-R (reduced placeholder schedule).");
const LTFU_EV = evidence("E2", LTFU, "Long-Term Outcomes",
  "At the 36-month placeholder timepoint, the synthetic Regimen A arm maintained a higher Placeholder Durability Index than the comparator arm.");

export function createMockApi(): AmbientApi {
  const hcps: HCPDetail[] = [
    {
      id: MORGAN, external_id: "SYN-HCP-001", name: "Dr. Maya Morgan", specialty: "Oncology",
      organization: "Synthetic Regional Cancer Center", region: "Northeast (synthetic)",
      preferences: [{ key: "clinical_evidence", value: "Prefers primary trial data", weight: 0.8 }],
      interests: [
        { entity: "HER2", entity_type: "BIOMARKER", score: 0.82, interaction_count: 9, last_interaction_at: null },
        { entity: "Novara", entity_type: "PRODUCT", score: 0.64, interaction_count: 5, last_interaction_at: null },
        { entity: "patient access", entity_type: "TOPIC", score: 0.55, interaction_count: 3, last_interaction_at: null },
        { entity: "dosing", entity_type: "TOPIC", score: 0.48, interaction_count: 2, last_interaction_at: null },
        { entity: "safety", entity_type: "TOPIC", score: 0.24, interaction_count: 1, last_interaction_at: null },
      ],
    },
    {
      id: "mock-chen", external_id: "SYN-HCP-002", name: "Dr. Ethan Chen", specialty: "Cardiology",
      organization: null, region: null, preferences: [], interests: [],
    },
  ];
  const timeline: TimelineEntry[] = [
    { id: "t3", timestamp: "2026-07-02T16:30:00Z", event_type: "RESOURCE_VIEW", label: "Viewed Novara Access Guide v1.0", entity: "Novara", topic: "patient access", resource_id: "r-access" },
    { id: "t2", timestamp: "2026-06-14T14:12:00Z", event_type: "TEXT_QUERY", label: 'Asked "long-term outcomes"', entity: "Novara", topic: "long-term outcomes", resource_id: null },
    { id: "t1", timestamp: "2026-06-14T14:05:00Z", event_type: "RESOURCE_VIEW", label: "Viewed Novara Prescribing Information v1.0", entity: "Novara", topic: null, resource_id: null },
  ];
  const signals: EngagementSignal[] = [];
  let activeEntity: string | null = null;
  const delay = <T,>(v: T, ms = 350) => new Promise<T>((r) => setTimeout(() => r(v), ms));
  const find = (id: string) => hcps.find((h) => h.id === id) ?? hcps[0]!;

  function bump(hcpId: string, entity: string, weight: number, intent: IntentType | null): EngagementSignal {
    const hcp = find(hcpId);
    let interest = hcp.interests.find((i) => i.entity.toLowerCase() === entity.toLowerCase());
    if (!interest) {
      interest = { entity, entity_type: "TOPIC", score: 0, interaction_count: 0, last_interaction_at: null };
      hcp.interests.push(interest);
    }
    interest.score = Math.min(1, +(interest.score + weight).toFixed(4));
    interest.interaction_count += 1;
    hcp.interests.sort((a, b) => b.score - a.score);
    const s: EngagementSignal = {
      hcp_id: hcpId, entity, entity_type: interest.entity_type, topic: null, intent,
      event_type: "VOICE_QUERY", weight, new_score: interest.score, timestamp: new Date().toISOString(),
    };
    signals.unshift(s);
    return s;
  }

  return {
    health: () => delay({ status: "ok", database: "mock", timescaledb: false, pgvector: false, ai_mode: "mock-frontend", voice_mode: "mock", gemini_model: "n/a" }),
    listHcps: () => delay(hcps.map((h) => ({ id: h.id, external_id: h.external_id, name: h.name, specialty: h.specialty, organization: h.organization, region: h.region }))),
    getHcp: (id) => delay(structuredClone(find(id))),
    getTimeline: () => delay([...timeline]),
    getInterests: (id) => delay([...find(id).interests]),
    listResources: () => delay(RESOURCES),
    getResource: (id) => {
      const r = RESOURCES.find((x) => x.id === id) ?? PI_V2;
      return delay({ ...r, chunks: [{ id: "c1", resource_id: r.id, chunk_index: 0, text: RENAL.excerpt, section: "Renal Impairment", page: null }] });
    },
    createSession: () => delay({ id: crypto.randomUUID() }),
    async query(body) {
      const q = body.query.toLowerCase();
      let intent: IntentType = "QUESTION_ANSWERING";
      let text = "The available approved resources don't address that question.";
      let ev: EvidenceReference[] = [];
      let topic: string | null = null;
      if (/new|changed|update/.test(q)) {
        intent = "WHATS_NEW";
        activeEntity = "Novara";
        ev = [RENAL, LTFU_EV];
        text = "Since you last reviewed Novara on July 2, 2026, 2 updated approved resources are available: Novara Prescribing Information v2.0 [E1] and Novara Trial A Long-Term Follow-Up [E2]. Key change: renal impairment guidance was added.";
      } else if (/renal/.test(q)) {
        intent = activeEntity ? "FOLLOW_UP" : "QUESTION_ANSWERING";
        activeEntity = "Novara";
        topic = "renal impairment";
        ev = [RENAL];
        text = "According to Novara Prescribing Information v2.0 (Renal Impairment): the synthetic label describes Regimen A-R for the fictional moderate renal impairment cohort. [E1]";
      } else if (/source/.test(q)) {
        intent = "SHOW_SOURCE";
        ev = [RENAL];
        text = "My previous answer drew on: Novara Prescribing Information v2.0, Renal Impairment [E1].";
      } else if (/last time|look at/.test(q)) {
        intent = "RECALL_HISTORY";
        text = "Here's your recent activity — Jul 2: Viewed Novara Access Guide v1.0; Jun 14: Asked \"long-term outcomes\".";
      }
      const signalsGenerated = activeEntity ? [bump(body.hcp_id, activeEntity, 0.08, intent)] : [];
      if (topic) signalsGenerated.push(bump(body.hcp_id, topic, 0.08, intent));
      timeline.unshift({ id: crypto.randomUUID(), timestamp: new Date().toISOString(), event_type: body.input_mode === "voice" ? "VOICE_QUERY" : "TEXT_QUERY", label: `Asked "${body.query}"`, entity: activeEntity, topic, resource_id: null });
      const res: AmbientResponse = {
        session_id: body.session_id ?? crypto.randomUUID(),
        query: body.query,
        resolved_query: body.query,
        intent,
        entities: activeEntity ? [{ name: activeEntity, type: "PRODUCT" }] : [],
        response: { text, speech_text: text.replace(/\s*\[E\d+\]/g, ""), insufficient_evidence: ev.length === 0 && intent !== "RECALL_HISTORY" },
        context: { active_entity: activeEntity, active_topic: topic, active_resource_id: ev[0]?.resource_id ?? null, last_intent: intent, last_evidence_resource_ids: ev.map((e) => e.resource_id), last_resolved_query: body.query, turn_count: 1 },
        evidence: ev,
        changes: intent === "WHATS_NEW" ? [{ resource: "Novara Prescribing Information", old_version: "1.0", new_version: "2.0", changes: [{ topic: "Renal Impairment", change_type: "UPDATED", importance: "HIGH", summary: "Renal impairment guidance added in v2.0.", old_evidence: null, new_evidence: RENAL.excerpt }] }] : [],
        history: intent === "RECALL_HISTORY" ? timeline.slice(1) : [],
        suggested_followups: ["What about renal impairment?", "Show me the source."],
        signals_generated: signalsGenerated,
        timings_ms: { "ambient.total": 350 },
      };
      return delay(res, 700);
    },
    recordEvent: (body) => delay({ signals_generated: body.entity ? [bump(body.hcp_id, body.entity, 0.1, null)] : [] }),
    transcribe: () => delay({ text: "What's changed with Novara since I last looked at it?", confidence: 1, language: "en", provider: "mock-frontend" }, 500),
    synthesize: () => delay({ url: null, provider: "mock-frontend", isPlaceholder: true }),
    getSignals: (id) => delay({ hcp_id: id, signals: [...signals], affinities: [...find(id).interests] }),
    getRecommendations: (id) => delay({ hcp_id: id, recommendations: [{ resource: LTFU, reason: "Not yet viewed; Novara affinity 0.64.", score: 0.64 }] }),
    getEngagement: (id) => delay({
      hcp_id: id, bucket: "1 day",
      points: [
        { bucket: "2026-06-14T00:00:00Z", topic: "Novara", event_count: 2 },
        { bucket: "2026-07-02T00:00:00Z", topic: "patient access", event_count: 1 },
      ],
      top_entities: [],
    }),
  };
}
