import { describe, expect, it } from "vitest";

import { matchesWakePhrase, normalizeWakeTranscript } from "@/lib/wakeWord";

describe("wakeWord", () => {
  it("matches hey ambient variants", () => {
    expect(matchesWakePhrase("hey Ambient")).toBe(true);
    expect(matchesWakePhrase("Hey ambient,")).toBe(true);
    expect(matchesWakePhrase("ok ambient")).toBe(true);
    expect(matchesWakePhrase("hello ambient")).toBe(true);
    expect(matchesWakePhrase("heyambient")).toBe(true);
  });

  it("rejects unrelated speech", () => {
    expect(matchesWakePhrase("what's new with Novara")).toBe(false);
    expect(matchesWakePhrase("hey Alexa")).toBe(false);
    expect(matchesWakePhrase("")).toBe(false);
  });

  it("normalizes punctuation", () => {
    expect(normalizeWakeTranscript("  Hey,  Ambient! ")).toBe("hey ambient");
  });
});
