/** API base URL for weather-agent and other backend calls (same as main API) */
export const API_BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export const RISK_LEVEL_COLORS: Record<
  string,
  { bg: string; text: string; border: string }
> = {
  low: {
    bg: "bg-cyan-blue/15 dark:bg-cyan-900/40",
    text: "text-primary-dark dark:text-cyan-200",
    border: "border-cyan-blue/40 dark:border-cyan-700/60",
  },
  moderate: {
    bg: "bg-primary-light/15 dark:bg-amber-900/30",
    text: "text-primary-dark dark:text-amber-200",
    border: "border-primary-light/40 dark:border-amber-700/50",
  },
  // Alias: some backend paths emit "medium" instead of "moderate"
  medium: {
    bg: "bg-primary-light/15 dark:bg-amber-900/30",
    text: "text-primary-dark dark:text-amber-200",
    border: "border-primary-light/40 dark:border-amber-700/50",
  },
  high: {
    bg: "bg-primary-dark/20 dark:bg-orange-900/40",
    text: "text-primary-dark dark:text-orange-200",
    border: "border-primary-dark/50 dark:border-orange-700/60",
  },
  critical: {
    bg: "bg-red-100 dark:bg-red-900/50",
    text: "text-red-800 dark:text-red-100",
    border: "border-red-300 dark:border-red-700",
  },
};

export const RISK_LEVEL_BAR_COLORS: Record<string, string> = {
  low: "bg-cyan-blue",
  moderate: "bg-primary-light",
  medium: "bg-primary-light", // alias for moderate
  high: "bg-primary-dark",
  critical: "bg-red-500",
};
