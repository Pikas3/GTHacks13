"use client";

import { AnimatePresence, motion } from "framer-motion";
import { FileText, X } from "lucide-react";

import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Skeleton } from "@/components/ui/skeleton";
import { useResource } from "@/hooks/useResource";
import type { EvidenceReference } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

export interface EvidenceDrawerProps {
  evidence: EvidenceReference[];
  highlightedId: string | null;
  openSource: EvidenceReference | null;
  onViewSource: (e: EvidenceReference) => void;
  onCloseSource: () => void;
}

/**
 * Bottom evidence rail + full-source viewer.
 * TODO(frontend): focus trap + Esc to close in SourceViewer; scroll the cited chunk into view.
 */
export function EvidenceDrawer({ evidence, highlightedId, openSource, onViewSource, onCloseSource }: EvidenceDrawerProps) {
  return (
    <>
      <section aria-label="Evidence" className={cn("w-full transition-opacity", evidence.length === 0 && "opacity-0")}>
        <div className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          <FileText className="h-3.5 w-3.5" /> Evidence from approved resources
        </div>
        <div className="flex gap-3 overflow-x-auto pb-2">
          {evidence.map((e) => (
            <EvidenceCard key={e.chunk_id} evidence={e} highlighted={highlightedId === e.id} onViewSource={onViewSource} />
          ))}
        </div>
      </section>
      <AnimatePresence>{openSource && <SourceViewer evidence={openSource} onClose={onCloseSource} />}</AnimatePresence>
    </>
  );
}

function SourceViewer({ evidence, onClose }: { evidence: EvidenceReference; onClose: () => void }) {
  const { resource, error } = useResource(evidence.resource_id);
  return (
    <motion.div
      className="fixed inset-0 z-50 flex justify-end bg-black/50"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.aside
        role="dialog"
        aria-label={`Source: ${evidence.title}`}
        className="h-full w-full max-w-xl overflow-y-auto border-l bg-background p-6"
        initial={{ x: 60 }}
        animate={{ x: 0 }}
        exit={{ x: 60 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{evidence.title}</h2>
            <p className="text-sm text-muted-foreground">
              v{evidence.version} · published {formatDate(evidence.published_at)} · synthetic resource
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close source" className="rounded-full p-1 hover:bg-muted">
            <X className="h-5 w-5" />
          </button>
        </div>
        <ErrorBanner error={error} />
        {!resource && !error && <Skeleton className="h-40 w-full" />}
        {resource?.chunks.map((c) => (
          <div
            key={c.id}
            className={cn("mb-3 rounded-xl p-3", c.id === evidence.chunk_id ? "bg-primary/10 ring-1 ring-primary/40" : "bg-muted/40")}
          >
            <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{c.section}</p>
            <p className="text-sm leading-relaxed">{c.text}</p>
          </div>
        ))}
      </motion.aside>
    </motion.div>
  );
}
