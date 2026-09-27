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

  it("matches common mis-transcriptions of Lepius", () => {
    expect(matchesWakePhrase("hey lepus")).toBe(true);
    expect(matchesWakePhrase("Hey, Lee Pius")).toBe(true);
    expect(matchesWakePhrase("okay leap us")).toBe(true);
    expect(matchesWakePhrase("hi lupus")).toBe(true);
    expect(matchesWakePhrase("Hey leap years")).toBe(true);
    expect(matchesWakePhrase("lepidus")).toBe(true);
  });

  it("does not fire on sound-alikes without a greeting mid-sentence", () => {
    expect(matchesWakePhrase("what about a lupus patient")).toBe(false);
    expect(matchesWakePhrase("hey leap using the guide")).toBe(false);
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
