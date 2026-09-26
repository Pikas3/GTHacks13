# Agent prompts

Copy-paste prompts for coding agents (Claude Code, etc.), one per workstream. Each one stands alone: it
gives the agent the product context, its ownership boundaries, what already exists, prioritized tasks,
gotchas, and a definition of done.

| File | Person | Branch | TODO tags |
|---|---|---|---|
| [A-frontend.md](A-frontend.md) | A: Frontend / UX | `feature/frontend-ambient` | `TODO(frontend)` |
| [B-ai-rag.md](B-ai-rag.md) | B: AI / RAG | `feature/ai-rag` | `TODO(ai-rag)`, `TODO(diff)` |
| [C-backend-db.md](C-backend-db.md) | C: Backend / Database | `feature/tigerdata` | `TODO(database)` |
| [D-voice.md](D-voice.md) | D: Voice / Integration | `feature/voice-elevenlabs` | `TODO(voice)` |

How to use one:

1. Check out your branch and run `make setup db-up migrate seed`.
2. Start your agent at the repo root and paste the whole prompt, or say:
   `Read docs/agent-prompts/B-ai-rag.md and follow it.`
3. Have the agent work one priority at a time and stop for review after each. The prompts ask for
   small, reviewable commits.

Every prompt lists which files are **shared contracts**. When an agent needs to change one, it must
propose the change first (see "Contract changes" in each prompt) rather than edit it silently.
