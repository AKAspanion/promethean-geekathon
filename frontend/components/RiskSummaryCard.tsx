"use client";

import type { RiskLevel } from "@/lib/types";
import { RISK_LEVEL_COLORS, RISK_LEVEL_BAR_COLORS } from "@/lib/constants";

function formatRiskLevel(level: RiskLevel): string {
  return level.charAt(0).toUpperCase() + level.slice(1);
}

interface RiskSummaryCardProps {
  overallLevel: RiskLevel;
  overallScore: number;
  primaryConcerns: string[];
}

export function RiskSummaryCard({
  overallLevel,
  overallScore,
  primaryConcerns,
}: RiskSummaryCardProps) {
  const colors = RISK_LEVEL_COLORS[overallLevel] ?? RISK_LEVEL_COLORS.low;
  const barColor = RISK_LEVEL_BAR_COLORS[overallLevel] ?? RISK_LEVEL_BAR_COLORS.low;

  return (
    <div className="rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[12px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400">
            Overall risk
          </h3>
          <p className="mt-2 text-[16px] text-dark-gray dark:text-gray-200">
            {formatRiskLevel(overallLevel)} · score {overallScore.toFixed(1)}/100
          </p>
        </div>
        <span
          className={`rounded-lg border px-3 py-1.5 text-[14px] font-semibold ${colors.bg} ${colors.text} ${colors.border}`}
        >
          {formatRiskLevel(overallLevel)}
        </span>
      </div>
      <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-light-gray/50 dark:bg-gray-700">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{
            width: `${Math.max(8, Math.min(100, overallScore))}%`,
          }}
        />
      </div>
      {primaryConcerns.length > 0 && (
        <ul className="mt-4 space-y-1 text-[14px] text-dark-gray dark:text-gray-300">
          {primaryConcerns.slice(0, 3).map((c) => (
            <li key={c}>• {c}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
