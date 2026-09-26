import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", year: "numeric" }): string {
  return new Date(iso).toLocaleDateString("en-US", { timeZone: "UTC", ...opts });
}

export function isToday(iso: string, now: Date = new Date()): boolean {
  return new Date(iso).toDateString() === now.toDateString();
}
