/**
 * Centralized frontend environment access. Do not read process.env anywhere else.
 * NEXT_PUBLIC_* values are inlined at build time.
 */
export const env = {
  apiBaseUrl: (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "").trim(),
  /** When true, the UI runs entirely on in-browser fixtures (lib/mockApi.ts). */
  useMockApi: (process.env.NEXT_PUBLIC_USE_MOCK_API ?? "").trim().toLowerCase() === "true",
} as const;
