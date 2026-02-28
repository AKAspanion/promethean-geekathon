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
    <main className="flex flex-col gap-8">
      {/* Page header */}
      <div className="flex flex-col gap-3">
        <div className="inline-flex w-fit items-center gap-2 rounded-full border border-primary-light/50 dark:border-primary-light/50 bg-sky-blue/40 dark:bg-gray-700/50 px-3 py-1.5 text-[12px] font-medium uppercase tracking-wide text-primary-dark dark:text-primary-light">
          <span className="h-1.5 w-1.5 rounded-full bg-primary-light" />
          Weather Agent · Manufacturing
        </div>
        <h2 className="text-[28px] font-bold leading-tight text-dark-gray dark:text-gray-200">
          Weather‑aware Supply Chain Risk
        </h2>
        <p className="text-[16px] leading-relaxed text-medium-gray dark:text-gray-400">
          Analyze weather exposure across your shipment timeline from Supplier to OEM —
          risks and opportunities identified automatically.
        </p>
      </div>

      {/* Action form */}
      <ShipmentForm
        onSubmit={handleSubmit}
        loading={loading}
        error={error}
      />

      {/* Full-width results */}
      {data && <ShipmentExposureSummary data={data} />}
    </main>
  );
}
