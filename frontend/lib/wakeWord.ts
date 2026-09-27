/** Wake-phrase matching for "hey Lepius" (browser SpeechRecognition transcripts). */

const WAKE_RE =
  /\b(?:hey|hi|hello|ok|okay)\s*[,.]?\s*lepius\b|\blepius\s*[,.]?\s*(?:hey|hi|hello)\b/i;

/** Normalize curly quotes / whitespace before matching. */
export function normalizeWakeTranscript(text: string): string {
  return text
    .toLowerCase()
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[^\p{L}\p{N}\s']/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** True when the transcript contains the Lepius wake phrase. */
export function matchesWakePhrase(text: string): boolean {
  const n = normalizeWakeTranscript(text);
  if (!n) return false;
  return WAKE_RE.test(n) || n === "lepius" || n.includes("heylepius");
}

export const WAKE_PHRASE_HINT = 'Say "hey Lepius"';
