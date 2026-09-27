import { describe, expect, it } from "vitest";

import { matchesWakePhrase, normalizeWakeTranscript } from "@/lib/wakeWord";

describe("wakeWord", () => {
  it("matches hey lepius variants", () => {
    expect(matchesWakePhrase("hey Lepius")).toBe(true);
    expect(matchesWakePhrase("Hey lepius,")).toBe(true);
    expect(matchesWakePhrase("ok lepius")).toBe(true);
    expect(matchesWakePhrase("hello lepius")).toBe(true);
    expect(matchesWakePhrase("heylepius")).toBe(true);
  });

  it("rejects unrelated speech", () => {
    expect(matchesWakePhrase("what's new with Novara")).toBe(false);
    expect(matchesWakePhrase("hey Alexa")).toBe(false);
    expect(matchesWakePhrase("")).toBe(false);
  });

  it("normalizes punctuation", () => {
    expect(normalizeWakeTranscript("  Hey,  Lepius! ")).toBe("hey lepius");
  });
});
