"use client";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { HCPInterest } from "@/lib/types";

/** Topic affinity scores (0–1). Single series → single hue, no legend; tooltip on hover. */
export function InterestChart({ interests }: { interests: HCPInterest[] }) {
  const data = interests.slice(0, 8).map((i) => ({ entity: i.entity, score: Number(i.score.toFixed(2)), count: i.interaction_count }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Topic affinity</CardTitle>
      </CardHeader>
      <CardContent className="h-72">
        {data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No affinities yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={6}>
              <XAxis type="number" domain={[0, 1]} tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="entity" width={130} tick={{ fill: "var(--foreground)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: "var(--muted)", opacity: 0.4 }}
                contentStyle={{ background: "var(--background)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                formatter={(v) => [String(v), "affinity"]}
              />
              <Bar dataKey="score" fill="var(--primary)" radius={[0, 4, 4, 0]} maxBarSize={14} isAnimationActive />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
