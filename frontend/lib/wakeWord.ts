/** Wake-phrase matching for "hey Lepius" (browser SpeechRecognition transcripts). */

/**
 * Browser speech recognition has no custom-vocabulary support, so "Lepius" (LEE-pee-us) comes
 * back as whatever real words it sounds like. Spaces inside a variant match optional whitespace.
 */
export const NAME_VARIANTS = [
  "lepius",
  "lepus",
  "leppius",
  "lepious",
  "lepias",
  "lepis",
  "lepidus",
  "leapius",
  "lipius",
  "lippius",
  "lapius",
  "lupus",
  "lee pius",
  "lee pious",
  "le pius",
  "lee pee us",
  "lepi us",
  "leap us",
  "leap yes",
  "leap years",
  "leap year",
  "halepias",
];

const GREETING = "(?:hey|hi|hello|ok|okay)";
const NAME = `(?:${NAME_VARIANTS.map((v) => v.replace(/ /g, "\\s*")).join("|")})`;

const WAKE_RE = new RegExp(
  `\\b${GREETING}\\s*${NAME}\\b|\\b${NAME}\\s*(?:hey|hi|hello)\\b|^${NAME}$`,
  "i",
);

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
  return WAKE_RE.test(n);
}

export const WAKE_PHRASE_HINT = 'Say "hey Lepius"';
