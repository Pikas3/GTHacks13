import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { HCPDetail } from "@/lib/types";

export function HCPProfile({ profile }: { profile: HCPDetail | null }) {
  if (!profile) return <Skeleton className="h-40 w-full rounded-2xl" />;
  return (
    <Card>
      <CardHeader>
        <CardTitle>HCP profile · synthetic</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <p className="text-xl font-semibold">{profile.name}</p>
          <p className="text-sm text-muted-foreground">
            {profile.specialty}
            {profile.organization && ` · ${profile.organization}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {profile.preferences.map((p) => (
            <Badge key={p.key} variant="outline" title={p.value}>
              {p.key.replaceAll("_", " ")}
            </Badge>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
