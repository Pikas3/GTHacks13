"use client";

import { AudioLines } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { APP_NAME } from "@/lib/constants";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/ambient", label: "Ambient" },
  { href: "/intelligence", label: "Intelligence" },
];

export function AppHeader({ children }: { children?: ReactNode }) {
  const pathname = usePathname();
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-8">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 sm:gap-x-6">
        <Link href="/" className="flex items-center gap-2 whitespace-nowrap font-semibold">
          <AudioLines className="h-5 w-5 text-primary" /> {APP_NAME}
          <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-medium uppercase text-warning">prototype</span>
        </Link>
        <nav className="flex gap-1 text-sm">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn("rounded-full px-3 py-1 text-muted-foreground hover:text-foreground", pathname === n.href && "bg-muted text-foreground")}
            >
              {n.label}
            </Link>
          ))}
        </nav>
      </div>
      {children}
    </header>
  );
}
