import { UserRound } from "lucide-react";

import type { HCP } from "@/lib/types";

export function HCPSelector({ hcps, selectedId, onSelect }: { hcps: HCP[]; selectedId: string | null; onSelect: (id: string) => void }) {
  return (
    <label className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm">
      <UserRound className="h-4 w-4 text-muted-foreground" />
      <span className="sr-only">Synthetic HCP profile</span>
      <select
        value={selectedId ?? ""}
        onChange={(e) => onSelect(e.target.value)}
        className="bg-transparent pr-1 outline-none"
        disabled={hcps.length === 0}
      >
        {hcps.length === 0 && <option value="">No HCPs — seed the DB</option>}
        {hcps.map((h) => (
          <option key={h.id} value={h.id} className="bg-background">
            {h.name} · {h.specialty}
          </option>
        ))}
      </select>
    </label>
  );
}
