"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { ResourceDetail } from "@/lib/types";

/** Loads a full resource (all chunks) for the source viewer. */
export function useResource(resourceId: string | null) {
  const [resource, setResource] = useState<ResourceDetail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!resourceId) return;
    let cancelled = false;
    api
      .getResource(resourceId)
      .then((r) => !cancelled && setResource(r))
      .catch((e: unknown) => !cancelled && setError(e instanceof ApiError ? e : new ApiError("INVALID_RESOURCE", String(e))));
    return () => {
      cancelled = true;
    };
  }, [resourceId]);

  return { resource: resource?.id === resourceId ? resource : null, error };
}
