"use client";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { EngagementSeries } from "@/lib/types";
import { formatDate } from "@/lib/utils";

/** Events per day from the interaction_event hypertable (Timescale time_bucket). */
export function EngagementChart({ series }: { series: EngagementSeries | null }) {
  const byDay = new Map<string, { day: string; events: number; topics: string[] }>();
  for (const p of series?.points ?? []) {
    const day = formatDate(p.bucket, { month: "short", day: "numeric" });
    const row = byDay.get(day) ?? { day, events: 0, topics: [] };
    row.events += p.event_count;
    row.topics.push(p.topic);
    byDay.set(day, row);
  }
  const data = [...byDay.values()];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Engagement over time</CardTitle>
      </CardHeader>
      <CardContent className="h-48">
        {data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No events yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ right: 8 }}>
              <XAxis dataKey="day" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} width={24} tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: "var(--muted)", opacity: 0.4 }}
                contentStyle={{ background: "var(--background)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                formatter={(v, _n, item) => [`${String(v)} events · ${(item.payload as { topics: string[] }).topics.join(", ")}`, ""]}
              />
              <Bar dataKey="events" fill="var(--primary)" radius={[4, 4, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
