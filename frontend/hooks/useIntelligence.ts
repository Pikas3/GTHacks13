"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { EngagementSeries, IntelligenceRecommendations, IntelligenceSignals } from "@/lib/types";

/** Impiricus-facing data for one HCP: signals, affinities, recommendations, engagement series. */
export function useIntelligence(hcpId: string | null) {
  const [signals, setSignals] = useState<IntelligenceSignals | null>(null);
  const [recs, setRecs] = useState<IntelligenceRecommendations | null>(null);
  const [engagement, setEngagement] = useState<EngagementSeries | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const refresh = useCallback(async () => {
    if (!hcpId) return;
    try {
      const [s, r, e] = await Promise.all([api.getSignals(hcpId), api.getRecommendations(hcpId), api.getEngagement(hcpId)]);
      setSignals(s);
      setRecs(r);
      setEngagement(e);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError("NETWORK_ERROR", String(e)));
    }
  }, [hcpId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  return { signals, recs, engagement, error, refresh };
}
