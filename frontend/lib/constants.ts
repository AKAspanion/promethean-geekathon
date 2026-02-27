/** API base URL for weather-agent and other backend calls (same as main API) */
export const API_BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const RISK_LEVEL_COLORS: Record<
  string,
  { bg: string; text: string; border: string }
> = {
  low: {
    bg: "bg-cyan-blue/15",
    text: "text-primary-dark",
    border: "border-cyan-blue/40",
  },
  moderate: {
    bg: "bg-primary-light/15",
    text: "text-primary-dark",
    border: "border-primary-light/40",
  },
  high: {
    bg: "bg-primary-dark/20",
    text: "text-primary-dark",
    border: "border-primary-dark/50",
  },
  critical: {
    bg: "bg-primary-dark",
    text: "text-white",
    border: "border-primary-dark",
  },
};

export const RISK_LEVEL_BAR_COLORS: Record<string, string> = {
  low: "bg-cyan-blue",
  moderate: "bg-primary-light",
  high: "bg-primary-dark",
  critical: "bg-primary-dark",
};
