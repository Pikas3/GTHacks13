import { describe, expect, it } from "vitest";

import { levelFromRms, rmsFromTimeDomain, shouldAutoStopOnSilence } from "@/lib/audio/silenceDetect";
import { clearTimings, getTimings, recordTiming, summarizeTimings } from "@/lib/audio/metrics";

describe("silenceDetect", () => {
  it("computes RMS from a flat mid buffer as near-zero", () => {
    const samples = Uint8Array.from({ length: 128 }, () => 128);
    expect(rmsFromTimeDomain(samples)).toBeCloseTo(0, 5);
    expect(levelFromRms(0)).toBe(0);
  });

  it("auto-stops only after min speech + sustained silence", () => {
    expect(
      shouldAutoStopOnSilence({ elapsedMs: 200, silentMs: 2000, rms: 0.001 }),
    ).toBe(false);
    expect(
      shouldAutoStopOnSilence({ elapsedMs: 1200, silentMs: 2000, rms: 0.001 }),
    ).toBe(true);
    expect(
      shouldAutoStopOnSilence({ elapsedMs: 1200, silentMs: 2000, rms: 0.05 }),
    ).toBe(false);
  });
});

describe("metrics", () => {
  it("records and summarizes stage timings", () => {
    clearTimings();
    recordTiming("stt", 120);
    recordTiming("query", 340);
    recordTiming("tts_ttfa", 80);
    expect(summarizeTimings()).toEqual({ stt: 120, query: 340, tts_ttfa: 80 });
    expect(getTimings()).toHaveLength(3);
  });
});
