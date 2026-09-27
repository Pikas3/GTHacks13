"use client";

/**
 * Orchestrates one Lepius conversation on the client:
 * record -> transcribe -> query -> (speak) -> idle, plus text fallback and source opens.
 * Components render state from this hook; they contain no pipeline logic.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { useWakeWord } from "@/hooks/useWakeWord";
import { recordTiming, summarizeTimings, timedAsync } from "@/lib/audio/metrics";
import { playObjectUrl, playPlaceholder, playSpeechResponse, stopActivePlayback } from "@/lib/audio/player";
import { rmsLevelFromTimeDomain } from "@/lib/audioLevel";
import { api, ApiError } from "@/lib/api";
import { orbTransition, type OrbEvent } from "@/lib/orbMachine";
import type { LepiusResponse, EvidenceReference, InputMode, OrbState } from "@/lib/types";

function startLevelMeter(analyser: AnalyserNode, onLevel: (level: number) => void): () => void {
  const buf = new Uint8Array(analyser.fftSize);
  let raf = 0;
  let stopped = false;
  const tick = () => {
    if (stopped) return;
    analyser.getByteTimeDomainData(buf);
    onLevel(rmsLevelFromTimeDomain(buf));
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return () => {
    stopped = true;
    cancelAnimationFrame(raf);
  };
}

function toApiError(e: unknown): ApiError {
  return e instanceof ApiError ? e : new ApiError("INTERNAL_ERROR", e instanceof Error ? e.message : String(e));
}

export interface ConversationOptions {
  /** Called after each recorded interaction so profile/timeline views can refresh. */
  onInteraction?: () => void;
}

export function useConversation(hcpId: string | null, { onInteraction }: ConversationOptions = {}) {
  const recorder = useAudioRecorder();
  const [state, setState] = useState<OrbState>("idle");
  const [transcript, setTranscript] = useState<string>("");
  const [response, setResponse] = useState<LepiusResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [speechEnabled, setSpeechEnabled] = useState(true);
  const [latencyMs, setLatencyMs] = useState<Partial<Record<"stt" | "query" | "tts_ttfa", number>>>({});
  const [audioLevel, setAudioLevel] = useState(0);
  const [hasLiveAudio, setHasLiveAudio] = useState(false);

  const sessionIdRef = useRef<string | null>(null);
  const speakGenRef = useRef(0);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const stopMeterRef = useRef<(() => void) | null>(null);
  const heldRef = useRef(false);

  const send = useCallback((event: OrbEvent) => setState((s) => orbTransition(s, event)), []);

  const refreshLatency = useCallback(() => {
    const s = summarizeTimings();
    setLatencyMs({ stt: s.stt, query: s.query, tts_ttfa: s.tts_ttfa });
  }, []);

  const unlockAudio = useCallback(() => {
    if (typeof window === "undefined") return;
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return;
    if (!audioCtxRef.current) audioCtxRef.current = new Ctor();
    if (audioCtxRef.current.state === "suspended") void audioCtxRef.current.resume();
  }, []);

  const clearMeter = useCallback(() => {
    stopMeterRef.current?.();
    stopMeterRef.current = null;
    setHasLiveAudio(false);
    setAudioLevel(0);
  }, []);

  const stopSpeaking = useCallback(() => {
    speakGenRef.current += 1;
    clearMeter();
    stopActivePlayback();
    send({ type: "SPEECH_ENDED" });
  }, [clearMeter, send]);

  const attachMeter = useCallback(
    (audio: HTMLAudioElement) => {
      clearMeter();
      const ctx = audioCtxRef.current;
      if (!ctx) return;
      try {
        if (ctx.state === "suspended") void ctx.resume();
        const source = ctx.createMediaElementSource(audio);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 1024;
        analyser.smoothingTimeConstant = 0.72;
        source.connect(analyser);
        analyser.connect(ctx.destination);
        setHasLiveAudio(true);
        stopMeterRef.current = startLevelMeter(analyser, setAudioLevel);
      } catch {
        setHasLiveAudio(false);
      }
    },
    [clearMeter],
  );

  // New HCP => new conversation; stop any in-flight audio.
  useEffect(() => {
    sessionIdRef.current = null;
    speakGenRef.current += 1;
    heldRef.current = false;
    clearMeter();
    stopActivePlayback();
    /* eslint-disable react-hooks/set-state-in-effect */
    setResponse(null);
    setTranscript("");
    setError(null);
    setState("idle");
    setLatencyMs({});
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [hcpId, clearMeter]);

  useEffect(
    () => () => {
      clearMeter();
      stopActivePlayback();
    },
    [clearMeter],
  );

  const fail = useCallback(
    (e: unknown) => {
      setError(toApiError(e));
      send({ type: "FAIL" });
    },
    [send],
  );

  const speak = useCallback(
    async (text: string) => {
      const gen = ++speakGenRef.current;
      clearMeter();
      try {
        const t0 = performance.now();
        const markTtfa = () => {
          recordTiming("tts_ttfa", performance.now() - t0);
          refreshLatency();
        };
        try {
          const handle = await api.createSpeech(text);
          if (gen !== speakGenRef.current) return;
          if (handle.is_placeholder) {
            markTtfa();
            await playPlaceholder();
          } else {
            const res = await api.streamSpeech(handle.speech_id);
            if (gen !== speakGenRef.current) return;
            await playSpeechResponse(res, {
              onFirstByte: markTtfa,
              onAudio: attachMeter,
            });
          }
        } catch {
          const speech = await timedAsync("tts_total", () => api.synthesize(text));
          if (gen !== speakGenRef.current) return;
          markTtfa();
          if (!speech.url) await playPlaceholder();
          else await playObjectUrl(speech.url, { onAudio: attachMeter });
        }
        if (gen === speakGenRef.current) {
          clearMeter();
          send({ type: "SPEECH_ENDED" });
        }
      } catch (e) {
        if (gen === speakGenRef.current) {
          setError(toApiError(e));
          clearMeter();
          send({ type: "SPEECH_ENDED" });
        }
      }
    },
    [send, refreshLatency, clearMeter, attachMeter],
  );

  const ask = useCallback(
    async (query: string, mode: InputMode) => {
      if (!hcpId || !query.trim()) return;
      setTranscript(query);
      setError(null);
      try {
        const res = await timedAsync("query", () =>
          api.query({ hcp_id: hcpId, session_id: sessionIdRef.current, query, input_mode: mode }),
        );
        refreshLatency();
        sessionIdRef.current = res.session_id;
        setResponse(res);
        send({ type: "ANSWERED", willSpeak: speechEnabled });
        onInteraction?.();
        if (speechEnabled) void speak(res.response.speech_text);
      } catch (e) {
        const err = toApiError(e);
        if (err.code === "INVALID_SESSION") sessionIdRef.current = null;
        fail(err);
      }
    },
    [hcpId, onInteraction, send, speak, speechEnabled, fail, refreshLatency],
  );

  const finishUtterance = useCallback(
    async (blob: Blob | null) => {
      if (!blob) {
        send({ type: "CANCEL" });
        return;
      }
      send({ type: "RELEASE" });
      try {
        const result = await timedAsync("stt", () => api.transcribe(blob));
        refreshLatency();
        setTranscript(result.text);
        send({ type: "TRANSCRIBED" });
        await ask(result.text, "voice");
      } catch (e) {
        fail(e);
      }
    },
    [send, ask, fail, refreshLatency],
  );

  /** Push-to-talk: pointer down. */
  const pressStart = useCallback(async () => {
    if (!hcpId || heldRef.current) return;
    heldRef.current = true;
    unlockAudio();
    speakGenRef.current += 1;
    clearMeter();
    stopActivePlayback();
    setError(null);
    send({ type: "PRESS" });
    const ok = await recorder.start();
    if (!ok) {
      heldRef.current = false;
      fail(new ApiError("AUDIO_TRANSCRIPTION_FAILED", "Microphone unavailable — use the text box instead."));
      return;
    }
    if (!heldRef.current) {
      await recorder.stop();
      send({ type: "CANCEL" });
      return;
    }
    send({ type: "PERMISSION_GRANTED" });
  }, [hcpId, recorder, send, fail, unlockAudio, clearMeter]);

  /** Push-to-talk: pointer up. */
  const pressEnd = useCallback(async () => {
    if (!heldRef.current) return;
    heldRef.current = false;
    const blob = await recorder.stop();
    await finishUtterance(blob);
  }, [recorder, finishUtterance]);

  // Hands-free: silence / max-duration auto-stop finishes the utterance after wake word.
  useEffect(() => {
    recorder.setOnAutoStop((blob) => {
      if (!heldRef.current) return;
      heldRef.current = false;
      void finishUtterance(blob);
    });
    return () => recorder.setOnAutoStop(null);
  }, [recorder, finishUtterance]);

  const onWake = useCallback(() => {
    if (!hcpId || heldRef.current || (state !== "idle" && state !== "error" && state !== "speaking")) return;
    void pressStart();
  }, [hcpId, state, pressStart]);

  const wake = useWakeWord({
    enabled: Boolean(hcpId) && (state === "idle" || state === "error"),
    onWake,
  });

  const submitText = useCallback(
    async (query: string) => {
      unlockAudio();
      speakGenRef.current += 1;
      clearMeter();
      stopActivePlayback();
      send({ type: "SUBMIT_TEXT" });
      await ask(query, "text");
    },
    [send, ask, unlockAudio, clearMeter],
  );

  /** Record SOURCE_OPEN engagement when the HCP opens an evidence source. */
  const openSource = useCallback(
    async (ev: EvidenceReference) => {
      if (!hcpId) return;
      try {
        await api.recordEvent({
          hcp_id: hcpId,
          session_id: sessionIdRef.current,
          event_type: "SOURCE_OPEN",
          resource_id: ev.resource_id,
          topic: response?.context.active_topic ?? null,
        });
        onInteraction?.();
      } catch {
        /* non-critical */
      }
    },
    [hcpId, onInteraction, response],
  );

  return {
    state,
    transcript,
    response,
    error,
    speechEnabled,
    setSpeechEnabled,
    pressStart,
    pressEnd,
    submitText,
    stopSpeaking,
    openSource,
    /** Live mic level 0–1 while recording (for VoiceOrb waveform). */
    level: recorder.level,
    /** Last measured client latencies (ms) for STT / query / TTS time-to-first-audio. */
    latencyMs,
    audioLevel,
    hasLiveAudio,
    /** Browser supports SpeechRecognition wake phrase. */
    wakeSupported: wake.supported,
    /** Wake-word mic is actively listening for "hey Lepius". */
    wakeListening: wake.listening,
  };
}
