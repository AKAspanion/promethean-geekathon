'use client';

import { useState } from 'react';
import { ShipmentForm, ShipmentExposureSummary } from '@/components/WeatherAgentComponents';
import { fetchShipmentWeatherExposure } from '@/lib/api';
import type { WeatherGraphResponse } from '@/lib/types';

export default function WeatherPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<WeatherGraphResponse | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const result = await fetchShipmentWeatherExposure();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex flex-col gap-10 md:flex-row md:items-stretch md:gap-10">
      <aside className="flex flex-1 flex-col justify-between border-b border-light-gray dark:border-gray-600 pb-8 md:border-b-0 md:border-r md:border-light-gray md:dark:border-gray-600 md:pb-0 md:pr-10">
        <div className="space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-primary-light/50 dark:border-primary-light/50 bg-sky-blue/40 dark:bg-gray-700/50 px-3 py-1.5 text-[12px] font-medium uppercase tracking-wide text-primary-dark dark:text-primary-light">
            <span className="h-1.5 w-1.5 rounded-full bg-primary-light" />
            Weather Agent · Manufacturing
          </div>
          <h2 className="text-[28px] font-bold leading-tight text-dark-gray dark:text-gray-200">
            Weather‑aware Supply Chain Risk
          </h2>
          <p className="max-w-xl text-[16px] leading-relaxed text-medium-gray dark:text-gray-400">
            Analyze weather exposure across your shipment timeline from Supplier to OEM — risks and opportunities identified automatically.
          </p>
        </div>
      </aside>

      <div className="flex flex-1 flex-col gap-6">
        <ShipmentForm
          onSubmit={handleSubmit}
          loading={loading}
          error={error}
        />

        {data && <ShipmentExposureSummary data={data} />}
      </div>
    </main>
  );
}
