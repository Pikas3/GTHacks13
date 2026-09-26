"use client";

/**
 * Continuous browser SpeechRecognition listening for the "hey Ambient" wake phrase.
 * Active only while `enabled` is true (typically orb idle). Stops cleanly on unmount.
 */
import { useEffect, useRef, useState } from "react";

import { matchesWakePhrase } from "@/lib/wakeWord";

type SpeechRec = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((ev: SpeechRecognitionEventLike) => void) | null;
  onerror: ((ev: { error: string }) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
};

function getSpeechRecognitionCtor(): (new () => SpeechRec) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRec;
    webkitSpeechRecognition?: new () => SpeechRec;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function isWakeWordSupported(): boolean {
  return getSpeechRecognitionCtor() != null;
}

export interface UseWakeWordOptions {
  enabled: boolean;
  onWake: () => void;
}

export function useWakeWord({ enabled, onWake }: UseWakeWordOptions) {
  const [supported] = useState(() => isWakeWordSupported());
  const [listening, setListening] = useState(false);
  const onWakeRef = useRef(onWake);
  onWakeRef.current = onWake;
  const armedRef = useRef(true);

  useEffect(() => {
    if (!enabled || !supported) {
      setListening(false);
      return;
    }

    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) return;

    let stopped = false;
    let rec: SpeechRec | null = null;
    armedRef.current = true;

    const start = () => {
      if (stopped) return;
      try {
        rec = new Ctor();
        rec.continuous = true;
        rec.interimResults = true;
        rec.lang = "en-US";
        rec.onresult = (ev) => {
          let chunk = "";
          for (let i = ev.resultIndex; i < ev.results.length; i += 1) {
            chunk += ev.results[i]![0]!.transcript;
          }
          if (!armedRef.current || !matchesWakePhrase(chunk)) return;
          armedRef.current = false;
          try {
            rec?.stop();
          } catch {
            /* ignore */
          }
          onWakeRef.current();
        };
        rec.onerror = (ev) => {
          // "no-speech" / "aborted" are normal; restart below via onend.
          if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
            stopped = true;
            setListening(false);
          }
        };
        rec.onend = () => {
          if (stopped) {
            setListening(false);
            return;
          }
          // Restart unless we just fired a wake (parent will disable `enabled`).
          window.setTimeout(() => {
            if (stopped || !armedRef.current) return;
            try {
              rec?.start();
              setListening(true);
            } catch {
              setListening(false);
            }
          }, 250);
        };
        rec.start();
        setListening(true);
      } catch {
        setListening(false);
      }
    };

    start();

    return () => {
      stopped = true;
      setListening(false);
      try {
        rec?.abort();
      } catch {
        try {
          rec?.stop();
        } catch {
          /* ignore */
        }
      }
    };
  }, [enabled, supported]);

  return { supported, listening };
}
