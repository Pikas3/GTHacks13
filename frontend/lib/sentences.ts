/** Split answer copy into sentences so the UI can fade each one in. */
export function splitSentences(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  // Only break on terminators followed by whitespace so "v2.0" or "1.5 mg" stay intact.
  return trimmed
    .split(/(?<=[.!?]["']?)\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}
