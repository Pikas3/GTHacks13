import { AlertTriangle } from "lucide-react";

import type { ApiError } from "@/lib/api";
import { ERROR_MESSAGE } from "@/lib/constants";
import { cn } from "@/lib/utils";

/** Graceful, normalized error display for any ApiError. */
export function ErrorBanner({ error, className }: { error: ApiError | null; className?: string }) {
  if (!error) return null;
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive",
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>
        {ERROR_MESSAGE[error.code] ?? error.message}
        {error.requestId && <span className="ml-2 opacity-60">(request {error.requestId})</span>}
      </span>
    </div>
  );
}
