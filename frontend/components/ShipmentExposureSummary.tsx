"use client";

import { useState } from "react";
import type {
  WeatherGraphResponse,
  WeatherRisk,
  WeatherOpportunity,
} from "@/lib/types";
import { RISK_LEVEL_COLORS, RISK_LEVEL_BAR_COLORS } from "@/lib/constants";
import { ShipmentTimeline } from "@/components/ShipmentTimeline";

// ─── helpers ────────────────────────────────────────────────────────────────

type Level = "low" | "moderate" | "high" | "critical";

function scoreToLevel(score: number): Level {
  if (score >= 75) return "critical";
  if (score >= 50) return "high";
  if (score >= 25) return "moderate";
  return "low";
}

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function factorLabel(key: string) {
  const map: Record<string, string> = {
    transportation: "Transportation",
    power_outage: "Power Outage",
    production: "Production",
    port_and_route: "Port & Route",
    raw_material_delay: "Raw Material",
  };
  return map[key] ?? key.replace(/_/g, " ");
}

// ─── sub-components ──────────────────────────────────────────────────────────

function MetricTile({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50 p-3 space-y-0.5">
      <div className="text-[11px] font-medium uppercase tracking-wide text-medium-gray dark:text-gray-400">
        {label}
      </div>
      <div className="text-[18px] font-bold text-dark-gray dark:text-gray-100">
        {value}
      </div>
      {sub && (
        <div className="text-[11px] text-medium-gray dark:text-gray-400">
          {sub}
        </div>
      )}
    </div>
  );
}

function ScoreBar({
  score,
  level,
  showLabel = true,
}: {
  score: number;
  level: Level;
  showLabel?: boolean;
}) {
  const barColor = RISK_LEVEL_BAR_COLORS[level] ?? RISK_LEVEL_BAR_COLORS.low;
  return (
    <div className="space-y-1">
      {showLabel && (
        <div className="flex items-center justify-between text-[11px] text-medium-gray dark:text-gray-400">
          <span>0</span>
          <span className="font-semibold text-dark-gray dark:text-gray-300">
            {score.toFixed(1)} / 100
          </span>
          <span>100</span>
        </div>
      )}
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-light-gray/50 dark:bg-gray-700">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.max(4, Math.min(100, score))}%` }}
        />
      </div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const sev = severity as Level;
  const c = RISK_LEVEL_COLORS[sev] ?? RISK_LEVEL_COLORS.low;
  return (
    <span
      className={`shrink-0 rounded-full border ${c.border} ${c.bg} px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${c.text}`}
    >
      {cap(severity)}
    </span>
  );
}

// ─── Section: Exposure overview ───────────────────────────────────────────────

function ExposureOverview({ risk }: { risk: WeatherRisk }) {
  const exp = risk.sourceData?.weatherExposure ?? {};
  const expScore = exp.weather_exposure_score ?? 0;
  const peakScore = exp.peak_risk_score ?? 0;
  const expLevel = scoreToLevel(expScore);
  const colors = RISK_LEVEL_COLORS[expLevel] ?? RISK_LEVEL_COLORS.low;
  const [origin, dest] = (exp.route ?? "").split("->").map((s) => s.trim());

  return (
    <div className="rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm space-y-5">
      {/* Route header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[15px] font-semibold text-dark-gray dark:text-gray-200">
          {origin && (
            <span className="rounded-lg border border-primary-light/50 dark:border-primary-light/40 bg-sky-blue/40 dark:bg-gray-700 px-3 py-1 text-[13px] text-primary-dark dark:text-primary-light">
              {origin}
            </span>
          )}
          <span className="text-medium-gray dark:text-gray-400 text-[18px]">
            →
          </span>
          {dest && (
            <span className="rounded-full border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/30 px-3 py-1 text-[13px] text-purple-700 dark:text-purple-300">
              {dest}
            </span>
          )}
        </div>
        <SeverityBadge severity={risk.severity ?? "low"} />
      </div>

      {/* Metric tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricTile
          label="Exposure Score"
          value={`${expScore.toFixed(1)}/100`}
          sub={cap(expLevel) + " risk"}
        />
        <MetricTile
          label="Peak Risk Score"
          value={`${peakScore.toFixed(1)}/100`}
          sub={`Day ${exp.peak_risk_day ?? "-"}`}
        />
        <MetricTile
          label="Peak Risk Date"
          value={exp.peak_risk_date ?? "-"}
          sub={`Day ${exp.peak_risk_day ?? "-"}`}
        />
        <MetricTile
          label="High-Risk Days"
          value={String(exp.high_risk_day_count ?? 0)}
          sub="days flagged high/critical"
        />
      </div>

      {/* Exposure score bar */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <span className={`text-[13px] font-semibold ${colors.text}`}>
            Overall Exposure — {cap(expLevel)}
          </span>
          <span className="text-[13px] text-medium-gray dark:text-gray-400">
            {expScore.toFixed(1)} / 100
          </span>
        </div>
        <ScoreBar score={expScore} level={expLevel} showLabel={false} />
      </div>

      {/* Description */}
      {risk.description && (
        <p className="text-[13px] leading-relaxed text-medium-gray dark:text-gray-400 border-t border-light-gray dark:border-gray-700 pt-4">
          {risk.description}
        </p>
      )}

      {/* Impact */}
      {risk.estimatedImpact && (
        <div className="rounded-xl border border-cyan-blue/30 dark:border-cyan-blue/20 bg-cyan-blue/5 dark:bg-gray-700/40 px-4 py-3">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-primary-dark dark:text-primary-light">
            Estimated Impact
          </span>
          <p className="mt-1 text-[13px] text-dark-gray dark:text-gray-300">
            {risk.estimatedImpact}
          </p>
        </div>
      )}

      {risk.affectedSupplier && (
        <p className="text-[12px] text-medium-gray dark:text-gray-400">
          <span className="font-semibold text-dark-gray dark:text-gray-300">
            Affected Supplier:{" "}
          </span>
          {risk.affectedSupplier}
        </p>
      )}
    </div>
  );
}

// ─── Section: Risk Factors Max ────────────────────────────────────────────────

function RiskFactorsMax({ factors }: { factors: Record<string, number> }) {
  const entries = Object.entries(factors).sort(([, a], [, b]) => b - a);
  if (!entries.length) return null;

  return (
    <div className="rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm space-y-4">
      <div>
        <h3 className="text-[15px] font-semibold text-dark-gray dark:text-gray-200">
          Risk Factors Breakdown
        </h3>
        <p className="text-[12px] text-medium-gray dark:text-gray-400 mt-0.5">
          Maximum risk score per dimension across all transit days
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {entries.map(([key, score]) => {
          const level = scoreToLevel(score);
          const colors = RISK_LEVEL_COLORS[level] ?? RISK_LEVEL_COLORS.low;
          const barColor =
            RISK_LEVEL_BAR_COLORS[level] ?? RISK_LEVEL_BAR_COLORS.low;
          return (
            <div
              key={key}
              className={`rounded-xl border ${colors.border} bg-off-white dark:bg-gray-700/40 p-3 space-y-2`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-semibold text-dark-gray dark:text-gray-200">
                  {factorLabel(key)}
                </span>
                <span
                  className={`rounded-lg border ${colors.border} ${colors.bg} px-2 py-0.5 text-[11px] font-bold ${colors.text}`}
                >
                  {cap(level)} · {score.toFixed(1)}
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-light-gray/50 dark:bg-gray-600">
                <div
                  className={`h-full rounded-full ${barColor}`}
                  style={{ width: `${Math.max(4, Math.min(100, score))}%` }}
                />
              </div>
              <div className="text-[11px] text-medium-gray dark:text-gray-500">
                Max score: {score.toFixed(1)} / 100
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Section: Day-level high-risk events ─────────────────────────────────────

function DayRiskTimeline({ dayRisks }: { dayRisks: WeatherRisk[] }) {
  if (!dayRisks.length) return null;

  return (
    <div className="rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm space-y-4">
      <div>
        <h3 className="text-[15px] font-semibold text-dark-gray dark:text-gray-200">
          High-Risk Transit Days
        </h3>
        <p className="text-[12px] text-medium-gray dark:text-gray-400 mt-0.5">
          Individual days flagged as high or critical during transit
        </p>
      </div>

      {/* Strip bar */}
      <div className="flex gap-1">
        {dayRisks
          .slice()
          .sort(
            (a, b) =>
              (a.sourceData?.weatherExposure?.day_number ?? 0) -
              (b.sourceData?.weatherExposure?.day_number ?? 0),
          )
          .map((r, i) => {
            const score =
              r.sourceData?.weatherExposure?.weather_exposure_score ?? 0;
            const level = scoreToLevel(score);
            const barColor =
              RISK_LEVEL_BAR_COLORS[level] ?? RISK_LEVEL_BAR_COLORS.low;
            const dayNum = r.sourceData?.weatherExposure?.day_number ?? i + 1;
            return (
              <div
                key={i}
                className={`h-3 flex-1 rounded-full ${barColor}`}
                title={`Day ${dayNum} — score ${score.toFixed(0)}/100`}
              />
            );
          })}
      </div>

      {/* Day cards */}
      <div className="flex gap-3 overflow-x-auto pb-1">
        {dayRisks
          .slice()
          .sort(
            (a, b) =>
              (a.sourceData?.weatherExposure?.day_number ?? 0) -
              (b.sourceData?.weatherExposure?.day_number ?? 0),
          )
          .map((r, i) => {
            const exp = r.sourceData?.weatherExposure ?? {};
            const score = exp.weather_exposure_score ?? 0;
            const level = scoreToLevel(score);
            const colors = RISK_LEVEL_COLORS[level] ?? RISK_LEVEL_COLORS.low;
            const barColor =
              RISK_LEVEL_BAR_COLORS[level] ?? RISK_LEVEL_BAR_COLORS.low;

            return (
              <div
                key={i}
                className={`min-w-[180px] flex-shrink-0 rounded-xl border ${colors.border} ${colors.bg} dark:border-gray-600 dark:bg-gray-700/40 p-3 space-y-2`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-[13px] font-bold text-dark-gray dark:text-gray-200">
                      Day {exp.day_number ?? "-"}
                    </div>
                    <div className="text-[11px] text-medium-gray dark:text-gray-400">
                      {exp.date ?? ""}
                    </div>
                  </div>
                  <SeverityBadge severity={r.severity ?? "high"} />
                </div>

                {exp.location && (
                  <div className="text-[11px] font-medium text-dark-gray dark:text-gray-300 leading-tight">
                    {exp.location}
                  </div>
                )}

                <div className="space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-medium-gray dark:text-gray-400">
                      Risk score
                    </span>
                    <span className="font-bold text-dark-gray dark:text-gray-200">
                      {score.toFixed(0)}/100
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/50 dark:bg-gray-600">
                    <div
                      className={`h-full rounded-full ${barColor}`}
                      style={{ width: `${Math.max(4, Math.min(100, score))}%` }}
                    />
                  </div>
                </div>

                {r.description && (
                  <p className="text-[11px] leading-snug text-medium-gray dark:text-gray-400 line-clamp-3">
                    {r.description}
                  </p>
                )}

                {r.estimatedImpact && (
                  <p className="text-[11px] font-medium text-primary-dark dark:text-primary-light">
                    {r.estimatedImpact}
                  </p>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}

// ─── Section: All risks ───────────────────────────────────────────────────────

function RiskItem({ risk }: { risk: WeatherRisk }) {
  const [open, setOpen] = useState(false);
  const exp = risk.sourceData?.weatherExposure ?? {};
  const score = exp.weather_exposure_score ?? 0;
  const level = scoreToLevel(score);
  const colors = RISK_LEVEL_COLORS[level] ?? RISK_LEVEL_COLORS.low;

  return (
    <div
      className={`rounded-xl border ${colors.border} bg-white dark:bg-gray-800 shadow-sm overflow-hidden`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-start justify-between gap-3 p-4 text-left"
      >
        <div className="space-y-0.5 flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[14px] font-semibold text-dark-gray dark:text-gray-200 leading-snug">
              {risk.title}
            </span>
            <SeverityBadge severity={risk.severity ?? "low"} />
          </div>
          {risk.affectedRegion && (
            <div className="text-[12px] text-medium-gray dark:text-gray-400">
              {risk.affectedRegion}
            </div>
          )}
        </div>
        <span className="shrink-0 mt-0.5 text-[18px] text-medium-gray dark:text-gray-400 leading-none">
          {open ? "−" : "+"}
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3 border-t border-light-gray dark:border-gray-700">
          {/* Score bar */}
          {score > 0 && (
            <div className="pt-3">
              <ScoreBar score={score} level={level} />
            </div>
          )}

          {/* Description */}
          <p className="text-[13px] leading-relaxed text-medium-gray dark:text-gray-400">
            {risk.description}
          </p>

          {/* Fields grid */}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 text-[12px]">
            {risk.estimatedImpact && (
              <div className="rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/40 px-3 py-2">
                <div className="font-semibold text-dark-gray dark:text-gray-300 mb-0.5">
                  Estimated Impact
                </div>
                <div className="text-medium-gray dark:text-gray-400">
                  {risk.estimatedImpact}
                </div>
              </div>
            )}
            {risk.affectedSupplier && (
              <div className="rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/40 px-3 py-2">
                <div className="font-semibold text-dark-gray dark:text-gray-300 mb-0.5">
                  Affected Supplier
                </div>
                <div className="text-medium-gray dark:text-gray-400">
                  {risk.affectedSupplier}
                </div>
              </div>
            )}
            {risk.affectedRegion && (
              <div className="rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/40 px-3 py-2">
                <div className="font-semibold text-dark-gray dark:text-gray-300 mb-0.5">
                  Affected Region
                </div>
                <div className="text-medium-gray dark:text-gray-400">
                  {risk.affectedRegion}
                </div>
              </div>
            )}
            <div className="rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/40 px-3 py-2">
              <div className="font-semibold text-dark-gray dark:text-gray-300 mb-0.5">
                Source Type
              </div>
              <div className="text-medium-gray dark:text-gray-400">
                {risk.sourceType}
              </div>
            </div>
          </div>

          {/* Source data detail */}
          {Object.keys(exp).length > 0 && (
            <div className="rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/40 p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400 mb-2">
                Weather Exposure Data
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
                {Object.entries(exp).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2">
                    <span className="text-medium-gray dark:text-gray-500">
                      {k.replace(/_/g, " ")}
                    </span>
                    <span className="font-semibold text-dark-gray dark:text-gray-300 text-right">
                      {v == null
                        ? "—"
                        : typeof v === "number"
                          ? v.toFixed(1)
                          : String(v)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Section: Opportunities ───────────────────────────────────────────────────

function OpportunityItem({ opp }: { opp: WeatherOpportunity }) {
  return (
    <div className="rounded-xl border border-green-200 dark:border-green-800/60 bg-white dark:bg-gray-800 p-4 shadow-sm space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-[14px] font-semibold text-dark-gray dark:text-gray-200 leading-snug">
          {opp.title}
        </p>
        <span className="shrink-0 rounded-full border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/30 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-green-700 dark:text-green-400">
          {opp.type.replace(/_/g, " ")}
        </span>
      </div>

      <p className="text-[13px] leading-relaxed text-medium-gray dark:text-gray-400">
        {opp.description}
      </p>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 text-[12px]">
        {opp.potentialBenefit && (
          <div className="rounded-lg border border-green-200 dark:border-green-800/40 bg-green-50/50 dark:bg-green-900/10 px-3 py-2">
            <div className="font-semibold text-dark-gray dark:text-gray-300 mb-0.5">
              Potential Benefit
            </div>
            <div className="text-medium-gray dark:text-gray-400">
              {opp.potentialBenefit}
            </div>
          </div>
        )}
        {opp.affectedRegion && (
          <div className="rounded-lg border border-green-200 dark:border-green-800/40 bg-green-50/50 dark:bg-green-900/10 px-3 py-2">
            <div className="font-semibold text-dark-gray dark:text-gray-300 mb-0.5">
              Affected Region
            </div>
            <div className="text-medium-gray dark:text-gray-400">
              {opp.affectedRegion}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Section: Raw JSON ────────────────────────────────────────────────────────

function RawJsonPanel({ data }: { data: WeatherGraphResponse }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(data, null, 2);

  function copyJson() {
    navigator.clipboard.writeText(json).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  }

  return (
    <div className="rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 shadow-sm overflow-hidden">
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((o) => !o);
          }
        }}
        className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left cursor-pointer"
      >
        <div>
          <div className="text-[14px] font-semibold text-dark-gray dark:text-gray-200">
            Full API Response — Raw JSON
          </div>
          <div className="text-[11px] text-medium-gray dark:text-gray-400 mt-0.5">
            Complete structured output from the weather graph agent
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              copyJson();
            }}
            className="rounded-lg border border-primary-light/40 dark:border-primary-light/30 bg-white dark:bg-gray-700 px-3 py-1.5 text-[12px] font-medium text-primary-dark dark:text-primary-light transition hover:bg-sky-blue/10 dark:hover:bg-gray-600"
          >
            {copied ? "✓ Copied" : "Copy JSON"}
          </button>
          <span className="text-[18px] text-medium-gray dark:text-gray-400">
            {open ? "−" : "+"}
          </span>
        </div>
      </div>
      {open && (
        <div className="border-t border-light-gray dark:border-gray-700 px-5 pb-5 pt-4">
          <pre className="max-h-96 overflow-auto rounded-xl border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-900 p-4 text-[11px] leading-relaxed text-dark-gray dark:text-gray-300">
            {json}
          </pre>
        </div>
      )}
    </div>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

interface ShipmentExposureSummaryProps {
  data: WeatherGraphResponse;
}

export function ShipmentExposureSummary({
  data,
}: ShipmentExposureSummaryProps) {
  const { risks, opportunities, daily_timeline } = data;

  // Separate route-level risk (has "route" key) from per-day risks (have "day_number")
  const routeRisk = risks.find(
    (r) => r.sourceData?.weatherExposure?.route != null,
  );
  const dayRisks = risks.filter(
    (r) => r.sourceData?.weatherExposure?.day_number != null,
  );
  const factorScores = (routeRisk?.sourceData?.risk_factors_max ??
    {}) as Record<string, number>;

  return (
    <div className="space-y-5">
      {/* 1 — Exposure overview */}
      {routeRisk && <ExposureOverview risk={routeRisk} />}

      {/* 2 — Full day-by-day weather timeline */}
      {daily_timeline?.length > 0 && (
        <div className="rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm">
          <ShipmentTimeline days={daily_timeline} />
        </div>
      )}

      {/* 3 — Risk factors max breakdown */}
      {Object.keys(factorScores).length > 0 && (
        <RiskFactorsMax factors={factorScores} />
      )}

      {/* 4 — Day-level high-risk events */}
      {dayRisks.length > 0 && <DayRiskTimeline dayRisks={dayRisks} />}

      {/* 5 — All risks (expandable) */}
      {risks.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-[15px] font-semibold text-dark-gray dark:text-gray-200">
            All Risks{" "}
            <span className="ml-1.5 rounded-full bg-red-100 dark:bg-red-900/40 px-2 py-0.5 text-[12px] text-red-700 dark:text-red-400">
              {risks.length}
            </span>
          </h3>
          {risks.map((r, i) => (
            <RiskItem key={i} risk={r} />
          ))}
        </div>
      )}

      {/* 6 — Opportunities */}
      {opportunities.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-[15px] font-semibold text-dark-gray dark:text-gray-200">
            Opportunities{" "}
            <span className="ml-1.5 rounded-full bg-green-100 dark:bg-green-900/40 px-2 py-0.5 text-[12px] text-green-700 dark:text-green-400">
              {opportunities.length}
            </span>
          </h3>
          {opportunities.map((o, i) => (
            <OpportunityItem key={i} opp={o} />
          ))}
        </div>
      )}

      {/* 7 — Raw JSON */}
      <RawJsonPanel data={data} />
    </div>
  );
}
