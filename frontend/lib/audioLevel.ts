/**
 * Pure amplitude helpers for the speaking-state waveform.
 * Web Audio wiring lives in useConversation; this file is unit-tested.
 */

const SILENCE = 128;

/** Clamp to [0, 1], treating NaN as 0. */
export function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.min(1, Math.max(0, n));
}

/**
 * Convert AnalyserNode time-domain bytes (0–255, 128 = silence) to a 0–1 RMS level.
 * Typical speech sits well below full-scale, so the result is scaled for a visible orb.
 */
export function rmsLevelFromTimeDomain(bytes: ArrayLike<number>): number {
  const n = bytes.length;
  if (n === 0) return 0;
  let sumSq = 0;
  for (let i = 0; i < n; i++) {
    const centered = ((bytes[i] ?? SILENCE) - SILENCE) / SILENCE;
    sumSq += centered * centered;
  }
  const rms = Math.sqrt(sumSq / n);
  return clamp01((rms - 0.02) / 0.35);
}
