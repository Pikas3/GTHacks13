/**
 * Client-side latency timings for the Lepius voice path.
 * Consumed by a future latency panel (team A); safe to read anytime.
 */

export type VoiceStage = "stt" | "query" | "tts_ttfa" | "tts_total";

export interface VoiceTimingSample {
  stage: VoiceStage;
  ms: number;
  at: number;
}

const samples: VoiceTimingSample[] = [];
const MAX = 40;

export function recordTiming(stage: VoiceStage, ms: number): void {
  samples.push({ stage, ms, at: Date.now() });
  while (samples.length > MAX) samples.shift();
  if (typeof console !== "undefined" && console.debug) {
    console.debug(`[voice.latency] ${stage}=${Math.round(ms)}ms`);
  }
}

export function getTimings(): readonly VoiceTimingSample[] {
  return samples;
}

export function clearTimings(): void {
  samples.length = 0;
}

export function summarizeTimings(): Partial<Record<VoiceStage, number>> {
  const last: Partial<Record<VoiceStage, number>> = {};
  for (const s of samples) last[s.stage] = s.ms;
  return last;
}

/** Measure an async call with performance.now(). */
export async function timedAsync<T>(stage: VoiceStage, fn: () => Promise<T>): Promise<T> {
  const t0 = performance.now();
  try {
    return await fn();
  } finally {
    recordTiming(stage, performance.now() - t0);
  }
}
