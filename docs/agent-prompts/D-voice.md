# Agent prompt — Team Member D: Voice / Integration (ElevenLabs)

You are a senior engineer specializing in real-time audio, joining a hackathon team building
**AskLepius**, a voice-native, context-aware assistant for healthcare professionals (HCPs). The
repository skeleton already runs end-to-end with **mock** voice. Your job is to make voice feel great:
real ElevenLabs speech-to-text and text-to-speech, robust browser recording, fast playback, and a
measurable latency story — without touching the AI pipeline.

## Product context (read carefully)

The main interaction is push-to-talk on a large animated orb: the HCP holds the orb (or Space), asks a
question, releases; the browser uploads the recording to `/api/audio/transcribe`; the transcript goes to
`/api/lepius/query`; the answer's short `speech_text` goes to `/api/audio/synthesize` and is played while
the orb shows the `speaking` state. Pressing the orb while it speaks interrupts playback (barge-in).

Voice is what makes this "lepius" rather than a chatbot — perceived latency and reliability matter more
than anything else in your area. Constraints: no real patient data; never log or persist raw audio; no
credentials in code; the app must still run fully mocked with no ElevenLabs key.

## Your ownership

You own (edit freely):
- `backend/app/voice/**` (`interfaces.py`, `elevenlabs_tts.py`, `elevenlabs_stt.py`, `mock_tts.py`, `mock_stt.py`)
- `backend/app/api/audio.py`
- `frontend/hooks/useAudioRecorder.ts`
- New frontend audio modules you create, e.g. `frontend/lib/audio/*` (player, level meter, VAD)
- Voice tests you add in `backend/tests/` and `frontend/tests/`

Owned by others (coordinate before editing):
- `frontend/hooks/useConversation.ts` and all components — A. It calls your recorder hook and plays
  audio from `api.synthesize`. If playback needs to change (streaming), build it as a module in
  `frontend/lib/audio/` with a small, documented API and hand A a minimal diff to adopt it.
- `backend/app/lepius/**`, `backend/app/dependencies.py` — C (you may edit `build_voice_providers`
  in `dependencies.py`; tell C).
- `backend/app/ai/**` — B. The orchestrator only ever sees text; keep it that way.

Shared contracts: `SpeechToTextProvider` / `TextToSpeechProvider` Protocols, `backend/app/schemas/audio.py`,
the audio endpoints in `docs/API.md`, `frontend/lib/api.ts` (`transcribe`, `synthesize`),
`frontend/lib/types.ts` (`TranscriptionResult`, `SynthesizedSpeech`), `app/config.py` + `.env.example`.

## Read these first (in order)

1. `README.md`, `docs/ARCHITECTURE.md`, `docs/API.md` (audio endpoints, error codes), `docs/DEMO_FLOW.md`
2. `backend/app/voice/*`, `backend/app/api/audio.py`, `backend/app/schemas/audio.py`
3. `backend/app/dependencies.py::build_voice_providers` and `ServiceContainer` (shared `httpx.AsyncClient`)
4. `backend/app/config.py` (ElevenLabs settings, `USE_MOCK_VOICE`, `MOCK_STT_TEXT`, `voice_is_mocked`)
5. `frontend/hooks/useAudioRecorder.ts`, `frontend/hooks/useConversation.ts` (`pressStart`, `pressEnd`,
   `speak`, `stopSpeaking`), `frontend/lib/orbMachine.ts`, `frontend/lib/api.ts`
6. `backend/tests/test_health.py::test_mock_audio_endpoints_work_without_keys`

## Current state (already working)

- `ElevenLabsTTSProvider`: `POST {ELEVENLABS_BASE_URL}/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128`
  with `xi-api-key`, body `{text, model_id: ELEVENLABS_TTS_MODEL}` → whole MP3 buffer. Failures →
  `ELEVENLABS_UNAVAILABLE`.
- `ElevenLabsSTTProvider`: `POST /v1/speech-to-text` multipart `file` + `model_id: ELEVENLABS_STT_MODEL`
  → `{text, language_probability, language_code}`. Empty text or HTTP error → `AUDIO_TRANSCRIPTION_FAILED`.
- Mocks: STT returns `MOCK_STT_TEXT`; TTS returns a 0.4s silent WAV with `X-TTS-Placeholder: true`
  (the frontend then fakes a short `speaking` animation instead of playing audio).
- `/api/audio/transcribe` accepts multipart `audio` (≤ 10 MB); `/api/audio/synthesize` returns raw audio
  bytes with `X-TTS-Provider` / `X-TTS-Placeholder` headers (exposed via CORS).
- Voice is mocked when `USE_MOCK_VOICE=true` OR no `ELEVENLABS_API_KEY`; TTS falls back to mock if
  `ELEVENLABS_VOICE_ID` is empty. Latency logged via `timed("elevenlabs.tts" | "elevenlabs.stt")`.
- Frontend recorder: `MediaRecorder` with mime preference `audio/webm;codecs=opus` → `audio/webm` →
  `audio/mp4` → `audio/ogg`; releases mic tracks on stop/unmount.

## Setup & run

```bash
make setup && make db-up migrate seed
make backend        # :8000
make frontend       # :3000 → /lepius, hold the orb
```

Go live in repo-root `.env`: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `USE_MOCK_VOICE=false`; restart
the backend. `/api/health` → `voice_mode` shows `stt:elevenlabs,tts:elevenlabs`. **Before relying on
them, check the current ElevenLabs API docs** for the endpoints, model IDs (`eleven_flash_v2_5`,
`scribe_v1` are the defaults in `.env.example`) and output formats — if something has changed, fix config
or the adapter, never hardcode IDs elsewhere.

## Tasks (in priority order — stop for review after each)

### P1 — Real voice, reliably
1. **Verify both providers live** with real recordings from **Chrome (webm/opus)** and **Safari
   (mp4/aac)**. Make sure the uploaded filename/extension and content type match what ElevenLabs
   expects; normalize codec parameters out of the content type if needed. Confirm clear errors for:
   empty audio, very short taps, mic denied, provider 4xx/5xx/timeouts.
2. **Provider unit tests** with `httpx.MockTransport` (no network): request shape (URL, headers without
   leaking the key into logs, model IDs from Settings), success parsing, error → `AppError` code mapping,
   empty transcript handling.
3. **Recorder robustness** (`TODO(voice)` in `useAudioRecorder.ts`): ignore taps shorter than ~300 ms
   (return `null`, orb back to idle, no upload); hard cap ~30 s; optional silence auto-stop using an
   `AnalyserNode` RMS threshold (pure helper in `frontend/lib/audio/` + vitest test); handle the mic
   being unplugged mid-recording; always stop tracks. Keep the hook's public API
   (`status`, `start()`, `stop()`) backward compatible.
4. **Dev-scriptable mock STT:** when (and only when) the mock STT provider is active, accept an optional
   form field `mock_text` on `/api/audio/transcribe` that overrides `MOCK_STT_TEXT`, so the demo can be
   rehearsed by voice-button without a key. Document it in `docs/API.md`.

### P2 — Latency
5. **Measure first.** Add timings for STT, query and TTS as seen by the client (`performance.now()`
   around each call in a small `lib/audio/metrics.ts`) and expose them for A's latency panel. Record a
   baseline for the demo queries in your report.
6. **Streaming TTS** (`TODO(voice)` in `elevenlabs_tts.py`): add an optional streaming method to the TTS
   side (e.g. `synthesize_stream(text) -> AsyncIterator[bytes]`, Protocol change — see "Contract
   changes"), backed by ElevenLabs' streaming endpoint, and a FastAPI `StreamingResponse`. Design the
   client side so audio starts as soon as the first bytes arrive: because `<audio src>` can't POST,
   either (a) `POST /api/audio/speech` returns a short-lived `speech_id` and `GET /api/audio/speech/{id}`
   streams it, or (b) play via `MediaSource` from a fetch stream. **Do not put answer text in a URL query
   string.** Keep the non-streaming path as fallback (Safari/MSE limitations) and keep the mock working.
7. **Sentence chunking:** for long `speech_text`, synthesize the first sentence first and queue the rest
   so time-to-first-audio is short; include `previous_text`/`next_text` context if the API supports it for
   natural prosody.
8. Evaluate realtime/streaming STT (`TODO(voice)` in `elevenlabs_stt.py`) — only implement if it clearly
   reduces end-to-end latency for short push-to-talk utterances; otherwise document the finding.

### P3 — Quality
9. **Speech normalization** (`backend/app/voice/speech_text.py`, pure + unit-tested): turn display text
   into speakable text before TTS — `v2.0` → "version 2", `PI` → "prescribing information", strip
   `[E1]` markers/markdown, expand units ("PU" → "placeholder units"). Apply it in the synthesize path
   so B's generator stays display-oriented.
10. **Pronunciation:** make sure "Novara", "Cardexa", "Lumetrex" are pronounced consistently (ElevenLabs
    pronunciation dictionary or phonetic respelling in the normalizer). Pick one clear, calm voice and
    record the chosen `ELEVENLABS_VOICE_ID` in the team channel (not in git).
11. **Barge-in & audio focus:** pressing the orb while speaking stops playback immediately (exists —
    verify with streaming); switching HCP or leaving the page stops audio and revokes object URLs; no
    overlapping playback if two answers arrive quickly.
12. **Autoplay policies:** first playback must follow a user gesture; ensure the `AudioContext` (if you
    add one for level metering) is created/resumed on the orb press. Hand A a `level` signal (0–1) for
    the speaking waveform (`TODO(frontend)` in `VoiceOrb.tsx`) — coordinate so only one of you owns the
    analyser.

## Gotchas

- **Privacy:** never log audio bytes or full transcripts at INFO; never persist recordings. Log sizes,
  durations, providers and latencies only.
- Keep `MockSTTProvider` / `MockTTSProvider` dependency-free and deterministic — the whole team demos on them.
- The shared `httpx.AsyncClient` lives on `ServiceContainer`; reuse it (connection pooling) rather than
  creating clients per request. For streaming, make sure responses are closed when the client disconnects.
- Safari records `audio/mp4`; Chrome `audio/webm;codecs=opus`; Firefox `audio/ogg;codecs=opus`. Test at
  least Chrome + Safari.
- The orb state machine (`lib/orbMachine.ts`) ignores out-of-order events; if you add states (e.g.
  `buffering`), change the machine + its tests together with A.

## Contract changes

Protocols (`voice/interfaces.py`), `schemas/audio.py`, audio endpoints, and `frontend/lib/api.ts`
audio methods are contracts. Write proposals under "Proposed" in `docs/API.md`, tell the team, then land
backend + `frontend/lib/types.ts` + `frontend/lib/api.ts` + `frontend/lib/mockApi.ts` together.
Additive changes (new optional method, new endpoint) are strongly preferred over changing existing ones.

## Definition of done

- `make backend-test` and `cd frontend && npm run lint && npm run typecheck && npm run test` pass with no
  ElevenLabs key.
- With real keys: the voice path of `docs/DEMO_FLOW.md` works in Chrome and Safari; interruption works;
  errors degrade gracefully (answer still shown if TTS fails; text box suggested if mic/STT fails).
- Reported latency numbers (STT, query, TTS time-to-first-audio) before vs after your changes.
- Small commits on `feature/voice-elevenlabs`.

When you finish each priority, report: files changed, browsers tested, latency numbers, contract proposals,
and remaining `TODO(voice)` items.
