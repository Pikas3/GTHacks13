"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { SELECTED_HCP_STORAGE_KEY } from "@/lib/constants";
import type { HCP, HCPDetail, TimelineEntry } from "@/lib/types";

function readStoredId(): string | null {
  try {
    return window.localStorage.getItem(SELECTED_HCP_STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeId(id: string): void {
  try {
    window.localStorage.setItem(SELECTED_HCP_STORAGE_KEY, id);
  } catch {
    /* storage unavailable — selection just won't persist */
  }
}

/** HCP list + selected HCP profile/timeline. Selection persists across /lepius and /intelligence. */
export function useHCP() {
  const [hcps, setHcps] = useState<HCP[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [profile, setProfile] = useState<HCPDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .listHcps()
      .then((list) => {
        if (cancelled) return;
        setHcps(list);
        const stored = readStoredId();
        const morgan = list.find((h) => h.external_id === "SYN-HCP-001");
        setSelectedId(list.some((h) => h.id === stored) ? stored : (morgan ?? list[0])?.id ?? null);
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof ApiError ? e : new ApiError("NETWORK_ERROR", String(e))))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const refresh = useCallback(async () => {
    if (!selectedId) return;
    try {
      const [p, t] = await Promise.all([api.getHcp(selectedId), api.getTimeline(selectedId)]);
      setProfile(p);
      setTimeline(t);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError("NETWORK_ERROR", String(e)));
    }
  }, [selectedId]);

  useEffect(() => {
    // Data fetch on selection change; state is set asynchronously after the requests resolve.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  const select = useCallback((id: string) => {
    storeId(id);
    setSelectedId(id);
  }, []);

  return { hcps, selectedId, select, profile, timeline, refresh, error, loading };
}
