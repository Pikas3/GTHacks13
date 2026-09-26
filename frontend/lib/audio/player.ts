/**
 * Audio playback helpers for Ambient TTS.
 *
 * - `playObjectUrl`: buffered MP3/WAV (fallback; works everywhere).
 * - `playSpeechResponse`: consume a streaming GET body into a Blob URL, then play.
 *
 * Only one clip plays at a time; call `stopActivePlayback` on barge-in / HCP switch.
 */

let activeAudio: HTMLAudioElement | null = null;
let activeUrl: string | null = null;
let activeAbort: AbortController | null = null;

export type PlayOptions = {
  onAudio?: (audio: HTMLAudioElement) => void;
  onFirstByte?: () => void;
};

export function stopActivePlayback(): void {
  activeAbort?.abort();
  activeAbort = null;
  if (activeAudio) {
    activeAudio.onended = null;
    activeAudio.onerror = null;
    activeAudio.pause();
    activeAudio.src = "";
    activeAudio = null;
  }
  if (activeUrl) {
    URL.revokeObjectURL(activeUrl);
    activeUrl = null;
  }
}

function attach(audio: HTMLAudioElement, url: string | null, opts?: PlayOptions): Promise<void> {
  stopActivePlayback();
  activeAudio = audio;
  activeUrl = url;
  opts?.onAudio?.(audio);
  return new Promise((resolve, reject) => {
    audio.onended = () => {
      if (activeUrl) URL.revokeObjectURL(activeUrl);
      activeUrl = null;
      activeAudio = null;
      resolve();
    };
    audio.onerror = () => {
      stopActivePlayback();
      reject(new Error("Audio playback failed"));
    };
    void audio.play().catch((err) => {
      stopActivePlayback();
      reject(err);
    });
  });
}

export async function playObjectUrl(url: string, opts?: PlayOptions): Promise<void> {
  const audio = new Audio(url);
  return attach(audio, url, opts);
}

export async function playPlaceholder(ms = 1600): Promise<void> {
  stopActivePlayback();
  await new Promise<void>((resolve) => {
    const id = window.setTimeout(resolve, ms);
    activeAbort = new AbortController();
    activeAbort.signal.addEventListener("abort", () => {
      window.clearTimeout(id);
      resolve();
    });
  });
}

/**
 * Fetch a streaming speech response into memory and play.
 * Reports `onFirstByte` when the first chunk arrives (network TTFA).
 */
export async function playSpeechResponse(
  res: Response,
  opts?: PlayOptions,
): Promise<{ provider: string; isPlaceholder: boolean }> {
  const provider = res.headers.get("x-tts-provider") ?? "unknown";
  const isPlaceholder = res.headers.get("x-tts-placeholder") === "true";
  if (isPlaceholder || !res.body) {
    opts?.onFirstByte?.();
    await playPlaceholder();
    return { provider, isPlaceholder: true };
  }

  const reader = res.body.getReader();
  const chunks: BlobPart[] = [];
  let first = true;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      if (first) {
        first = false;
        opts?.onFirstByte?.();
      }
      chunks.push(value);
    }
  }
  const mime = res.headers.get("content-type") || "audio/mpeg";
  const blob = new Blob(chunks, { type: mime });
  const url = URL.createObjectURL(blob);
  await playObjectUrl(url, opts);
  return { provider, isPlaceholder: false };
}

/** Optional MediaSource path for earlier start on Chromium; falls back to full buffer. */
export function canUseMediaSource(mime = 'audio/mpeg; codecs="mp3"'): boolean {
  return typeof MediaSource !== "undefined" && MediaSource.isTypeSupported(mime);
}
