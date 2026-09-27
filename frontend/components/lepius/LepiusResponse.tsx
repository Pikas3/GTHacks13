"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Info, Sparkles } from "lucide-react";
import { Fragment } from "react";

import { CitationBadge } from "@/components/evidence/CitationBadge";
import { Badge } from "@/components/ui/badge";
import { splitSentences } from "@/lib/sentences";
import type { LepiusResponse as LepiusResponseT } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Renders answer text, turning [E1] markers into citation badges. */
function AnswerText({ text, onCite, animate }: { text: string; onCite: (id: string) => void; animate: boolean }) {
  const sentences = splitSentences(text);
  return (
    <div className="space-y-2">
      {sentences.map((sentence, si) => (
        <motion.p
          key={`${si}-${sentence.slice(0, 24)}`}
          className="text-base leading-relaxed text-foreground/90"
          initial={animate ? { opacity: 0, y: 8 } : false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: animate ? si * 0.12 : 0 }}
        >
          {sentence.split(/(\[E\d+\])/g).map((part, i) => {
            const m = /^\[(E\d+)\]$/.exec(part);
            return m ? <CitationBadge key={i} id={m[1]!} onClick={onCite} /> : <Fragment key={i}>{part}</Fragment>;
          })}
        </motion.p>
      ))}
    </div>
  );
}

export interface LepiusResponseProps {
  response: LepiusResponseT | null;
  onCite: (evidenceId: string) => void;
  onFollowUp: (query: string) => void;
  disabled?: boolean;
}

export function LepiusResponse({ response, onCite, onFollowUp, disabled }: LepiusResponseProps) {
  const insufficient = Boolean(response?.response.insufficient_evidence);
  return (
    <AnimatePresence mode="wait">
      {response && (
        <motion.section
          key={response.query + response.response.text}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          className={cn(
            "w-full max-w-2xl rounded-2xl border bg-card/60 p-5 backdrop-blur",
            insufficient && "border-border bg-muted/25",
          )}
        >
          {insufficient && (
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-border bg-background/40 px-3 py-1 text-xs text-muted-foreground">
              <Info className="h-3.5 w-3.5" /> Limited coverage — not in the approved resources
            </div>
          )}
          <AnswerText text={response.response.text} onCite={onCite} animate />

          {response.changes.flatMap((d) => d.changes).length > 0 && (
            <div className="mt-4 space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">What changed</p>
              {response.changes.map((d) =>
                d.changes.slice(0, 4).map((c) => (
                  <div key={`${d.resource}-${c.topic}`} className="flex items-center gap-2 text-sm">
                    <Badge variant={c.importance === "HIGH" ? "warning" : "outline"}>{c.change_type.toLowerCase()}</Badge>
                    <span className="text-foreground/80">
                      {c.topic} <span className="text-muted-foreground">· {d.resource} v{d.old_version} → v{d.new_version}</span>
                    </span>
                  </div>
                )),
              )}
            </div>
          )}

          {response.suggested_followups.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {response.suggested_followups.map((q) => (
                <button
                  key={q}
                  type="button"
                  disabled={disabled}
                  onClick={() => onFollowUp(q)}
                  className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition hover:border-primary hover:text-foreground disabled:opacity-50"
                >
                  <Sparkles className="h-3 w-3" /> {q}
                </button>
              ))}
            </div>
          )}
        </motion.section>
      )}
    </AnimatePresence>
  );
}
