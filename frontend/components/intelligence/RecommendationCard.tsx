import { Lightbulb } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RESOURCE_TYPE_LABEL } from "@/lib/constants";
import type { Recommendation } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export function RecommendationCard({ recommendations }: { recommendations: Recommendation[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <Lightbulb className="h-3.5 w-3.5" /> Recommended next resource
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {recommendations.length === 0 && <p className="text-sm text-muted-foreground">No recommendations yet.</p>}
        {recommendations.map((r) => (
          <div key={r.resource.id} className="rounded-xl bg-muted/40 p-3">
            <div className="flex items-center gap-1.5">
              <Badge variant="outline">{RESOURCE_TYPE_LABEL[r.resource.resource_type]}</Badge>
              <span className="text-xs text-muted-foreground">{formatDate(r.resource.published_at)}</span>
            </div>
            <p className="mt-1 font-medium">
              {r.resource.title} v{r.resource.version}
            </p>
            <p className="text-xs text-muted-foreground">{r.reason}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
