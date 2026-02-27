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
    <div className="space-y-3">
      <h3 className="text-[13px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400">
        Day-by-Day Weather Exposure
      </h3>

      <div className="flex gap-1">
        {days.map((d) => {
          const barColor = RISK_LEVEL_BAR_COLORS[d.risk.overall_level] ?? RISK_LEVEL_BAR_COLORS.low;
          return (
            <div
              key={d.day_number}
              className={`h-2 flex-1 rounded-full ${barColor}`}
              title={`Day ${d.day_number}: ${d.risk.overall_level} (${d.risk.overall_score.toFixed(0)}/100)`}
            />
          );
        })}
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {days.map((d) => {
          const colors = RISK_LEVEL_COLORS[d.risk.overall_level] ?? RISK_LEVEL_COLORS.low;
          const dot = RISK_DOT[d.risk.overall_level];
          const isOrigin = d.day_number === 1;
          const isDest = d.day_number === days.length;
          return (
            <div
              key={d.day_number}
              className={`min-w-[150px] flex-1 rounded-xl border p-3 text-[13px] transition ${colors.border} ${colors.bg} dark:border-gray-600 dark:bg-gray-800`}
            >
              <div className="flex items-start justify-between gap-1">
                <div>
                  <span className="font-semibold text-dark-gray dark:text-gray-200">
                    Day {d.day_number}
                  </span>
                  {isOrigin && (
                    <span className="ml-1.5 rounded-lg bg-sky-blue/40 dark:bg-gray-700 px-1.5 py-0.5 text-[10px] font-medium text-primary-dark dark:text-primary-light">
                      Origin
                    </span>
                  )}
                  {isDest && (
                    <span className="ml-1.5 rounded-full bg-purple-100 dark:bg-purple-900/30 px-1.5 py-0.5 text-[10px] font-medium text-purple-700 dark:text-purple-300">
                      Dest.
                    </span>
                  )}
                  {d.weather.is_historical && (
                    <span className="ml-1 rounded-lg bg-light-gray/50 dark:bg-gray-700 px-1.5 py-0.5 text-[10px] font-medium text-medium-gray dark:text-gray-400">
                      Historical
                    </span>
                  )}
                </div>
                <WeatherIcon condition={d.weather.condition} />
              </div>

              <p className="mt-0.5 text-[11px] text-medium-gray dark:text-gray-400">{d.date}</p>

              <p className="mt-1 text-[11px] font-medium text-dark-gray dark:text-gray-200 leading-tight">
                {d.location_name}
              </p>

              <div className="mt-2 space-y-0.5 text-[12px] text-dark-gray dark:text-gray-300">
                <div className="flex items-center gap-1">
                  <span className="text-medium-gray dark:text-gray-400">Cond:</span>{" "}
                  <span className="font-medium">{d.weather.condition}</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-medium-gray dark:text-gray-400">Temp:</span>{" "}
                  <span className="font-medium">{d.weather.temp_c.toFixed(1)}°C</span>
                  {d.weather.min_temp_c != null && d.weather.max_temp_c != null && (
                    <span className="text-[11px] text-medium-gray dark:text-gray-400">
                      ({d.weather.min_temp_c.toFixed(0)}-{d.weather.max_temp_c.toFixed(0)})
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-medium-gray dark:text-gray-400">Wind:</span>{" "}
                  <span className="font-medium">{d.weather.wind_kph.toFixed(0)} km/h</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-medium-gray dark:text-gray-400">Rain:</span>{" "}
                  <span className="font-medium">{d.weather.precip_mm.toFixed(1)} mm</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-medium-gray dark:text-gray-400">Vis:</span>{" "}
                  <span className="font-medium">{d.weather.vis_km.toFixed(1)} km</span>
                </div>
              </div>

              <div className="mt-3 flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full ${dot}`} />
                <span className={`text-[12px] font-semibold ${colors.text}`}>
                  {d.risk.overall_level.charAt(0).toUpperCase() +
                    d.risk.overall_level.slice(1)}{" "}
                  ({d.risk.overall_score.toFixed(0)}/100)
                </span>
              </div>

              {d.risk.primary_concerns[0] && (
                <p className="mt-1.5 text-[11px] leading-snug text-dark-gray dark:text-gray-400 opacity-80">
                  {d.risk.primary_concerns[0]}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
