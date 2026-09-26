/**
 * Pure RMS helpers for silence auto-stop / level metering.
 * Analyser wiring lives in useAudioRecorder; these stay unit-testable.
 */

export function rmsFromTimeDomain(samples: Uint8Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const centered = (samples[i]! - 128) / 128;
    sum += centered * centered;
  }
  return Math.sqrt(sum / samples.length);
}

/** Map RMS (0–~1) to a display level 0–1 with light compression. */
export function levelFromRms(rms: number): number {
  const clamped = Math.max(0, Math.min(1, rms * 3.2));
  return Number(clamped.toFixed(3));
}

/**
 * Decide whether trailing silence should auto-stop recording.
 * `silentMs` is how long RMS has stayed below `threshold`.
 */
export function shouldAutoStopOnSilence(opts: {
  elapsedMs: number;
  silentMs: number;
  minSpeechMs?: number;
  silenceDurationMs?: number;
  threshold?: number;
  rms: number;
}): boolean {
  const minSpeechMs = opts.minSpeechMs ?? 800;
  const silenceDurationMs = opts.silenceDurationMs ?? 1400;
  const threshold = opts.threshold ?? 0.02;
  if (opts.elapsedMs < minSpeechMs) return false;
  if (opts.rms >= threshold) return false;
  return opts.silentMs >= silenceDurationMs;
}
