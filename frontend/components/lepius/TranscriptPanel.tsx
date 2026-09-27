import { Badge } from "@/components/ui/badge";
import type { LepiusResponse } from "@/lib/types";

/** Latest HCP utterance plus how the system understood it. */
export function TranscriptPanel({ transcript, response }: { transcript: string; response: LepiusResponse | null }) {
  if (!transcript) {
    return <p className="text-center text-sm text-muted-foreground">Hold the orb (or press Space) and ask about an approved resource.</p>;
  }
  const understood = response && response.query === transcript ? response : null;
  return (
    <div className="flex flex-col items-center gap-2 text-center">
      <p className="text-lg font-medium text-foreground/90">“{transcript}”</p>
      {understood && (
        <div className="flex flex-wrap items-center justify-center gap-1.5">
          <Badge variant="accent">{understood.intent.replaceAll("_", " ").toLowerCase()}</Badge>
          {understood.entities.map((e) => (
            <Badge key={`${e.type}:${e.name}`} variant="outline">
              {e.name}
            </Badge>
          ))}
          {understood.resolved_query !== understood.query && (
            <span className="text-xs text-muted-foreground">→ {understood.resolved_query}</span>
          )}
        </div>
      )}
    </div>
  );
}
