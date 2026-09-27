import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ConversationContext as Ctx, TimelineEntry } from "@/lib/types";
import { formatDate } from "@/lib/utils";

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate text-right font-medium">{value ?? "—"}</span>
    </div>
  );
}

/** Right-hand context panel: what the assistant currently "has in mind" + relevant memory. */
export function ConversationContext({ context, timeline }: { context: Ctx | null; timeline: TimelineEntry[] }) {
  const reviews = timeline.filter((t) => t.event_type === "RESOURCE_VIEW" || t.event_type === "SOURCE_OPEN");
  const last = timeline.find((t) => t.event_type !== "SESSION_STARTED");
  return (
    <div className="flex flex-col gap-3">
      <Card>
        <CardHeader>
          <CardTitle>Conversation context</CardTitle>
        </CardHeader>
        <CardContent>
          <Row label="Active product" value={context?.active_entity} />
          <Row label="Active topic" value={context?.active_topic} />
          <Row label="Turns" value={context ? String(context.turn_count) : null} />
          <Row label="Last interaction" value={last ? `${formatDate(last.timestamp)} · ${last.label}` : null} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Previously reviewed</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {reviews.length === 0 && <p className="text-sm text-muted-foreground">No resources reviewed yet.</p>}
          {reviews.slice(0, 5).map((r) => (
            <div key={r.id} className="text-sm">
              <p className="font-medium leading-snug">{r.label.replace(/^(Viewed|Opened source:) /, "")}</p>
              <p className="text-xs text-muted-foreground">{formatDate(r.timestamp)}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
