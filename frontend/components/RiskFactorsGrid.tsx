"use client";

import type { RiskFactor, RiskLevel } from "@/lib/types";
import { RISK_LEVEL_COLORS } from "@/lib/constants";

function formatRiskLevel(level: RiskLevel): string {
  return level.charAt(0).toUpperCase() + level.slice(1);
}

interface RiskFactorsGridProps {
  factors: RiskFactor[];
}

export function RiskFactorsGrid({ factors }: RiskFactorsGridProps) {
  return (
    <div className="space-y-3">
      <h3 className="text-[12px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400">
        Risk breakdown by dimension
      </h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {factors.map((f) => {
          const colors = RISK_LEVEL_COLORS[f.level] ?? RISK_LEVEL_COLORS.low;
          return (
            <div
              key={f.factor}
              className="flex flex-col rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-4 shadow-sm"
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold capitalize text-dark-gray dark:text-gray-200">
                  {f.factor.replace(/_/g, " ")}
                </span>
                <span
                  className={`rounded-lg border px-2 py-0.5 text-[12px] font-semibold ${colors.bg} ${colors.text} ${colors.border}`}
                >
                  {formatRiskLevel(f.level)} · {f.score.toFixed(1)}
                </span>
              </div>
              <p className="text-[14px] leading-relaxed text-medium-gray dark:text-gray-400">
                {f.summary}
              </p>
              {f.mitigation && (
                <p className="mt-2 text-[13px] text-primary-dark dark:text-primary-light">
                  Mitigation: {f.mitigation}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
