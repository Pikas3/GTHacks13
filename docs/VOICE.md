# Voice workstream notes (Team D)

## Local secrets

Put keys only in repo-root `.env` (gitignored). Never commit voice IDs that are
personal preferences into shared docs with the API key.

Current local defaults used for demos:

- `ELEVENLABS_TTS_MODEL=eleven_flash_v2_5`
- `ELEVENLABS_STT_MODEL=scribe_v1`
- `ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM` (Rachel — calm default; swap after `/v1/voices`)

Set `USE_MOCK_VOICE=false` to go live. `/api/health` → `voice_mode` should show
`stt:elevenlabs,tts:elevenlabs`.

## Realtime STT finding

ElevenLabs realtime STT (WebSocket / `scribe_v2_realtime`) is excellent for always-on
partial transcripts, but for our **push-to-talk** UX the user already holds until they
finish speaking. Adding a WebSocket handshake + PCM conversion on every press did not
clearly beat batch `POST /v1/speech-to-text` for short utterances. **Keep batch STT.**

## Remaining TODO(voice)

- Live Chrome + Safari verification with real mic recordings (needs keys + browser).
- Optional MediaSource early-start path on Chromium for true mid-stream playback.
- Pronunciation dictionary upload if product names are misread (respelling hook is ready).
