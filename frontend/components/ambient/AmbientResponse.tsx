"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Info, Sparkles } from "lucide-react";
import { Fragment } from "react";

import { CitationBadge } from "@/components/evidence/CitationBadge";
import { Badge } from "@/components/ui/badge";
import type { AmbientResponse as AmbientResponseT } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Renders answer text, turning [E1] markers into citation badges. */
function AnswerText({ text, onCite }: { text: string; onCite: (id: string) => void }) {
  const parts = text.split(/(\[E\d+\])/g);
  return (
    <p className="text-base leading-relaxed text-foreground/90">
      {parts.map((part, i) => {
        const m = /^\[(E\d+)\]$/.exec(part);
        return m ? <CitationBadge key={i} id={m[1]!} onClick={onCite} /> : <Fragment key={i}>{part}</Fragment>;
      })}
    </p>
  );
}

export interface AmbientResponseProps {
  response: AmbientResponseT | null;
  onCite: (evidenceId: string) => void;
  onFollowUp: (query: string) => void;
  disabled?: boolean;
}

export function AmbientResponse({ response, onCite, onFollowUp, disabled }: AmbientResponseProps) {
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
            response.response.insufficient_evidence && "border-warning/40",
          )}
        >
          {response.response.insufficient_evidence && (
            <div className="mb-3 flex items-center gap-2 text-xs text-warning">
              <Info className="h-3.5 w-3.5" /> Not covered by the available approved resources
            </div>
          )}
          <AnswerText text={response.response.text} onCite={onCite} />

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
