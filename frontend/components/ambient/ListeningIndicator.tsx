"use client";

import { motion } from "framer-motion";

import { cn } from "@/lib/utils";

const BARS = [0.5, 0.9, 0.6, 1, 0.7];

/** Small animated bars used while listening or speaking. */
export function ListeningIndicator({ active, tone = "listening" }: { active: boolean; tone?: "listening" | "speaking" }) {
  return (
    <div className="flex h-5 items-end gap-0.5" aria-hidden>
      {BARS.map((h, i) => (
        <motion.span
          key={i}
          className={cn("w-1 rounded-full", tone === "speaking" ? "bg-success" : "bg-primary", !active && "opacity-30")}
          initial={{ height: 4 }}
          animate={active ? { height: [4, 20 * h, 6, 16 * h, 4] } : { height: 4 }}
          transition={active ? { duration: 0.9, repeat: Infinity, delay: i * 0.08 } : { duration: 0.2 }}
        />
      ))}
    </div>
  );
}
