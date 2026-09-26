"use client";

import { SendHorizontal } from "lucide-react";
import { useState } from "react";

import { SAMPLE_QUERIES } from "@/lib/constants";

/** Small developer/debug text fallback — deliberately low-key so voice stays primary. */
export function TextQueryInput({ onSubmit, disabled }: { onSubmit: (q: string) => void; disabled?: boolean }) {
  const [value, setValue] = useState("");
  return (
    <form
      className="flex w-full max-w-md items-center gap-2 rounded-full border border-border bg-background/40 px-3 py-1 text-sm opacity-80 focus-within:opacity-100"
      onSubmit={(e) => {
        e.preventDefault();
        if (!value.trim()) return;
        onSubmit(value.trim());
        setValue("");
      }}
    >
      <input
        list="sample-queries"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="or type a question…"
        aria-label="Type a question"
        disabled={disabled}
        className="flex-1 bg-transparent py-1.5 outline-none placeholder:text-muted-foreground"
      />
      <datalist id="sample-queries">
        {SAMPLE_QUERIES.map((q) => (
          <option key={q} value={q} />
        ))}
      </datalist>
      <button type="submit" disabled={disabled || !value.trim()} aria-label="Send" className="text-muted-foreground hover:text-foreground disabled:opacity-40">
        <SendHorizontal className="h-4 w-4" />
      </button>
    </form>
  );
}
