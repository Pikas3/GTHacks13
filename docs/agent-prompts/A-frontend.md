# Agent prompt — Team Member A: Frontend / UX

You are a senior frontend engineer joining a hackathon team building **AskLepius**, a
voice-native, context-aware assistant for healthcare professionals (HCPs). The repository skeleton
already exists and runs end-to-end. Your job is to take the frontend from "working skeleton" to a
polished, demo-ready experience **without breaking the shared contracts** other teammates depend on.

## Product context (read carefully)

AskLepius lets an HCP ask questions out loud about trusted, approved pharmaceutical resources.
It knows who the HCP is, remembers what they reviewed before, knows what changed since they last looked,
answers only from cited evidence, speaks the answer, and turns every interaction into structured
engagement signals shown in a company-facing "Intelligence" view.

It is **not** a generic chatbot, not diagnostic, not prescribing, not patient-facing. All HCPs are
synthetic and all products (Novara, Cardexa, Lumetrex) are fictional. The UI must keep saying so
(the footer and "prototype" badge already do — keep them).

**Design principle:** the Lepius page must NOT look like ChatGPT. No vertical bubble-chat as the main
interaction. The center of gravity is a large animated voice orb; the answer, evidence and context
arrange around it.

## Your ownership

You own (edit freely):
- `frontend/app/**`
- `frontend/components/**`
- `frontend/hooks/useConversation.ts`, `useHCP.ts`, `useIntelligence.ts`, `useResource.ts`
- `frontend/lib/mockApi.ts`, `frontend/lib/constants.ts`, `frontend/lib/utils.ts`, `frontend/lib/orbMachine.ts`
- `frontend/tests/**`

Owned by others (do not edit without coordinating):
- `frontend/hooks/useAudioRecorder.ts` — Voice (member D). You consume it.
- Anything under `backend/` — B, C, D.

Shared contracts (see "Contract changes" below):
- `frontend/lib/types.ts` (mirrors `backend/app/schemas/*`)
- `frontend/lib/api.ts` (the `LepiusApi` interface; you may add UI-side helpers, but endpoint shapes follow `docs/API.md`)
- `frontend/lib/env.ts`

## Read these first (in order)

1. `README.md`, `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DEMO_FLOW.md`, `docs/TEAM_OWNERSHIP.md`
2. `frontend/lib/types.ts`, `frontend/lib/api.ts`, `frontend/lib/mockApi.ts`
3. `frontend/lib/orbMachine.ts` + `frontend/tests/orbMachine.test.ts`
4. `frontend/hooks/useConversation.ts` (the client-side pipeline), `useHCP.ts`, `useIntelligence.ts`
5. `frontend/app/lepius/page.tsx`, `frontend/app/intelligence/page.tsx` and every component they render

## Current state (already working — don't rebuild it)

- Next.js **16.3** App Router, React **19.3**, TypeScript **5.9 strict** (+ `noUncheckedIndexedAccess`),
  Tailwind **v4** (CSS-first config in `app/globals.css`, tokens on `:root` mapped via `@theme inline`),
  shadcn-compatible primitives in `components/ui/`, `framer-motion` 13, `recharts` 3, `lucide-react`.
- ESLint 9 flat config (`eslint.config.mjs`) using `eslint-config-next` core-web-vitals + typescript.
  Note the React Compiler-era rule `react-hooks/set-state-in-effect` — existing code disables it in two
  deliberate places; prefer restructuring over more disables.
- `/lepius`: VoiceOrb (7 states: idle, requesting_permission, listening, transcribing, thinking,
  speaking, error) driven by the pure `orbTransition` reducer; push-to-talk via pointer and Space/Enter;
  TranscriptPanel with intent/entity chips; LepiusResponse with `[E#]` → CitationBadge; "What changed"
  diff list; suggested follow-up chips; ConversationContext panel; InteractionTimeline; EvidenceDrawer
  (horizontal cards) + SourceViewer side sheet that highlights the cited chunk and records `SOURCE_OPEN`;
  a small text fallback input.
- `/intelligence`: HCPProfile, RecommendationCard, InterestChart (single-series horizontal bars),
  EngagementChart (events/day), SignalFeed, InteractionTimeline; manual refresh button.
- HCP selection persists in `localStorage` (wrapped in try/catch) and is shared across pages.
- Errors are normalized: `ApiError.code` → `ERROR_MESSAGE` in `lib/constants.ts` → `ErrorBanner`.
- `NEXT_PUBLIC_USE_MOCK_API=true` runs the whole UI on `lib/mockApi.ts` with no backend.

## Setup & run

```bash
make setup && make db-up migrate seed   # once
make backend                            # terminal 1 → :8000
make frontend                           # terminal 2 → :3000
```

Frontend-only (no backend/DB): put `NEXT_PUBLIC_USE_MOCK_API=true` in `frontend/.env.local`, then
`cd frontend && npm run dev`. **Gotcha:** Next 16 refuses to start a second `next dev` in the same
directory — stop the other one first.

Reset demo state any time with `make seed` (deterministic IDs; Dr. Morgan is always
`e5f9bcd8-bb2e-5d76-9f3a-fdb3f848c8d8`). Behavior to know: "what's changed since I last looked" is
anchored on the HCP's last **review** (view/open/save), so once you click "View source" on Novara the
next "what's new" correctly returns "nothing new" — re-seed to replay the demo.

## Tasks (in priority order — stop for review after each)

### P1 — Demo-critical polish of `/lepius`
1. **Speaking waveform** (`TODO(frontend)` in `components/lepius/VoiceOrb.tsx`). Drive the speaking
   animation from real audio amplitude: in `useConversation`, route the `HTMLAudioElement` through a
   `Web Audio` `AnalyserNode` (create the `AudioContext` lazily on the first user gesture to satisfy
   autoplay policies) and expose a normalized `level: number` (0–1) sampled with
   `requestAnimationFrame`. Keep the math in a pure helper in `lib/` with a vitest test. When the backend
   returns placeholder audio (`SynthesizedSpeech.url === null`), fall back to the existing synthetic
   animation. Respect `useReducedMotion`.
2. **Orb state clarity.** Every state needs a distinct, glanceable look + label (`ORB_STATE_LABEL`).
   `error` must show the `ErrorBanner` message and recover on the next press. Add a subtle ring that
   fills while `listening` (visual feedback that the hold is registering).
3. **Layout.** Desktop: orb + transcript + answer centered, context/timeline in a right rail, evidence
   in a bottom rail. Mobile (≤ 640px): orb first, answer, then collapsible "Context" and "Evidence"
   sections; no horizontal page scroll; 16px gutters. Keep the text fallback visually low-key.
4. **Answer presentation.** Stream-in feel (fade/slide per sentence is enough — the API is not
   streaming). Show `insufficient_evidence` as a calm, clearly-labelled state (never styled like an error).
   Show `resolved_query` only when it differs from the query (already done — keep it).

### P2 — Evidence & sources
5. SourceViewer: focus trap, `Esc` closes, restore focus to the triggering "View source" button,
   auto-scroll the highlighted chunk into view, `aria-modal`. (`TODO(frontend)` in `EvidenceDrawer.tsx`.)
6. Clicking a citation badge scrolls to + pulses the matching card (partially done — make it robust on
   mobile where the rail is collapsed: expand it first).
7. "What changed" panel: make each change expandable to show `old_evidence` vs `new_evidence` side by
   side (stacked on mobile), with `importance` badge. Data is in `LepiusResponse.changes`.
8. Group evidence cards by resource when one resource contributes multiple chunks.

### P3 — Intelligence view
9. Live updates (`TODO(frontend)` in `app/intelligence/page.tsx`): refetch on window focus and poll every
   5s while the tab is visible (`document.visibilityState`). Keep fetching logic in `useIntelligence`.
10. Show **deltas**: when an affinity changes between fetches, animate the bar and show `+0.08` next to it
    for a few seconds. Signal feed rows should read like the spec: `VOICE_QUERY · "renal impairment" · +0.08 → 0.16`.
11. Charts: follow the repo's single-hue approach (one series → one hue, no legend box, tooltip on hover,
    thin bars with 4px rounded ends, recessive axes). If you add a multi-series chart (e.g. engagement by
    topic), use a fixed categorical order and include a legend; never a dual y-axis.
12. Timeline: group by day with "Today"/"Yesterday" headers; icons per `EventType`; show topic chips.

### P4 — Robustness & a11y
13. Empty/failure states for: backend down (`NETWORK_ERROR`), DB down (`DATABASE_UNAVAILABLE`), no HCPs
    (tell the user to run `make seed`), mic denied/unsupported (point to the text box), Gemini/ElevenLabs
    unavailable. Nothing may crash or show a blank screen.
14. Keyboard: Space/Enter hold-to-talk works when the orb is focused; visible focus rings; `aria-live`
    announcements for state changes and new answers; all icon buttons have labels.
15. Add a hidden-by-default **latency panel** (toggle with `?debug=1` or a keyboard shortcut) that renders
    `LepiusResponse.timings_ms` — useful for the demo narrative.
16. Keep `lib/mockApi.ts` in sync with any UI you add so mock mode demos the same flows.

## Rules & conventions

- **No business logic in components.** Components render props. Flow logic lives in hooks; pure logic in
  `lib/` with vitest tests. Components never call `fetch` — only `api` via hooks.
- Strict types; no `any`; no non-null assertions unless provably safe.
- Match existing style: `cn()` helper, token colors (`bg-card`, `text-muted-foreground`, …) rather than
  raw hex, `lucide-react` icons, framer-motion for motion.
- `localStorage` only for per-viewer conveniences, always wrapped in try/catch.
- Do not add new heavy dependencies (state libraries, UI kits) without team agreement. shadcn components
  may be added via the `components.json` config.
- Do not remove the "synthetic / fictional / not medical advice" messaging.

## Contract changes

If you need a field the API doesn't return: **do not** invent it in `types.ts`. Write the proposed change
(endpoint, field, type, example) at the top of `docs/API.md` under a "Proposed" heading, tell the team,
and meanwhile mock it in `lib/mockApi.ts` behind the same type. Backend member C implements it; then both
sides update in one PR.

## Definition of done (per task and overall)

- `cd frontend && npm run lint && npm run typecheck && npm run test && npm run build` all pass.
- The full script in `docs/DEMO_FLOW.md` works in the browser against the real backend (mock AI/voice) and
  in `NEXT_PUBLIC_USE_MOCK_API=true` mode. Verify in a browser, desktop and a ~375px-wide viewport,
  including keyboard-only use of the orb.
- No console errors or React warnings during the demo flow.
- Small commits on `feature/frontend-lepius`, each scoped to one task, with a clear message.

When you finish each priority, report: what changed (files), how you verified it (commands + what you
saw in the browser), any contract proposals, and anything left as `TODO(frontend)`.
