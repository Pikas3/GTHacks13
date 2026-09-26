"use client";

/**
 * Orchestrates one Ambient conversation on the client:
 * record -> transcribe -> query -> (speak) -> idle, plus text fallback and source opens.
 * Components render state from this hook; they contain no pipeline logic.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { api, ApiError } from "@/lib/api";
import { rmsLevelFromTimeDomain } from "@/lib/audioLevel";
import { orbTransition, type OrbEvent } from "@/lib/orbMachine";
import type { AmbientResponse, EvidenceReference, InputMode, OrbState } from "@/lib/types";

const PLACEHOLDER_SPEAK_MS = 1600;

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
  const [response, setResponse] = useState<AmbientResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [speechEnabled, setSpeechEnabled] = useState(true);
  const sessionIdRef = useRef<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const stopMeterRef = useRef<(() => void) | null>(null);
  const heldRef = useRef(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [hasLiveAudio, setHasLiveAudio] = useState(false);

  const send = useCallback((event: OrbEvent) => setState((s) => orbTransition(s, event)), []);

  const unlockAudio = useCallback(() => {
    if (typeof window === "undefined") return;
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return;
    if (!audioCtxRef.current) audioCtxRef.current = new Ctor();
    if (audioCtxRef.current.state === "suspended") void audioCtxRef.current.resume();
  }, []);

  const clearPlayback = useCallback(() => {
    stopMeterRef.current?.();
    stopMeterRef.current = null;
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      const src = audio.src;
      audio.removeAttribute("src");
      audio.load();
      if (src.startsWith("blob:")) URL.revokeObjectURL(src);
    }
    audioRef.current = null;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setHasLiveAudio(false);
    setAudioLevel(0);
  }, []);

  const stopSpeaking = useCallback(() => {
    clearPlayback();
    send({ type: "SPEECH_ENDED" });
  }, [clearPlayback, send]);

  // New HCP => new conversation.
  useEffect(() => {
    sessionIdRef.current = null;
    // Resetting local conversation state when the selected HCP changes is intentional.
    /* eslint-disable react-hooks/set-state-in-effect */
    clearPlayback();
    setResponse(null);
    setTranscript("");
    setError(null);
    setState("idle");
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [hcpId, clearPlayback]);

  const fail = useCallback(
    (e: unknown) => {
      setError(toApiError(e));
      send({ type: "FAIL" });
    },
    [send],
  );

  const speak = useCallback(
    async (text: string) => {
      try {
        const speech = await api.synthesize(text);
        if (!speech.url) {
          setHasLiveAudio(false);
          timerRef.current = setTimeout(() => send({ type: "SPEECH_ENDED" }), PLACEHOLDER_SPEAK_MS);
          return;
        }
        const audio = new Audio(speech.url);
        audioRef.current = audio;
        const ctx = audioCtxRef.current;
        if (ctx) {
          try {
            if (ctx.state === "suspended") await ctx.resume();
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
        }
        audio.onended = () => {
          clearPlayback();
          send({ type: "SPEECH_ENDED" });
        };
        await audio.play();
      } catch (e) {
        // Voice failure is non-fatal: the answer is already on screen.
        setError(toApiError(e));
        clearPlayback();
        send({ type: "SPEECH_ENDED" });
      }
    },
    [clearPlayback, send],
  );

  const ask = useCallback(
    async (query: string, mode: InputMode) => {
      if (!hcpId || !query.trim()) return;
      setTranscript(query);
      setError(null);
      try {
        const res = await api.query({ hcp_id: hcpId, session_id: sessionIdRef.current, query, input_mode: mode });
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
    [hcpId, onInteraction, send, speak, speechEnabled, fail],
  );

  /** Push-to-talk: pointer down. */
  const pressStart = useCallback(async () => {
    if (!hcpId || heldRef.current) return;
    heldRef.current = true;
    unlockAudio();
    clearPlayback();
    setError(null);
    send({ type: "PRESS" });
    const ok = await recorder.start();
    if (!ok) {
      heldRef.current = false;
      fail(new ApiError("AUDIO_TRANSCRIPTION_FAILED", "Microphone unavailable — use the text box instead."));
    } else if (!heldRef.current) {
      // Released before the mic was ready: nothing useful was captured.
      await recorder.stop();
      send({ type: "CANCEL" });
    } else {
      send({ type: "PERMISSION_GRANTED" });
    }
  }, [hcpId, recorder, send, fail, unlockAudio, clearPlayback]);

  /** Push-to-talk: pointer up. Safe to call when nothing is held. */
  const pressEnd = useCallback(async () => {
    if (!heldRef.current) return;
    heldRef.current = false;
    const blob = await recorder.stop();
    if (!blob) return;
    send({ type: "RELEASE" });
    try {
      const result = await api.transcribe(blob);
      setTranscript(result.text);
      send({ type: "TRANSCRIBED" });
      await ask(result.text, "voice");
    } catch (e) {
      fail(e);
    }
  }, [recorder, send, ask, fail]);

  const submitText = useCallback(
    async (query: string) => {
      unlockAudio();
      clearPlayback();
      send({ type: "SUBMIT_TEXT" });
      await ask(query, "text");
    },
    [send, ask, unlockAudio, clearPlayback],
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

  useEffect(() => () => clearPlayback(), [clearPlayback]);

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
    audioLevel,
    hasLiveAudio,
  };
}
