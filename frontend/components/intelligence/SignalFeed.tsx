"use client";

import { AnimatePresence, motion } from "framer-motion";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { EngagementSignal } from "@/lib/types";

/** Structured engagement signals produced by Lepius interactions (hackathon scoring heuristic). */
export function SignalFeed({ signals }: { signals: EngagementSignal[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent structured signals</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {signals.length === 0 && <p className="text-sm text-muted-foreground">Ask something in Lepius to generate signals.</p>}
        <AnimatePresence initial={false}>
          {signals.slice(0, 10).map((s, i) => (
            <motion.div
              key={`${s.timestamp}-${s.entity}-${i}`}
              layout
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center justify-between gap-2 rounded-xl bg-muted/40 px-3 py-2 text-sm"
            >
              <div className="flex min-w-0 items-center gap-2">
                <Badge variant="outline">{s.event_type}</Badge>
                <span className="truncate font-medium">{s.entity}</span>
                {s.topic && s.topic !== s.entity && <span className="truncate text-xs text-muted-foreground">· {s.topic}</span>}
              </div>
              <span className="shrink-0 text-xs text-success">
                +{s.weight.toFixed(2)}
                {s.new_score != null && <span className="text-muted-foreground"> → {s.new_score.toFixed(2)}</span>}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
      </CardContent>
    </Card>
  );
}
