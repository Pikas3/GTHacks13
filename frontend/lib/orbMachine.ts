/**
 * Pure state machine for the voice interaction loop. Kept framework-free so it is unit
 * tested (tests/orbMachine.test.ts) and so components contain no business logic.
 *
 * idle -> requesting_permission -> listening -> transcribing -> thinking -> speaking -> idle
 *                                                     text input ─┘
 */
import type { OrbState } from "@/lib/types";

export type OrbEvent =
  | { type: "PRESS" }
  | { type: "PERMISSION_GRANTED" }
  | { type: "RELEASE" }
  | { type: "TRANSCRIBED" }
  | { type: "SUBMIT_TEXT" }
  | { type: "ANSWERED"; willSpeak: boolean }
  | { type: "SPEECH_ENDED" }
  | { type: "CANCEL" }
  | { type: "FAIL" }
  | { type: "RESET" };

export function orbTransition(state: OrbState, event: OrbEvent): OrbState {
  switch (event.type) {
    case "PRESS":
      return state === "idle" || state === "error" || state === "speaking" ? "requesting_permission" : state;
    case "PERMISSION_GRANTED":
      return state === "requesting_permission" ? "listening" : state;
    case "RELEASE":
      return state === "listening" ? "transcribing" : state;
    case "TRANSCRIBED":
      return state === "transcribing" ? "thinking" : state;
    case "SUBMIT_TEXT":
      return state === "idle" || state === "error" || state === "speaking" ? "thinking" : state;
    case "ANSWERED":
      return state === "thinking" ? (event.willSpeak ? "speaking" : "idle") : state;
    case "SPEECH_ENDED":
      return state === "speaking" ? "idle" : state;
    case "CANCEL":
      return state === "error" ? state : "idle";
    case "FAIL":
      return "error";
    case "RESET":
      return "idle";
  }
}

export const isBusy = (s: OrbState): boolean => s === "transcribing" || s === "thinking" || s === "requesting_permission";
