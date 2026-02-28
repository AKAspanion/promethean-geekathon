"use client";

import { useState, useEffect, useRef } from "react";
import type { DayRiskSnapshot, RiskFactor, RiskLevel } from "@/lib/types";
import { RISK_LEVEL_COLORS, RISK_LEVEL_BAR_COLORS } from "@/lib/constants";

const RISK_DOT: Record<RiskLevel, string> = {
  low: "bg-green-400",
  moderate: "bg-yellow-400",
  high: "bg-orange-500",
  critical: "bg-red-600",
};

type DataSourceType = "historical" | "current" | "forecast";

function getDataSource(date: string, isHistorical: boolean): DataSourceType {
  if (isHistorical) return "historical";
  const today = new Date().toISOString().slice(0, 10);
  if (date === today) return "current";
  return "forecast";
}

const DATA_SOURCE_STYLES: Record<DataSourceType, { label: string; className: string }> = {
  historical: {
    label: "Historical",
    className: "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800/50",
  },
  current: {
    label: "Live",
    className: "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/50",
  },
  forecast: {
    label: "Forecast",
    className: "bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-400 border border-violet-200 dark:border-violet-800/50",
  },
};

const FACTOR_LABELS: Record<string, string> = {
  transportation: "Transportation",
  power_outage: "Power Outage",
  production: "Production",
  port_and_route: "Port & Route",
  raw_material_delay: "Raw Material Delay",
};

function WeatherIcon({ condition, size = "sm" }: { condition: string; size?: "sm" | "lg" }) {
  const c = condition.toLowerCase();
  const emoji =
    c.includes("thunder") || c.includes("storm") ? "⛈️" :
    c.includes("snow") || c.includes("blizzard") ? "❄️" :
    c.includes("rain") || c.includes("drizzle") || c.includes("shower") ? "🌧️" :
    c.includes("fog") || c.includes("mist") ? "🌫️" :
    c.includes("cloud") || c.includes("overcast") ? "☁️" :
    c.includes("partly") || c.includes("partial") ? "⛅" :
    c.includes("clear") || c.includes("sunny") ? "☀️" : "🌤️";
  return (
    <span title={condition} className={size === "lg" ? "text-4xl" : "text-base"}>
      {emoji}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Day Risk Modal
// ---------------------------------------------------------------------------

function FactorScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const color =
    pct >= 75 ? "bg-red-500" :
    pct >= 50 ? "bg-orange-500" :
    pct >= 25 ? "bg-yellow-400" : "bg-green-400";
  return (
    <div className="h-1.5 w-full rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function FactorCard({ factor }: { factor: RiskFactor }) {
  const [open, setOpen] = useState(false);
  const levelDot: Record<string, string> = {
    low: "bg-green-400",
    moderate: "bg-yellow-400",
    high: "bg-orange-500",
    critical: "bg-red-600",
  };
  const label = FACTOR_LABELS[factor.factor] ?? factor.factor.replace(/_/g, " ");
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/60 overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${levelDot[factor.level] ?? "bg-gray-400"}`}
        />
        <span className="flex-1 text-[12px] font-semibold text-dark-gray dark:text-gray-100 capitalize">
          {label}
        </span>
        <div className="w-24 shrink-0">
          <FactorScoreBar score={factor.score} />
        </div>
        <span className="text-[11px] font-bold text-dark-gray dark:text-gray-300 w-10 text-right shrink-0">
          {factor.score.toFixed(0)}/100
        </span>
        <span className="text-medium-gray dark:text-gray-500 text-[10px] ml-1">
          {open ? "▲" : "▼"}
        </span>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2 border-t border-gray-100 dark:border-gray-700 pt-2">
          {factor.summary && (
            <p className="text-[11px] text-medium-gray dark:text-gray-400">{factor.summary}</p>
          )}
          {factor.details && (
            <p className="text-[11px] text-dark-gray dark:text-gray-300">
              <span className="font-semibold">Details: </span>{factor.details}
            </p>
          )}
          {factor.mitigation && (
            <p className="text-[11px] text-dark-gray dark:text-gray-300">
              <span className="font-semibold">Mitigation: </span>{factor.mitigation}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function DayRiskModal({
  day,
  onClose,
}: {
  day: DayRiskSnapshot;
  onClose: () => void;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const colors = RISK_LEVEL_COLORS[day.risk.overall_level] ?? RISK_LEVEL_COLORS.low;
  const dot = RISK_DOT[day.risk.overall_level];
  const dataSource = getDataSource(day.date, day.weather.is_historical);
  const ds = DATA_SOURCE_STYLES[dataSource];
  const isOrigin = /\(origin\)/i.test(day.location_name);
  const isDest = /\(destination\)/i.test(day.location_name);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="relative w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white dark:bg-gray-900 shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col">
        {/* Header */}
        <div className={`px-5 py-4 border-b border-gray-100 dark:border-gray-800 ${colors.bg}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <WeatherIcon condition={day.weather.condition} size="lg" />
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[15px] font-bold text-dark-gray dark:text-gray-100">
                    Day {day.day_number}
                  </span>
                  {isOrigin && (
                    <span className="rounded bg-sky-blue/50 dark:bg-gray-700 px-1.5 py-px text-[9px] font-bold uppercase text-primary-dark dark:text-primary-light">
                      Origin
                    </span>
                  )}
                  {isDest && (
                    <span className="rounded bg-purple-100 dark:bg-purple-900/40 px-1.5 py-px text-[9px] font-bold uppercase text-purple-700 dark:text-purple-300">
                      Destination
                    </span>
                  )}
                  <span className={`rounded-full px-2 py-px text-[9px] font-bold uppercase tracking-wide ${ds.className}`}>
                    {ds.label}
                  </span>
                </div>
                <p className="text-[13px] font-semibold text-dark-gray dark:text-gray-100 mt-0.5">
                  {day.weather.estimated_location}
                </p>
                <p className="text-[11px] text-medium-gray dark:text-gray-400">{day.date}</p>
                <p className="text-[11px] text-medium-gray dark:text-gray-400 mt-px italic">{day.weather.condition}</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="shrink-0 text-medium-gray hover:text-dark-gray dark:text-gray-400 dark:hover:text-gray-100 text-xl leading-none"
              aria-label="Close"
            >
              ✕
            </button>
          </div>

          {/* Risk level banner */}
          <div className="flex items-center gap-2 mt-3">
            <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${dot}`} />
            <span className={`text-[13px] font-bold ${colors.text}`}>
              {day.risk.overall_level.charAt(0).toUpperCase() + day.risk.overall_level.slice(1)} Risk
            </span>
            <div className="flex-1 h-2 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden ml-1">
              <div
                className={`h-full rounded-full ${RISK_LEVEL_BAR_COLORS[day.risk.overall_level]}`}
                style={{ width: `${day.risk.overall_score}%` }}
              />
            </div>
            <span className={`text-[12px] font-bold ${colors.text}`}>
              {day.risk.overall_score.toFixed(0)}/100
            </span>
          </div>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-5 overflow-y-auto">

          {/* Weather stats grid */}
          <section>
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400 mb-2">
              Weather Conditions
            </h4>
            <div className="grid grid-cols-3 gap-2">
              <StatTile label="Temp" value={`${day.weather.temp_c.toFixed(1)}°C`} />
              {day.weather.min_temp_c != null && (
                <StatTile label="Min Temp" value={`${day.weather.min_temp_c.toFixed(1)}°C`} />
              )}
              {day.weather.max_temp_c != null && (
                <StatTile label="Max Temp" value={`${day.weather.max_temp_c.toFixed(1)}°C`} />
              )}
              <StatTile label="Wind" value={`${day.weather.wind_kph.toFixed(0)} km/h`} />
              <StatTile label="Rainfall" value={`${day.weather.precip_mm.toFixed(1)} mm`} />
              <StatTile label="Visibility" value={`${day.weather.vis_km.toFixed(1)} km`} />
              <StatTile label="Humidity" value={`${day.weather.humidity}%`} />
            </div>
          </section>

          {/* Risk factors */}
          {day.risk.factors.length > 0 && (
            <section>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400 mb-2">
                Risk Factor Breakdown
              </h4>
              <div className="space-y-1.5">
                {day.risk.factors.map((f) => (
                  <FactorCard key={f.factor} factor={f} />
                ))}
              </div>
            </section>
          )}

          {/* Primary concerns */}
          {day.risk.primary_concerns.length > 0 && (
            <section>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400 mb-2">
                Primary Concerns
              </h4>
              <ul className="space-y-1.5">
                {day.risk.primary_concerns.map((c, i) => (
                  <li key={i} className="flex items-start gap-2 text-[12px] text-dark-gray dark:text-gray-300">
                    <span className="mt-0.5 shrink-0 text-orange-500">⚠</span>
                    {c}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Suggested actions */}
          {day.risk.suggested_actions.length > 0 && (
            <section>
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400 mb-2">
                Suggested Actions
              </h4>
              <ul className="space-y-1.5">
                {day.risk.suggested_actions.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-[12px] text-dark-gray dark:text-gray-300">
                    <span className="mt-0.5 shrink-0 text-emerald-500">✓</span>
                    {a}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Summary text */}
          {day.risk_summary_text && (
            <section className="rounded-lg bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 px-3 py-2.5">
              <p className="text-[11px] text-medium-gray dark:text-gray-400 italic leading-relaxed">
                {day.risk_summary_text}
              </p>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tile for modal weather stats
// ---------------------------------------------------------------------------

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 px-3 py-2 flex flex-col gap-0.5">
      <span className="text-[10px] text-medium-gray dark:text-gray-400">{label}</span>
      <span className="text-[13px] font-bold text-dark-gray dark:text-gray-100">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ShipmentTimeline
// ---------------------------------------------------------------------------

interface ShipmentTimelineProps {
  days: DayRiskSnapshot[];
}

export function ShipmentTimeline({ days }: ShipmentTimelineProps) {
  const [selectedDay, setSelectedDay] = useState<DayRiskSnapshot | null>(null);

  return (
    <div className="space-y-4">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <h3 className="text-[13px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400">
          Day-by-Day Weather Exposure
        </h3>
        <span className="text-[11px] text-medium-gray dark:text-gray-500">
          {days.length} days · click a card for details
        </span>
      </div>

      {/* Risk strip — coloured segment per day */}
      <div className="flex gap-px">
        {days.map((d) => {
          const barColor = RISK_LEVEL_BAR_COLORS[d.risk.overall_level] ?? RISK_LEVEL_BAR_COLORS.low;
          return (
            <div
              key={d.day_number}
              className={`h-2 flex-1 first:rounded-l-full last:rounded-r-full ${barColor}`}
              title={`Day ${d.day_number} · ${d.weather.estimated_location} · ${d.risk.overall_level} (${d.risk.overall_score.toFixed(0)}/100)`}
            />
          );
        })}
      </div>

      {/* Wrapping grid — no horizontal scroll */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-4 xl:grid-cols-5">
        {days.map((d) => {
          const colors = RISK_LEVEL_COLORS[d.risk.overall_level] ?? RISK_LEVEL_COLORS.low;
          const dot = RISK_DOT[d.risk.overall_level];
          const isOrigin = /\(origin\)/i.test(d.location_name);
          const isDest = /\(destination\)/i.test(d.location_name);
          const cityName = d.weather.estimated_location;
          const dataSource = getDataSource(d.date, d.weather.is_historical);
          const ds = DATA_SOURCE_STYLES[dataSource];

          // Derive a short leg label from location_name
          const legLabel = d.location_name
            .replace(/\s*\(Origin\)/i, "")
            .replace(/\s*\(Destination\)/i, "")
            .replace(/In Transit via (\w+) - Day \d+/i, "via $1")
            .replace(/In Transit - Day \d+/i, "In Transit")
            .trim();

          return (
            <div
              key={d.day_number}
              onClick={() => setSelectedDay(d)}
              className={`flex flex-col gap-2 rounded-xl border p-3 cursor-pointer transition-all duration-150 hover:shadow-md hover:scale-[1.02] active:scale-[0.99] ${colors.border} ${colors.bg} dark:border-gray-600 dark:bg-gray-800/60`}
            >
              {/* Top row: day number + origin/dest badges + weather icon */}
              <div className="flex items-center justify-between gap-1">
                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-[12px] font-bold text-dark-gray dark:text-gray-100">
                    Day {d.day_number}
                  </span>
                  {isOrigin && (
                    <span className="rounded bg-sky-blue/50 dark:bg-gray-700 px-1 py-px text-[9px] font-bold uppercase text-primary-dark dark:text-primary-light">
                      Origin
                    </span>
                  )}
                  {isDest && (
                    <span className="rounded bg-purple-100 dark:bg-purple-900/40 px-1 py-px text-[9px] font-bold uppercase text-purple-700 dark:text-purple-300">
                      Dest
                    </span>
                  )}
                </div>
                <WeatherIcon condition={d.weather.condition} />
              </div>

              {/* City + leg label + date */}
              <div>
                <p className="text-[13px] font-bold leading-tight text-dark-gray dark:text-gray-100">
                  {cityName}
                </p>
                {legLabel && legLabel !== cityName && (
                  <p className="text-[10px] leading-tight text-medium-gray dark:text-gray-500 mt-0.5">
                    {legLabel}
                  </p>
                )}
                <p className="text-[10px] text-medium-gray dark:text-gray-500 mt-0.5">
                  {d.date}
                </p>
              </div>

              {/* Data source badge */}
              <span
                className={`self-start rounded-full px-2 py-px text-[9px] font-bold uppercase tracking-wide ${ds.className}`}
              >
                {ds.label}
              </span>

              {/* Key stats */}
              <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[11px]">
                <Stat label="Temp" value={`${d.weather.temp_c.toFixed(1)}°C`} />
                <Stat label="Wind" value={`${d.weather.wind_kph.toFixed(0)} km/h`} />
                <Stat label="Rain" value={`${d.weather.precip_mm.toFixed(1)} mm`} />
                <Stat label="Vis" value={`${d.weather.vis_km.toFixed(1)} km`} />
              </div>

              {/* Risk level */}
              <div className="flex items-center gap-1.5 pt-1.5 border-t border-black/5 dark:border-white/5">
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
                <span className={`text-[11px] font-semibold ${colors.text}`}>
                  {d.risk.overall_level.charAt(0).toUpperCase() + d.risk.overall_level.slice(1)}
                  <span className="ml-1 font-normal opacity-60 text-[10px]">
                    {d.risk.overall_score.toFixed(0)}/100
                  </span>
                </span>
                <span className="ml-auto text-[9px] text-medium-gray dark:text-gray-500 opacity-60">
                  tap ↗
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Modal */}
      {selectedDay && (
        <DayRiskModal day={selectedDay} onClose={() => setSelectedDay(null)} />
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-medium-gray dark:text-gray-400">{label}</span>
      <span className="text-[12px] font-semibold text-dark-gray dark:text-gray-200">{value}</span>
    </div>
  );
}
