"use client";

/**
 * Central push-to-talk orb. Visual only: state comes from useConversation.
 * Optional `level` (0–1) from the voice recorder analyser drives a subtle scale pulse.
 */
import { motion, useReducedMotion, type TargetAndTransition } from "framer-motion";
import { Loader2, Mic, Square, TriangleAlert } from "lucide-react";
import type { KeyboardEvent } from "react";

import { ListeningIndicator } from "@/components/ambient/ListeningIndicator";
import { ORB_STATE_LABEL } from "@/lib/constants";
import type { OrbState } from "@/lib/types";
import { cn } from "@/lib/utils";

const ORB_GRADIENT: Record<OrbState, string> = {
  idle: "from-cyan-400/80 via-sky-500/70 to-violet-500/70",
  requesting_permission: "from-slate-400/70 via-slate-500/60 to-slate-600/60",
  listening: "from-emerald-300/90 via-cyan-400/80 to-sky-500/80",
  transcribing: "from-sky-300/80 via-indigo-400/70 to-violet-500/70",
  thinking: "from-violet-400/80 via-fuchsia-500/70 to-sky-500/70",
  speaking: "from-cyan-300/90 via-teal-400/80 to-emerald-400/80",
  error: "from-rose-400/80 via-rose-500/70 to-orange-400/70",
};

function orbAnimation(state: OrbState, reduced: boolean, level = 0): TargetAndTransition {
  if (reduced) return { scale: 1 };
  const boost = 1 + Math.min(0.14, level * 0.22);
  switch (state) {
    case "listening":
      return { scale: [1, 1.08 * boost, 1], transition: { duration: 1.1, repeat: Infinity } };
    case "thinking":
    case "transcribing":
      return { rotate: 360, transition: { duration: 3, repeat: Infinity, ease: "linear" } };
    case "speaking":
      return { scale: [1, 1.04 * boost, 0.98, 1.05 * boost, 1], transition: { duration: 1.4, repeat: Infinity } };
    case "error":
      return { x: [0, -6, 6, -3, 0], transition: { duration: 0.4 } };
    default:
      return { scale: [1, 1.02, 1], transition: { duration: 4, repeat: Infinity } };
  }
}

export interface VoiceOrbProps {
  state: OrbState;
  disabled?: boolean;
  /** Optional 0–1 mic/TTS level from the voice workstream analyser. */
  level?: number;
  onPressStart: () => void;
  onPressEnd: () => void;
  onStopSpeaking: () => void;
}

export function VoiceOrb({ state, disabled, level = 0, onPressStart, onPressEnd, onStopSpeaking }: VoiceOrbProps) {
  const reduced = useReducedMotion() ?? false;
  const holding = state === "listening" || state === "requesting_permission";

  const onKeyDown = (e: KeyboardEvent) => {
    if ((e.key === " " || e.key === "Enter") && !e.repeat && !holding) {
      e.preventDefault();
      if (state === "speaking") onStopSpeaking();
      else onPressStart();
    }
  };
  const onKeyUp = (e: KeyboardEvent) => {
    if ((e.key === " " || e.key === "Enter") && holding) {
      e.preventDefault();
      onPressEnd();
    }
  };

  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative grid place-items-center">
        {/* halo */}
        <motion.div
          aria-hidden
          className={cn("absolute h-72 w-72 rounded-full bg-gradient-to-br opacity-30 blur-3xl", ORB_GRADIENT[state])}
          animate={reduced ? undefined : { scale: holding ? 1.25 : 1 }}
          transition={{ type: "spring", stiffness: 80 }}
        />
        <motion.button
          type="button"
          aria-label={state === "speaking" ? "Stop speaking" : "Hold to ask a question"}
          aria-pressed={holding}
          disabled={disabled}
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            if (state === "speaking") onStopSpeaking();
            else onPressStart();
          }}
          onPointerUp={() => holding && onPressEnd()}
          onPointerLeave={() => holding && onPressEnd()}
          onKeyDown={onKeyDown}
          onKeyUp={onKeyUp}
          animate={orbAnimation(state, reduced, level)}
          whileTap={{ scale: 0.97 }}
          className={cn(
            "relative grid h-48 w-48 touch-none select-none place-items-center rounded-full bg-gradient-to-br shadow-2xl ring-1 ring-white/20 outline-none focus-visible:ring-4 focus-visible:ring-primary/60 disabled:opacity-40 sm:h-56 sm:w-56",
            ORB_GRADIENT[state],
          )}
        >
          <span className="absolute inset-3 rounded-full bg-background/10 backdrop-blur-sm" />
          <span className="relative text-white drop-shadow">
            {state === "transcribing" || state === "thinking" ? (
              <Loader2 className="h-10 w-10 animate-spin" />
            ) : state === "speaking" ? (
              <Square className="h-9 w-9" />
            ) : state === "error" ? (
              <TriangleAlert className="h-10 w-10" />
            ) : (
              <Mic className="h-10 w-10" />
            )}
          </span>
        </motion.button>
      </div>
      <div className="flex h-8 items-center gap-3 text-sm text-muted-foreground" aria-live="polite">
        <ListeningIndicator active={state === "listening" || state === "speaking"} tone={state === "speaking" ? "speaking" : "listening"} />
        <span>{ORB_STATE_LABEL[state]}</span>
      </div>
    </div>
  );
}
