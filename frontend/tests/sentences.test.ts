import { describe, expect, it } from "vitest";

import { splitSentences } from "@/lib/sentences";

describe("splitSentences", () => {
  it("returns empty for blank input", () => {
    expect(splitSentences("")).toEqual([]);
    expect(splitSentences("   ")).toEqual([]);
  });

  it("keeps citation markers with their sentence", () => {
    expect(
      splitSentences(
        "Two updated resources are available [E1]. Key change: renal impairment guidance was added [E2].",
      ),
    ).toEqual([
      "Two updated resources are available [E1].",
      "Key change: renal impairment guidance was added [E2].",
    ]);
  });

  it("does not split inside version numbers or decimals", () => {
    expect(
      splitSentences("Novara Prescribing Information v2.0 [E1] is available. Dose is 1.5 mg."),
    ).toEqual(["Novara Prescribing Information v2.0 [E1] is available.", "Dose is 1.5 mg."]);
  });

  it("keeps a trailing fragment without a terminator", () => {
    expect(splitSentences("No approved resources cover that.")).toEqual(["No approved resources cover that."]);
    expect(splitSentences("Limited coverage")).toEqual(["Limited coverage"]);
  });
});
