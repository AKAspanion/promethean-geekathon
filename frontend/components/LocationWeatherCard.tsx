"use client";

import type { LocationInfo, WeatherCondition } from "@/lib/types";

interface LocationWeatherCardProps {
  location: LocationInfo;
  weather: WeatherCondition;
}

export function LocationWeatherCard({ location, weather }: LocationWeatherCardProps) {
  return (
    <div className="rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm">
      <h3 className="text-[12px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400">
        Location & weather
      </h3>
      <p className="mt-2 text-[20px] font-semibold leading-tight text-dark-gray dark:text-gray-200">
        {location.name || "Unknown"}
        {location.region && `, ${location.region}`}
        {location.country && `, ${location.country}`}
      </p>
      <p className="mt-0.5 text-[14px] text-medium-gray dark:text-gray-400">
        {location.localtime
          ? `Local time · ${location.localtime}`
          : `Lat ${location.lat.toFixed(2)}, Lon ${location.lon.toFixed(2)}`}
      </p>
      <div className="mt-4 grid grid-cols-2 gap-4 text-[14px]">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wide text-medium-gray dark:text-gray-400">
            Condition
          </div>
          <div className="mt-0.5 font-medium text-dark-gray dark:text-gray-200">{weather.text}</div>
        </div>
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wide text-medium-gray dark:text-gray-400">
            Temperature
          </div>
          <div className="mt-0.5 font-medium text-dark-gray dark:text-gray-200">
            {weather.temp_c.toFixed(1)}°C
            <span className="ml-1 text-[13px] font-normal text-medium-gray dark:text-gray-400">
              (feels {weather.feelslike_c.toFixed(1)}°C)
            </span>
          </div>
        </div>
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wide text-medium-gray dark:text-gray-400">
            Wind / Visibility
          </div>
          <div className="mt-0.5 font-medium text-dark-gray dark:text-gray-200">
            {weather.wind_kph.toFixed(1)} km/h · {weather.vis_km.toFixed(1)} km
            vis
          </div>
        </div>
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wide text-medium-gray dark:text-gray-400">
            Humidity / UV
          </div>
          <div className="mt-0.5 font-medium text-dark-gray dark:text-gray-200">
            {weather.humidity}% hum · UV {weather.uv ?? "-"}
          </div>
        </div>
      </div>
    </div>
  );
}
