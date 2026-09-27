# Demo flow (2–3 minutes)

**Setup (before judges arrive):** `make db-up migrate seed`, `make backend`, `make frontend`.
Open `http://localhost:3000/lepius`. Run `make seed` again to reset demo state between runs.
For the real voice + AI demo, set `GOOGLE_API_KEY`, `ELEVENLABS_*`, `USE_MOCK_AI=false`,
`USE_MOCK_VOICE=false`, then run `make seed` again. Everything below also works fully mocked.

> Say up front: synthetic HCPs, fictional products, not medical advice, not a diagnostic tool.

| # | Action | What to point out |
|---|--------|-------------------|
| 1 | Profile selector → **Dr. Maya Morgan · Oncology** | Synthetic HCP. Right panel shows her memory |
| 2 | Point at **Previously reviewed / Interaction timeline** | Jun 14 viewed Novara PI v1, asked "long-term outcomes"; Jul 2 viewed Access Guide |
| 3 | **Hold the orb** and say *"What's changed with Novara since I last looked at it?"* | Orb goes listening → transcribing → thinking |
| 4 | Transcript appears with `whats new` + `Novara` chips | Gemini structured intent (`WHATS_NEW`, entity Novara, temporal ref = last interaction) |
| 5–7 | Answer: *"Since you last reviewed Novara on July 2, 2026, 2 updated approved resources…"* | Memory found her last review (Jul 2) and pulled only resources published after it: PI v2 and Trial A long-term follow-up |
| 8 | **What changed** list: Renal Impairment UPDATED (PI v1.0 → v2.0) | Semantic diff between superseded and current PI |
| 9 | Evidence cards at the bottom, tagged **New since last review**; click `E1` in the answer | Each claim cites an approved passage |
| 10 | Answer is spoken | ElevenLabs TTS of the shorter `speech_text` |
| 11 | Hold orb: *"What about renal impairment?"* | No product named |
| 12 | Transcript shows `→ Novara: What about renal impairment?` | Context resolved Novara from conversation state |
| 13 | Answer cites PI v2 Renal Impairment + renal sub-study; click **View source** | Full source with the cited passage highlighted. Records `SOURCE_OPEN` (+0.10) |
| 14 | Switch to **Intelligence** tab | Impiricus-facing view of the same HCP |
| 15 | Topic affinity chart: Novara ↑, new **renal impairment** bar; signal feed shows `VOICE_QUERY Novara +0.08 → …`, `SOURCE_OPEN +0.10`; timeline shows "Today"; engagement chart has a spike today | Every interaction became structured engagement data in Tiger Data (hypertable + time_bucket) |

Optional extras: *"Show me the source."* (re-surfaces the last evidence) and *"What did I look at last
time?"* (answered from structured memory, no LLM).

## Talking points

- **Not a chatbot:** the same question means different things for different HCPs, because identity, history
  and time are part of the query.
- **Grounded:** answers only from approved resources. When coverage is missing it says so.
- **Temporal:** "since I last looked" is a real SQL query over a Timescale hypertable.
- **One datastore:** Tiger Data holds relational profiles, time-series engagement and pgvector embeddings.
- **Closed loop:** every interaction updates HCP interest signals that Impiricus can act on (mocked as
  `MockIONService`).

## If something breaks

- Mic blocked → use the small text box under the orb (same pipeline).
- ElevenLabs down → answer still shows; orb skips speaking.
- Gemini down → set `USE_MOCK_AI=true`, then `make seed` and restart the backend (deterministic answers).
