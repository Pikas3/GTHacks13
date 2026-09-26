import { describe, expect, it } from "vitest";

import { clamp01, rmsLevelFromTimeDomain } from "@/lib/audioLevel";

describe("clamp01", () => {
  it("clamps and treats non-finite as 0", () => {
    expect(clamp01(-1)).toBe(0);
    expect(clamp01(0.4)).toBe(0.4);
    expect(clamp01(2)).toBe(1);
    expect(clamp01(Number.NaN)).toBe(0);
  });
});

describe("rmsLevelFromTimeDomain", () => {
  it("returns 0 for silence and empty buffers", () => {
    expect(rmsLevelFromTimeDomain([])).toBe(0);
    expect(rmsLevelFromTimeDomain(new Uint8Array(16).fill(128))).toBe(0);
  });

  it("returns a high level for full-scale oscillation", () => {
    const bytes = Uint8Array.from({ length: 8 }, (_, i) => (i % 2 === 0 ? 0 : 255));
    expect(rmsLevelFromTimeDomain(bytes)).toBe(1);
  });

  it("is monotonic with amplitude", () => {
    const quiet = Uint8Array.from({ length: 8 }, (_, i) => (i % 2 === 0 ? 120 : 136));
    const loud = Uint8Array.from({ length: 8 }, (_, i) => (i % 2 === 0 ? 64 : 192));
    expect(rmsLevelFromTimeDomain(loud)).toBeGreaterThan(rmsLevelFromTimeDomain(quiet));
  });
});
