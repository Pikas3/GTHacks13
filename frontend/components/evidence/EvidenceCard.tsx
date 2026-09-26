"use client";

import { motion } from "framer-motion";
import { ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { RESOURCE_TYPE_LABEL } from "@/lib/constants";
import type { EvidenceReference } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

export interface EvidenceCardProps {
  evidence: EvidenceReference;
  highlighted?: boolean;
  onViewSource: (evidence: EvidenceReference) => void;
}

export function EvidenceCard({ evidence: e, highlighted, onViewSource }: EvidenceCardProps) {
  return (
    <motion.article
      id={`evidence-${e.id}`}
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "flex w-72 shrink-0 flex-col gap-2 rounded-2xl border bg-card p-4 transition-shadow sm:w-80",
        highlighted && "ring-2 ring-primary",
      )}
    >
      <div className="flex items-center gap-1.5">
        <Badge>{e.id}</Badge>
        <Badge variant="outline">{RESOURCE_TYPE_LABEL[e.resource_type]}</Badge>
        {e.is_new && <Badge variant="success">New since last review</Badge>}
      </div>
      <div>
        <h4 className="font-semibold leading-snug">{e.title}</h4>
        <p className="text-xs text-muted-foreground">
          v{e.version} · {e.section ?? "General"} · {formatDate(e.published_at)}
        </p>
      </div>
      <p className="line-clamp-4 text-sm text-foreground/80">{e.excerpt}</p>
      <button
        type="button"
        onClick={() => onViewSource(e)}
        className="mt-auto inline-flex items-center gap-1 self-start text-xs font-medium text-primary hover:underline"
      >
        View source <ExternalLink className="h-3 w-3" />
      </button>
    </motion.article>
  );
}
