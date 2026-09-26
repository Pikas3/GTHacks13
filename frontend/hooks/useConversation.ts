"use client";

/**
 * Orchestrates one Ambient conversation on the client:
 * record -> transcribe -> query -> (speak) -> idle, plus text fallback and source opens.
 * Components render state from this hook; they contain no pipeline logic.
 *
 * Voice playback uses `lib/audio/player` (barge-in safe). Timings land in `lib/audio/metrics`
 * for a latency panel.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { summarizeTimings, timedAsync, recordTiming } from "@/lib/audio/metrics";
import { playObjectUrl, playPlaceholder, playSpeechResponse, stopActivePlayback } from "@/lib/audio/player";
import { api, ApiError } from "@/lib/api";
import { orbTransition, type OrbEvent } from "@/lib/orbMachine";
import type { AmbientResponse, EvidenceReference, InputMode, OrbState } from "@/lib/types";

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
  const [latencyMs, setLatencyMs] = useState<Partial<Record<"stt" | "query" | "tts_ttfa", number>>>({});
  const sessionIdRef = useRef<string | null>(null);
  const speakGenRef = useRef(0);

  const send = useCallback((event: OrbEvent) => setState((s) => orbTransition(s, event)), []);

  const refreshLatency = useCallback(() => {
    const s = summarizeTimings();
    setLatencyMs({ stt: s.stt, query: s.query, tts_ttfa: s.tts_ttfa });
  }, []);

  const stopSpeaking = useCallback(() => {
    speakGenRef.current += 1;
    stopActivePlayback();
    send({ type: "SPEECH_ENDED" });
  }, [send]);

  // New HCP => new conversation; stop any in-flight audio.
  useEffect(() => {
    sessionIdRef.current = null;
    speakGenRef.current += 1;
    stopActivePlayback();
    /* eslint-disable react-hooks/set-state-in-effect */
    setResponse(null);
    setTranscript("");
    setError(null);
    setState("idle");
    setLatencyMs({});
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [hcpId]);

  useEffect(() => () => stopActivePlayback(), []);

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
      try {
        const t0 = performance.now();
        try {
          const handle = await api.createSpeech(text);
          if (gen !== speakGenRef.current) return;
          if (handle.is_placeholder) {
            recordTiming("tts_ttfa", performance.now() - t0);
            refreshLatency();
            await playPlaceholder();
          } else {
            const res = await api.streamSpeech(handle.speech_id);
            if (gen !== speakGenRef.current) return;
            await playSpeechResponse(res, {
              onFirstByte: () => {
                recordTiming("tts_ttfa", performance.now() - t0);
                refreshLatency();
              },
            });
          }
        } catch {
          const speech = await timedAsync("tts_total", () => api.synthesize(text));
          if (gen !== speakGenRef.current) return;
          recordTiming("tts_ttfa", performance.now() - t0);
          refreshLatency();
          if (!speech.url) await playPlaceholder();
          else await playObjectUrl(speech.url);
        }
        if (gen === speakGenRef.current) send({ type: "SPEECH_ENDED" });
      } catch (e) {
        if (gen === speakGenRef.current) {
          setError(toApiError(e));
          send({ type: "SPEECH_ENDED" });
        }
      }
    },
    [send, refreshLatency],
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

  /** Push-to-talk: pointer down. */
  const pressStart = useCallback(async () => {
    if (!hcpId) return;
    stopSpeaking();
    setError(null);
    send({ type: "PRESS" });
    const ok = await recorder.start();
    if (ok) send({ type: "PERMISSION_GRANTED" });
    else fail(new ApiError("AUDIO_TRANSCRIPTION_FAILED", "Microphone unavailable — use the text box instead."));
  }, [hcpId, recorder, send, fail, stopSpeaking]);

  /** Push-to-talk: pointer up. */
  const pressEnd = useCallback(async () => {
    const blob = await recorder.stop();
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
  }, [recorder, send, ask, fail, refreshLatency]);

  const submitText = useCallback(
    async (query: string) => {
      stopSpeaking();
      send({ type: "SUBMIT_TEXT" });
      await ask(query, "text");
    },
    [send, ask, stopSpeaking],
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
  };
}
