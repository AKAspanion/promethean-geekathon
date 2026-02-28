"use client";

import type { DayRiskSnapshot, RiskLevel } from "@/lib/types";
import { RISK_LEVEL_COLORS, RISK_LEVEL_BAR_COLORS } from "@/lib/constants";

const RISK_DOT: Record<RiskLevel, string> = {
  low: "bg-green-400",
  moderate: "bg-yellow-400",
  high: "bg-orange-500",
  critical: "bg-red-600",
};

function WeatherIcon({ condition }: { condition: string }) {
  const c = condition.toLowerCase();
  if (c.includes("thunder") || c.includes("storm")) return <span title={condition}>⛈️</span>;
  if (c.includes("snow") || c.includes("blizzard")) return <span title={condition}>❄️</span>;
  if (c.includes("rain") || c.includes("drizzle") || c.includes("shower")) return <span title={condition}>🌧️</span>;
  if (c.includes("fog") || c.includes("mist")) return <span title={condition}>🌫️</span>;
  if (c.includes("cloud") || c.includes("overcast")) return <span title={condition}>☁️</span>;
  if (c.includes("partly") || c.includes("partial")) return <span title={condition}>⛅</span>;
  if (c.includes("clear") || c.includes("sunny")) return <span title={condition}>☀️</span>;
  return <span title={condition}>🌤️</span>;
}

interface ShipmentTimelineProps {
  days: DayRiskSnapshot[];
}

export function ShipmentTimeline({ days }: ShipmentTimelineProps) {
  return (
    <div className="space-y-4">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <h3 className="text-[13px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400">
          Day-by-Day Weather Exposure
        </h3>
        <span className="text-[11px] text-medium-gray dark:text-gray-500">
          {days.length} days
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
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {days.map((d) => {
          const colors = RISK_LEVEL_COLORS[d.risk.overall_level] ?? RISK_LEVEL_COLORS.low;
          const dot = RISK_DOT[d.risk.overall_level];
          const isOrigin = /\(origin\)/i.test(d.location_name);
          const isDest = /\(destination\)/i.test(d.location_name);
          const cityName = d.weather.estimated_location;

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
              className={`flex flex-col gap-2 rounded-xl border p-3 ${colors.border} ${colors.bg} dark:border-gray-600 dark:bg-gray-800/60`}
            >
              {/* Top row: day + icon */}
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

              {/* City + leg label */}
              <div>
                <p className="text-[13px] font-bold leading-tight text-dark-gray dark:text-gray-100 truncate">
                  {cityName}
                </p>
                {legLabel && legLabel !== cityName && (
                  <p className="text-[10px] leading-tight text-medium-gray dark:text-gray-500 truncate mt-0.5">
                    {legLabel}
                  </p>
                )}
                <p className="text-[10px] text-medium-gray dark:text-gray-500 mt-0.5">
                  {d.date}
                  {d.weather.is_historical && (
                    <span className="ml-1 text-[9px] opacity-70">hist</span>
                  )}
                </p>
              </div>

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
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-1 min-w-0">
      <span className="text-medium-gray dark:text-gray-400 shrink-0">{label}</span>
      <span className="font-semibold text-dark-gray dark:text-gray-200 truncate text-right">{value}</span>
    </div>
  );
}
