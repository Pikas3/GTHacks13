"use client";

import { motion } from "framer-motion";
import { Eye, FileSearch, MessageSquare, Mic, PlayCircle } from "lucide-react";
import type { ComponentType } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { EventType, TimelineEntry } from "@/lib/types";
import { formatDate, isToday } from "@/lib/utils";

const ICON: Partial<Record<EventType, ComponentType<{ className?: string }>>> = {
  RESOURCE_VIEW: Eye,
  SOURCE_OPEN: FileSearch,
  VOICE_QUERY: Mic,
  TEXT_QUERY: MessageSquare,
  SESSION_STARTED: PlayCircle,
};

/** Persistent HCP memory, rendered as a dated timeline (newest first). */
export function InteractionTimeline({ entries, limit = 12 }: { entries: TimelineEntry[]; limit?: number }) {
  const items = entries.filter((e) => e.event_type !== "SESSION_STARTED").slice(0, limit);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Interaction timeline</CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 && <p className="text-sm text-muted-foreground">No interactions yet.</p>}
        <ol className="relative space-y-3 border-l border-border pl-5">
          {items.map((e) => {
            const Icon = ICON[e.event_type] ?? MessageSquare;
            return (
              <motion.li key={e.id} layout initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} className="relative">
                <span className="absolute -left-[27px] grid h-5 w-5 place-items-center rounded-full border border-border bg-background">
                  <Icon className="h-3 w-3 text-primary" />
                </span>
                <p className="text-xs text-muted-foreground">{isToday(e.timestamp) ? "Today" : formatDate(e.timestamp)}</p>
                <p className="text-sm leading-snug">{e.label}</p>
              </motion.li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
