import { describe, expect, it } from "vitest";

import { orbTransition } from "@/lib/orbMachine";
import type { OrbState } from "@/lib/types";

const run = (events: Parameters<typeof orbTransition>[1][], start: OrbState = "idle") =>
  events.reduce<OrbState>((s, e) => orbTransition(s, e), start);

describe("orbTransition", () => {
  it("walks the full voice loop", () => {
    expect(
      run([
        { type: "PRESS" },
        { type: "PERMISSION_GRANTED" },
        { type: "RELEASE" },
        { type: "TRANSCRIBED" },
        { type: "ANSWERED", willSpeak: true },
        { type: "SPEECH_ENDED" },
      ]),
    ).toBe("idle");
  });

  it("text fallback skips listening/transcribing", () => {
    expect(run([{ type: "SUBMIT_TEXT" }])).toBe("thinking");
    expect(run([{ type: "SUBMIT_TEXT" }, { type: "ANSWERED", willSpeak: false }])).toBe("idle");
  });

  it("ignores out-of-order events", () => {
    expect(run([{ type: "RELEASE" }])).toBe("idle");
    expect(run([{ type: "PRESS" }, { type: "SUBMIT_TEXT" }])).toBe("requesting_permission");
  });

  it("any failure goes to error and a new press recovers", () => {
    expect(run([{ type: "SUBMIT_TEXT" }, { type: "FAIL" }])).toBe("error");
    expect(run([{ type: "PRESS" }], "error")).toBe("requesting_permission");
  });

  it("pressing while speaking interrupts playback", () => {
    expect(run([{ type: "PRESS" }], "speaking")).toBe("requesting_permission");
  });
});
