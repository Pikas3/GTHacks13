"use client";

/**
 * Central push-to-talk orb. Visual only: state comes from useConversation.
 * Optional `level` (mic, 0–1) and `audioLevel` (TTS, 0–1) drive listening / speaking motion.
 */
import { motion, useReducedMotion, type TargetAndTransition } from "framer-motion";
import { Loader2, Mic, Sparkles, TriangleAlert } from "lucide-react";
import { useEffect, useState, type KeyboardEvent } from "react";

import { ListeningIndicator } from "@/components/ambient/ListeningIndicator";
import { ORB_STATE_LABEL } from "@/lib/constants";
import type { OrbState } from "@/lib/types";
import { cn } from "@/lib/utils";

const LISTENING_FILL_MS = 12_000;
const WAVE_WEIGHTS = [0.45, 0.75, 1, 0.7, 0.5];

const ORB_GRADIENT: Record<OrbState, string> = {
  idle: "from-cyan-400/80 via-sky-500/70 to-violet-500/70",
  requesting_permission: "from-slate-400/80 via-slate-500/70 to-indigo-500/60",
  listening: "from-emerald-300/90 via-cyan-400/80 to-sky-500/80",
  transcribing: "from-sky-300/80 via-indigo-400/70 to-blue-600/70",
  thinking: "from-violet-400/80 via-fuchsia-500/70 to-sky-500/70",
  speaking: "from-cyan-300/90 via-teal-400/80 to-emerald-400/80",
  error: "from-rose-400/80 via-rose-500/70 to-orange-400/70",
};

function orbAnimation(
  state: OrbState,
  reduced: boolean,
  micLevel: number,
  speakScale: number,
): TargetAndTransition {
  if (reduced) return { scale: 1 };
  const micBoost = 1 + Math.min(0.14, micLevel * 0.22);
  switch (state) {
    case "requesting_permission":
      return { opacity: [0.7, 1, 0.7], transition: { duration: 1.2, repeat: Infinity } };
    case "listening":
      return { scale: [1, 1.08 * micBoost, 1], transition: { duration: 1.1, repeat: Infinity } };
    case "thinking":
      return { scale: [1, 1.05, 1], transition: { duration: 1.6, repeat: Infinity } };
    case "transcribing":
      return { scale: 1 };
    case "speaking":
      return speakScale > 0
        ? { scale: 1 + 0.1 * speakScale, transition: { duration: 0.08 } }
        : { scale: [1, 1.04, 0.98, 1.05, 1], transition: { duration: 1.4, repeat: Infinity } };
    case "error":
      return { x: [0, -6, 6, -3, 0], transition: { duration: 0.4 } };
    default:
      return { scale: [1, 1.02, 1], transition: { duration: 4, repeat: Infinity } };
  }
}

function HoldRing({ progress, visible }: { progress: number; visible: boolean }) {
  const size = 224;
  const r = 104;
  const c = 2 * Math.PI * r;
  return (
    <svg
      aria-hidden
      viewBox={`0 0 ${size} ${size}`}
      className={cn(
        "pointer-events-none absolute h-[13.5rem] w-[13.5rem] -rotate-90 text-emerald-200 sm:h-[15.5rem] sm:w-[15.5rem]",
        visible ? "opacity-100" : "opacity-0",
      )}
    >
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeWidth="3" className="opacity-20" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - progress)}
      />
    </svg>
  );
}

function SpeakingWave({ level, live, reduced }: { level: number; live: boolean; reduced: boolean }) {
  return (
    <div className="relative flex h-10 items-end gap-1" aria-hidden>
      {WAVE_WEIGHTS.map((w, i) => (
        <motion.span
          key={i}
          className="w-1.5 rounded-full bg-white"
          animate={
            reduced
              ? { height: 10 }
              : live
                ? { height: 6 + w * 28 * Math.max(0.14, level) }
                : { height: [8, 8 + 24 * w, 10, 8 + 18 * w, 8] }
          }
          transition={live || reduced ? { duration: 0.08 } : { duration: 0.9, repeat: Infinity, delay: i * 0.07 }}
        />
      ))}
    </div>
  );
}

export interface VoiceOrbProps {
  state: OrbState;
  disabled?: boolean;
  /** Mic level 0–1 while listening (from the recorder analyser). */
  level?: number;
  /** TTS playback level 0–1 while speaking. */
  audioLevel?: number;
  hasLiveAudio?: boolean;
  /** Wake-word listener is armed (idle + browser support). */
  wakeListening?: boolean;
  errorMessage?: string | null;
  onPressStart: () => void;
  onPressEnd: () => void;
  onStopSpeaking: () => void;
}

export function VoiceOrb({
  state,
  disabled,
  level = 0,
  audioLevel = 0,
  hasLiveAudio = false,
  wakeListening = false,
  errorMessage,
  onPressStart,
  onPressEnd,
  onStopSpeaking,
}: VoiceOrbProps) {
  const reduced = useReducedMotion() ?? false;
  const holding = state === "listening" || state === "requesting_permission";
  const [holdProgress, setHoldProgress] = useState(0);
  const speakScale = state === "speaking" && hasLiveAudio && !reduced ? audioLevel : 0;
  const label = state === "error" && errorMessage ? errorMessage : ORB_STATE_LABEL[state];

  useEffect(() => {
    if (state !== "listening") return;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      setHoldProgress(reduced ? 1 : Math.min(1, (now - start) / LISTENING_FILL_MS));
      if (!reduced) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [state, reduced]);

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
        <motion.div
          aria-hidden
          className={cn("absolute h-72 w-72 rounded-full bg-gradient-to-br opacity-30 blur-3xl", ORB_GRADIENT[state])}
          animate={reduced ? undefined : { scale: holding ? 1.25 : state === "speaking" ? 1.12 : 1 }}
          transition={{ type: "spring", stiffness: 80 }}
        />
        <HoldRing progress={holdProgress} visible={state === "listening"} />
        <motion.button
          type="button"
          aria-label={
            state === "speaking"
              ? "Stop speaking"
              : 'Hold to ask, or say "hey Ambient"'
          }
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
          animate={orbAnimation(state, reduced, level, speakScale)}
          whileTap={{ scale: 0.97 }}
          className={cn(
            "relative grid h-48 w-48 touch-none select-none place-items-center rounded-full bg-gradient-to-br shadow-2xl outline-none focus-visible:ring-4 focus-visible:ring-primary/60 disabled:opacity-40 sm:h-56 sm:w-56",
            state === "listening" ? "ring-2 ring-emerald-200/70" : "ring-1 ring-white/20",
            ORB_GRADIENT[state],
          )}
        >
          <span className="absolute inset-3 rounded-full bg-background/10 backdrop-blur-sm" />
          <span className="relative text-white drop-shadow">
            {state === "speaking" ? (
              <SpeakingWave level={audioLevel} live={hasLiveAudio} reduced={reduced} />
            ) : state === "transcribing" ? (
              <Loader2 className="h-10 w-10 animate-spin" />
            ) : state === "thinking" ? (
              <Sparkles className="h-10 w-10" />
            ) : state === "error" ? (
              <TriangleAlert className="h-10 w-10" />
            ) : (
              <Mic className={cn("h-10 w-10", state === "requesting_permission" && "opacity-70")} />
            )}
          </span>
        </motion.button>
      </div>
      <div
        className="flex min-h-8 max-w-sm items-center justify-center gap-3 px-2 text-center text-sm text-muted-foreground"
        aria-live="polite"
      >
        <ListeningIndicator
          active={state === "listening" || state === "speaking"}
          tone={state === "speaking" ? "speaking" : "listening"}
          level={state === "speaking" && hasLiveAudio ? audioLevel : state === "listening" ? level : null}
          reduced={reduced}
        />
        <span>
          {label}
          {state === "idle" && wakeListening ? (
            <span className="mt-1 block text-xs text-emerald-600/90 dark:text-emerald-400/90">Wake word on</span>
          ) : null}
        </span>
      </div>
    </div>
  );
}
