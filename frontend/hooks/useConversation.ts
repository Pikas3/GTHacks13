"use client";

/**
 * Orchestrates one Ambient conversation on the client:
 * record -> transcribe -> query -> (speak) -> idle, plus text fallback and source opens.
 * Components render state from this hook; they contain no pipeline logic.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { api, ApiError } from "@/lib/api";
import { orbTransition, type OrbEvent } from "@/lib/orbMachine";
import type { AmbientResponse, EvidenceReference, InputMode, OrbState } from "@/lib/types";

const PLACEHOLDER_SPEAK_MS = 1600;

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

  const send = useCallback((event: OrbEvent) => setState((s) => orbTransition(s, event)), []);

  const stopSpeaking = useCallback(() => {
    audioRef.current?.pause();
    audioRef.current = null;
    if (timerRef.current) clearTimeout(timerRef.current);
    send({ type: "SPEECH_ENDED" });
  }, [send]);

  // New HCP => new conversation.
  useEffect(() => {
    sessionIdRef.current = null;
    audioRef.current?.pause();
    // Resetting local conversation state when the selected HCP changes is intentional.
    /* eslint-disable react-hooks/set-state-in-effect */
    setResponse(null);
    setTranscript("");
    setError(null);
    setState("idle");
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [hcpId]);

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
          timerRef.current = setTimeout(() => send({ type: "SPEECH_ENDED" }), PLACEHOLDER_SPEAK_MS);
          return;
        }
        const audio = new Audio(speech.url);
        audioRef.current = audio;
        audio.onended = () => {
          URL.revokeObjectURL(speech.url!);
          send({ type: "SPEECH_ENDED" });
        };
        await audio.play();
      } catch (e) {
        // Voice failure is non-fatal: the answer is already on screen.
        setError(toApiError(e));
        send({ type: "SPEECH_ENDED" });
      }
    },
    [send],
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
    if (!hcpId) return;
    audioRef.current?.pause();
    setError(null);
    send({ type: "PRESS" });
    const ok = await recorder.start();
    if (ok) send({ type: "PERMISSION_GRANTED" });
    else fail(new ApiError("AUDIO_TRANSCRIPTION_FAILED", "Microphone unavailable — use the text box instead."));
  }, [hcpId, recorder, send, fail]);

  /** Push-to-talk: pointer up. */
  const pressEnd = useCallback(async () => {
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
      audioRef.current?.pause();
      send({ type: "SUBMIT_TEXT" });
      await ask(query, "text");
    },
    [send, ask],
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
  };
}
