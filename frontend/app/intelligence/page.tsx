"use client";

import { RefreshCw } from "lucide-react";

import { HCPProfile } from "@/components/hcp/HCPProfile";
import { HCPSelector } from "@/components/hcp/HCPSelector";
import { InteractionTimeline } from "@/components/hcp/InteractionTimeline";
import { EngagementChart } from "@/components/intelligence/EngagementChart";
import { InterestChart } from "@/components/intelligence/InterestChart";
import { RecommendationCard } from "@/components/intelligence/RecommendationCard";
import { SignalFeed } from "@/components/intelligence/SignalFeed";
import { AppHeader } from "@/components/layout/AppHeader";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useHCP } from "@/hooks/useHCP";
import { useIntelligence } from "@/hooks/useIntelligence";

/**
 * Impiricus-facing view: what Ambient learned about this (synthetic) HCP.
 * TODO(frontend): live-update when Ambient records events (poll or SSE) instead of manual refresh.
 */
export default function IntelligencePage() {
  const hcp = useHCP();
  const intel = useIntelligence(hcp.selectedId);

  const refresh = () => {
    void hcp.refresh();
    void intel.refresh();
  };

  return (
    <main className="min-h-dvh">
      <AppHeader>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={refresh} aria-label="Refresh">
            <RefreshCw className="h-4 w-4" />
          </Button>
          <HCPSelector hcps={hcp.hcps} selectedId={hcp.selectedId} onSelect={hcp.select} />
        </div>
      </AppHeader>
      <div className="grid gap-4 px-4 pb-8 sm:px-8 lg:grid-cols-3">
        <ErrorBanner error={hcp.error ?? intel.error} className="lg:col-span-3" />
        <div className="flex flex-col gap-4">
          <HCPProfile profile={hcp.profile} />
          <RecommendationCard recommendations={intel.recs?.recommendations ?? []} />
        </div>
        <div className="flex flex-col gap-4">
          <InterestChart interests={intel.signals?.affinities ?? hcp.profile?.interests ?? []} />
          <EngagementChart series={intel.engagement} />
        </div>
        <div className="flex flex-col gap-4">
          <SignalFeed signals={intel.signals?.signals ?? []} />
          <InteractionTimeline entries={hcp.timeline} />
        </div>
      </div>
    </main>
  );
}
