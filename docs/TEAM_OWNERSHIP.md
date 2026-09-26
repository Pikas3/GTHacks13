# Team ownership

The repo is split so four people can work in parallel without editing the same files. Each workstream
builds against **interfaces** (Protocols / HTTP contracts), not against other people's code.

Find your work with: `grep -rn "TODO(<tag>)" backend frontend`

## A — Frontend / UX (`TODO(frontend)`)

**Owns:** `frontend/app/`, `frontend/components/`, `frontend/hooks/useConversation.ts`, `useHCP.ts`,
`useIntelligence.ts`, `useResource.ts`, `frontend/lib/mockApi.ts`

**Tasks:** VoiceOrb polish and waveform, ambient layout and animations, evidence cards and source viewer,
timeline, intelligence dashboard.

**Work independently:** set `NEXT_PUBLIC_USE_MOCK_API=true` in `frontend/.env.local` to run with no
backend. Talk to the backend only through `lib/api.ts` and the contracts in `docs/API.md`. Keep pipeline
logic in hooks and `lib/`, not in components.

**Start with:** `TODO(frontend)` in `components/ambient/VoiceOrb.tsx` (speaking waveform), then the
evidence/source viewer polish.

## B — AI / RAG (`TODO(ai-rag)`, `TODO(diff)`)

**Owns:** `backend/app/ai/`, `backend/app/ingestion/`, `data/seed/resources/`

**Tasks:** Gemini integration, intent extraction, embeddings, retrieval ranking, RAG prompting, semantic
diff, document ingestion.

**Interfaces you implement** (no route or orchestrator changes needed):

| Protocol | File | Mock | Real |
|---|---|---|---|
| `IntentClassifier` | `ai/intent.py` | `MockIntentClassifier` | `GeminiIntentClassifier` |
| `EmbeddingProvider` | `ai/embeddings.py` | `MockEmbeddingProvider` | `GeminiEmbeddingProvider` |
| `ResourceRetriever` | `ai/retrieval.py` | — | `HybridResourceRetriever` (weights in `RankingWeights`) |
| `ResponseGenerator` | `ai/generation.py` | `MockResponseGenerator` | `GeminiResponseGenerator` |
| `SemanticDiffService` | `ai/semantic_diff.py` | `MockSemanticDiffService` | `GeminiSemanticDiffService` |

**Start with:** set `GOOGLE_API_KEY` and `USE_MOCK_AI=false`, run `make seed` (re-embeds with Gemini),
then work through `TODO(ai-rag)` in `ai/retrieval.py` (hybrid ranking) and `ai/intent.py`.
Regression-test against `backend/tests/test_intent.py` and `test_orchestrator.py`.

## C — Backend / Database (`TODO(database)`)

**Owns:** `backend/app/db/`, `backend/app/ambient/`, `backend/app/impiricus/`, `backend/app/api/`,
`backend/app/dependencies.py`, `data/seed/*.json`

**Tasks:** Tiger Data schema, Timescale event storage, conversation state, memory, personalization,
MockIONService, API orchestration.

**Interfaces you implement:** `HCPRepository`, `ResourceRepository`, `InteractionRepository` (which also
covers the memory queries, i.e. the MemoryRepository role), `ConversationRepository`, all in
`db/repositories/interfaces.py`. Keep returning Pydantic schemas so the AI code and the tests never
change.

**Start with:** `TODO(database)` in `interaction_repository.py` (read from the continuous aggregate),
connect to Tiger Data cloud via `DATABASE_URL`, then interest-score decay.

## D — Voice / Integration (`TODO(voice)`)

**Owns:** `backend/app/voice/`, `frontend/hooks/useAudioRecorder.ts`, `backend/app/api/audio.py`

**Tasks:** ElevenLabs STT/TTS, audio recording, streaming playback, latency.

**Interfaces you implement:** `SpeechToTextProvider`, `TextToSpeechProvider` (`voice/interfaces.py`). You
never touch `AmbientOrchestrator`, which only ever sees text.

**Start with:** set `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `USE_MOCK_VOICE=false`. Verify
`/api/audio/transcribe` with real browser recordings (webm/opus from Chrome, mp4 from Safari), then
`TODO(voice)` streaming TTS.

## Shared files (change with care)

| File | Why it's shared |
|---|---|
| `backend/app/schemas/*` + `frontend/lib/types.ts` | The contract. Change both in one PR and update `docs/API.md` first |
| `backend/app/config.py`, `.env.example` | Add settings; never rename existing ones without telling the team |
| `backend/app/dependencies.py` | The only place implementations are chosen. Coordinate with C |
| `backend/app/ambient/orchestrator.py` | Pipeline order. Coordinate with C |
| `backend/app/db/migrations/versions/*` | Never edit a merged migration; add a new one |

## Git workflow

Suggested branches:

```
feature/frontend-ambient
feature/ai-rag
feature/tigerdata
feature/voice-elevenlabs
```

- Rebase on `main` often; keep PRs small and scoped to your owned directories.
- If a shared contract has to change, write the change in `docs/API.md` first, post it to the team, then
  update backend schema and frontend types in one PR.
- `make test` must pass before merging (backend pytest + frontend lint/typecheck/vitest). Nothing in it
  needs a DB or API keys.
