"use client";

import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Mobile-only disclosure; always expanded from the `sm` breakpoint up. */
export function CollapsibleSection({
  title,
  children,
  className,
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={className}>
      <button
        type="button"
        className="flex w-full items-center justify-between rounded-xl border border-border bg-card/60 px-3 py-2.5 text-sm font-medium sm:hidden"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {title}
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      <div className={cn("max-sm:mt-2", !open && "max-sm:hidden")}>{children}</div>
    </div>
  );
}
