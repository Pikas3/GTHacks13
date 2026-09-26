# API contracts

Base URL: `http://localhost:8000/api`. Interactive docs: `http://localhost:8000/docs` (OpenAPI).
Backend schemas are in `backend/app/schemas/`. Frontend mirrors are in `frontend/lib/types.ts`.
**Change both together, and update this file first.**

## Errors

Every non-2xx response has the same shape:

```json
{ "error": { "code": "INVALID_HCP", "message": "Unknown HCP …", "details": {}, "request_id": "a1b2c3d4e5f6" } }
```

| Code | HTTP | When |
|------|------|------|
| `GEMINI_UNAVAILABLE` | 503 | Gemini call failed or returned output that failed schema validation |
| `ELEVENLABS_UNAVAILABLE` | 503 | TTS provider failed |
| `DATABASE_UNAVAILABLE` | 503 | DB unreachable or not migrated |
| `NO_EVIDENCE_FOUND` | 404 | reserved (answers normally set `insufficient_evidence` instead) |
| `INVALID_HCP` / `INVALID_SESSION` / `INVALID_RESOURCE` | 404 | unknown ID, or session belongs to another HCP |
| `AUDIO_TRANSCRIPTION_FAILED` | 422 | empty or oversized audio, or STT failure |
| `VALIDATION_ERROR` | 422 | request body/query invalid |
| `INTERNAL_ERROR` | 500 | anything else |

Each response has an `x-request-id` header, and the same ID appears in the backend logs.

## Endpoints

| Method | Path | Returns |
|--------|------|---------|
| GET | `/health` | `{status, database, timescaledb, pgvector, ai_mode, voice_mode, gemini_model, …}` (never errors) |
| GET | `/hcps` | `HCP[]` |
| GET | `/hcps/{hcp_id}` | `HCPDetail` (+ preferences, interests) |
| GET | `/hcps/{hcp_id}/timeline?limit=30` | `TimelineEntry[]` newest first |
| GET | `/hcps/{hcp_id}/interests` | `HCPInterest[]` by score |
| GET | `/resources?product=Novara` | `Resource[]` |
| GET | `/resources/{resource_id}` | `ResourceDetail` (+ chunks) |
| POST | `/sessions` `{hcp_id}` | `Session` (201), also records `SESSION_STARTED` |
| GET | `/sessions/{session_id}` | `SessionDetail` (+ turns, context) |
| POST | `/ambient/query` | `AmbientResponse` (below) |
| POST | `/ambient/events` | `{event, signals_generated}`: client-reported engagement, e.g. `SOURCE_OPEN` |
| POST | `/audio/transcribe` (multipart `audio`) | `{text, confidence, language, provider}` |
| POST | `/audio/synthesize` `{text}` | audio bytes (`audio/mpeg` real, `audio/wav` mock); headers `X-TTS-Provider`, `X-TTS-Placeholder` |
| GET | `/intelligence/{hcp_id}/signals?limit=20` | `{hcp_id, signals: EngagementSignal[], affinities: HCPInterest[]}` |
| GET | `/intelligence/{hcp_id}/recommendations` | `{hcp_id, recommendations: [{resource, reason, score}]}` |
| GET | `/intelligence/{hcp_id}/engagement?bucket=1 day` | `{points: [{bucket, topic, event_count}], top_entities}` |

## POST /ambient/query

Request:

```json
{
  "hcp_id": "e5f9bcd8-bb2e-5d76-9f3a-fdb3f848c8d8",
  "session_id": null,
  "query": "What's changed with Novara since I last looked at it?",
  "input_mode": "voice"
}
```

Omit `session_id` or send `null` to start a session. Send back the returned `session_id` for follow-ups.

Response (abridged, real mock-mode output):

```json
{
  "session_id": "1116…",
  "query": "What's changed with Novara since I last looked at it?",
  "resolved_query": "What's changed with Novara since I last looked at it?",
  "intent": "WHATS_NEW",
  "entities": [{ "name": "Novara", "type": "PRODUCT" }],
  "response": {
    "text": "Since you last reviewed Novara on July 2, 2026, 2 updated approved resource(s) are available: Novara Prescribing Information v2.0 [E1], Novara Trial A Long-Term Follow-Up v1.0 [E2]. Key change: …",
    "speech_text": "Since you last reviewed Novara on July 2, 2026, there are 2 new resources, …",
    "insufficient_evidence": false
  },
  "context": { "active_entity": "Novara", "active_topic": null, "active_resource_id": "…", "last_intent": "WHATS_NEW", "last_evidence_resource_ids": ["…"], "last_resolved_query": "…", "turn_count": 1 },
  "evidence": [
    { "id": "E1", "resource_id": "…", "chunk_id": "…", "title": "Novara Prescribing Information", "product": "Novara",
      "resource_type": "PRESCRIBING_INFORMATION", "version": "2.0", "section": "Renal Impairment", "page": null,
      "published_at": "2026-08-04T00:00:00Z", "excerpt": "Version 2.0 adds a dedicated renal impairment subsection…",
      "source_url": "https://example.invalid/…", "is_new": true, "score": 0.71 }
  ],
  "changes": [
    { "resource": "Novara Prescribing Information", "old_version": "1.0", "new_version": "2.0",
      "changes": [{ "topic": "Renal Impairment", "change_type": "UPDATED", "importance": "HIGH", "summary": "…", "old_evidence": "…", "new_evidence": "…" }] }
  ],
  "history": [],
  "suggested_followups": ["What about renal impairment?", "Show me the source.", "What did I look at last time?"],
  "signals_generated": [
    { "hcp_id": "…", "entity": "Novara", "entity_type": "PRODUCT", "topic": null, "intent": "WHATS_NEW",
      "event_type": "VOICE_QUERY", "weight": 0.08, "new_score": 0.72, "timestamp": "…" }
  ],
  "timings_ms": { "retrieval.vector_search": 5.4, "generation": 0.2, "ambient.total": 124.1 }
}
```

`text` may contain `[E#]` markers that refer to `evidence[].id`. `speech_text` is shorter and has no markers.
`history` is filled for `RECALL_HISTORY`. `changes` is filled for `WHATS_NEW` when a new version supersedes an old one.

## curl cheatsheet

```bash
M=$(curl -s localhost:8000/api/hcps | python3 -c "import json,sys;print([h['id'] for h in json.load(sys.stdin) if h['external_id']=='SYN-HCP-001'][0])")
curl -s -X POST localhost:8000/api/ambient/query -H 'content-type: application/json' \
  -d "{\"hcp_id\":\"$M\",\"query\":\"What's changed with Novara since I last looked at it?\"}"
curl -s -X POST localhost:8000/api/audio/synthesize -H 'content-type: application/json' -d '{"text":"hello"}' -o out.audio
```
