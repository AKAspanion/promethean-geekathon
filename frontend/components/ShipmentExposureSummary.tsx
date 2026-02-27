"use client";

import type { ShipmentWeatherExposureResponse, RiskLevel } from "@/lib/types";
import { RISK_LEVEL_COLORS, RISK_LEVEL_BAR_COLORS } from "@/lib/constants";

function formatLevel(level: RiskLevel) {
  return level.charAt(0).toUpperCase() + level.slice(1);
}

interface ShipmentExposureSummaryProps {
  data: ShipmentWeatherExposureResponse;
  onCopyPayload?: () => void;
  payloadCopied?: boolean;
}

export function ShipmentExposureSummary({
  data,
  onCopyPayload,
  payloadCopied,
}: ShipmentExposureSummaryProps) {
  const colors = RISK_LEVEL_COLORS[data.overall_exposure_level] ?? RISK_LEVEL_COLORS.low;
  const barColor = RISK_LEVEL_BAR_COLORS[data.overall_exposure_level] ?? RISK_LEVEL_BAR_COLORS.low;
  const exp = (data.risk_analysis_payload?.exposure_summary as Record<string, unknown>) ?? {};

  return (
    <div className="space-y-4 rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2 text-[16px] font-semibold text-dark-gray dark:text-gray-200">
          <span className="rounded-lg border border-primary-light/50 dark:border-primary-light/40 bg-sky-blue/40 dark:bg-gray-700 px-3 py-1 text-[13px] text-primary-dark dark:text-primary-light">
            {data.supplier_city}
          </span>
          <span className="text-medium-gray dark:text-gray-400">→</span>
          <span className="rounded-full border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/30 px-3 py-1 text-[13px] text-purple-700 dark:text-purple-300">
            {data.oem_city}
          </span>
        </div>
        <span className="text-[13px] text-medium-gray dark:text-gray-400">
          {data.transit_days} days · starts {data.shipment_start_date}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-light-gray dark:border-gray-600 p-3">
          <div className="text-[11px] font-medium uppercase tracking-wide text-medium-gray dark:text-gray-400">
            Exposure Level
          </div>
          <div className={`mt-1 text-[16px] font-bold ${colors.text}`}>
            {formatLevel(data.overall_exposure_level)}
          </div>
        </div>
        <div className="rounded-xl border border-light-gray dark:border-gray-600 p-3">
          <div className="text-[11px] font-medium uppercase tracking-wide text-medium-gray dark:text-gray-400">
            Exposure Score
          </div>
          <div className="mt-1 text-[16px] font-bold text-dark-gray dark:text-gray-200">
            {data.overall_exposure_score.toFixed(1)}/100
          </div>
        </div>
        <div className="rounded-xl border border-light-gray dark:border-gray-600 p-3">
          <div className="text-[11px] font-medium uppercase tracking-wide text-medium-gray dark:text-gray-400">
            Peak Risk Day
          </div>
          <div className="mt-1 text-[16px] font-bold text-dark-gray dark:text-gray-200">
            Day {String(exp.peak_risk_day ?? "-")}
          </div>
          <div className="text-[11px] text-medium-gray dark:text-gray-400">{String(exp.peak_risk_date ?? "")}</div>
        </div>
        <div className="rounded-xl border border-light-gray dark:border-gray-600 p-3">
          <div className="text-[11px] font-medium uppercase tracking-wide text-medium-gray dark:text-gray-400">
            High-Risk Days
          </div>
          <div className="mt-1 text-[16px] font-bold text-dark-gray dark:text-gray-200">
            {String(exp.high_risk_day_count ?? 0)} / {data.transit_days}
          </div>
        </div>
      </div>

      <div className="h-2.5 w-full overflow-hidden rounded-full bg-light-gray/50 dark:bg-gray-700">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.max(8, Math.min(100, data.overall_exposure_score))}%` }}
        />
      </div>

      {data.agent_summary && (
        <div className="rounded-xl border border-cyan-blue/40 dark:border-cyan-blue/30 bg-cyan-blue/5 dark:bg-gray-700/50 p-4">
          <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-primary-dark dark:text-primary-light">
            Agent Summary
          </div>
          <p className="whitespace-pre-line text-[14px] leading-relaxed text-dark-gray dark:text-gray-300">
            {data.agent_summary}
          </p>
        </div>
      )}

      {(data.risk_analysis_payload?.primary_concerns as string[] | undefined)?.length ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400">
              Key Concerns
            </div>
            <ul className="space-y-1">
              {(data.risk_analysis_payload.primary_concerns as string[]).slice(0, 4).map((c, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[13px] text-dark-gray dark:text-gray-300">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-orange-400" />
                  {c}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400">
              Recommended Actions
            </div>
            <ul className="space-y-1">
              {(data.risk_analysis_payload.recommended_actions as string[]).slice(0, 4).map((a, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[13px] text-dark-gray dark:text-gray-300">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-green-500" />
                  {a}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      <div className="rounded-xl border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50 p-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="text-[12px] font-semibold text-dark-gray dark:text-gray-200">
              Risk Analysis Agent Payload
            </div>
            <div className="text-[11px] text-medium-gray dark:text-gray-400">
              Structured JSON ready for downstream Risk Analysis Agent consumption
            </div>
          </div>
          {onCopyPayload && (
            <button
              type="button"
              onClick={onCopyPayload}
              className="shrink-0 rounded-lg border border-primary-light/40 dark:border-primary-light/30 bg-white dark:bg-gray-800 px-3 py-1.5 text-[12px] font-medium text-primary-dark dark:text-primary-light transition hover:bg-sky-blue/10 dark:hover:bg-gray-600"
            >
              {payloadCopied ? "✓ Copied!" : "Copy JSON"}
            </button>
          )}
        </div>
        <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-3 text-[11px] leading-relaxed text-dark-gray dark:text-gray-300">
          {JSON.stringify(data.risk_analysis_payload, null, 2)}
        </pre>
      </div>
    </div>
  );
}
