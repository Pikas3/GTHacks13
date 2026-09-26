"use client";

/**
 * Push-to-talk recording with MediaRecorder.
 * Owned by the voice workstream. Audio stays in memory and is only sent to /api/audio/transcribe.
 *
 * Public API stays backward compatible: `{ status, start(), stop(), level }`.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { levelFromRms, rmsFromTimeDomain, shouldAutoStopOnSilence } from "@/lib/audio/silenceDetect";

export type RecorderStatus = "idle" | "requesting_permission" | "recording" | "unsupported" | "denied";

const PREFERRED_MIME = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];
const MIN_MS = 300;
const MAX_MS = 30_000;

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return PREFERRED_MIME.find((m) => MediaRecorder.isTypeSupported(m));
}

export function useAudioRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [level, setLevel] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const maxTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafRef = useRef<number | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const stopResolverRef = useRef<((blob: Blob | null) => void) | null>(null);
  const onAutoStopRef = useRef<((blob: Blob | null) => void) | null>(null);
  const silentMsRef = useRef(0);
  const lastRafTsRef = useRef(0);

  const setOnAutoStop = useCallback((cb: ((blob: Blob | null) => void) | null) => {
    onAutoStopRef.current = cb;
  }, []);

  const releaseStream = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (maxTimerRef.current) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
    analyserRef.current = null;
    if (audioCtxRef.current) {
      void audioCtxRef.current.close().catch(() => undefined);
      audioCtxRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setLevel(0);
  }, []);

  useEffect(() => releaseStream, [releaseStream]);

  const finishRecording = useCallback(async (): Promise<Blob | null> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      releaseStream();
      setStatus("idle");
      return null;
    }
    const elapsed = performance.now() - startedAtRef.current;
    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () => resolve(new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }));
      try {
        recorder.stop();
      } catch {
        resolve(new Blob([], { type: "audio/webm" }));
      }
    });
    recorderRef.current = null;
    releaseStream();
    setStatus("idle");
    if (elapsed < MIN_MS || blob.size < 64) return null;
    return blob;
  }, [releaseStream]);

  const requestStop = useCallback(() => {
    void finishRecording().then((blob) => {
      const waiter = stopResolverRef.current;
      stopResolverRef.current = null;
      if (waiter) waiter(blob);
      else onAutoStopRef.current?.(blob);
    });
  }, [finishRecording]);

  const pumpLevels = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;
    const buf = new Uint8Array(analyser.fftSize);
    const tick = (ts: number) => {
      analyser.getByteTimeDomainData(buf);
      const rms = rmsFromTimeDomain(buf);
      setLevel(levelFromRms(rms));
      const dt = lastRafTsRef.current ? ts - lastRafTsRef.current : 16;
      lastRafTsRef.current = ts;
      if (rms < 0.02) silentMsRef.current += dt;
      else silentMsRef.current = 0;
      const elapsed = performance.now() - startedAtRef.current;
      if (
        shouldAutoStopOnSilence({
          elapsedMs: elapsed,
          silentMs: silentMsRef.current,
          rms,
        })
      ) {
        requestStop();
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [requestStop]);

  /** Request the mic (if needed) and start recording. Resolves false if unavailable/denied. */
  const start = useCallback(async (): Promise<boolean> => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setStatus("unsupported");
      return false;
    }
    setStatus("requesting_permission");
    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setStatus("denied");
      return false;
    }

    // AudioContext must be created/resumed inside the user gesture (orb press).
    try {
      const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new Ctx();
      await ctx.resume();
      const source = ctx.createMediaStreamSource(streamRef.current);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      audioCtxRef.current = ctx;
      analyserRef.current = analyser;
    } catch {
      /* level metering is optional */
    }

    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(streamRef.current, mimeType ? { mimeType } : undefined);
    chunksRef.current = [];
    silentMsRef.current = 0;
    lastRafTsRef.current = 0;
    startedAtRef.current = performance.now();
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onerror = () => requestStop();
    streamRef.current.getAudioTracks().forEach((track) => {
      track.onended = () => requestStop();
    });
    recorder.start(250);
    recorderRef.current = recorder;
    setStatus("recording");
    maxTimerRef.current = setTimeout(() => requestStop(), MAX_MS);
    pumpLevels();
    return true;
  }, [pumpLevels, requestStop]);

  /** Stop recording and return the captured audio (null if too short / nothing recorded). */
  const stop = useCallback(async (): Promise<Blob | null> => {
    if (stopResolverRef.current) {
      // Auto-stop already in flight
      return new Promise((resolve) => {
        const prev = stopResolverRef.current;
        stopResolverRef.current = (blob) => {
          prev?.(blob);
          resolve(blob);
        };
      });
    }
    return finishRecording();
  }, [finishRecording]);

  return { status, start, stop, level, setOnAutoStop };
}
