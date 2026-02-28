'use client';

import { useState, useEffect } from 'react';
import { ShipmentExposureSummary } from '@/components/WeatherAgentComponents';
import { fetchShipmentWeatherExposure, suppliersApi, type Supplier } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import type { WeatherGraphResponse } from '@/lib/types';

function riskLevelClass(level: string | null | undefined): string {
  const l = (level || '').toLowerCase();
  if (l === 'low') return 'text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-900/20 border-cyan-200 dark:border-cyan-800/50';
  if (l === 'medium' || l === 'moderate') return 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800/50';
  if (l === 'high') return 'text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800/50';
  if (l === 'critical') return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800/50';
  return 'text-medium-gray dark:text-gray-400 bg-light-gray/50 dark:bg-gray-700 border-light-gray dark:border-gray-600';
}

export default function WeatherPage() {
  const { oem } = useAuth();
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loadingSuppliers, setLoadingSuppliers] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<WeatherGraphResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingSuppliers(true);
    suppliersApi
      .getAll()
      .then((list) => { if (!cancelled) setSuppliers(Array.isArray(list) ? list : []); })
      .catch(() => { if (!cancelled) setSuppliers([]); })
      .finally(() => { if (!cancelled) setLoadingSuppliers(false); });
    return () => { cancelled = true; };
  }, []);

  const handleSelectSupplier = async (supplier: Supplier) => {
    if (running) return;
    setSelectedId(supplier.id);
    setRunning(true);
    setError(null);
    setData(null);
    try {
      const result = await fetchShipmentWeatherExposure(supplier.id);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setRunning(false);
    }
  };

  const selectedSupplier = suppliers.find((s) => s.id === selectedId) ?? null;

  return (
    <main className="flex flex-col gap-8">
      {/* Page header */}
      <div className="flex flex-col gap-3">
        <div className="inline-flex w-fit items-center gap-2 rounded-full border border-primary-light/50 bg-sky-blue/40 dark:bg-gray-700/50 px-3 py-1.5 text-[12px] font-medium uppercase tracking-wide text-primary-dark dark:text-primary-light">
          <span className="h-1.5 w-1.5 rounded-full bg-primary-light" />
          Weather Agent · Manufacturing
        </div>
        <h2 className="text-[28px] font-bold leading-tight text-dark-gray dark:text-gray-200">
          Weather‑aware Supply Chain Risk
        </h2>
        <p className="text-[16px] leading-relaxed text-medium-gray dark:text-gray-400">
          Select a supplier to analyse weather exposure from Supplier →{' '}
          <span className="font-semibold text-dark-gray dark:text-gray-200">{oem?.name ?? 'OEM'}</span>
          {' '}— risks and opportunities identified automatically.
        </p>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr] items-start">

        {/* Left column — supplier list */}
        <div className="flex flex-col gap-3 rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-4 shadow-sm">
          <div>
            <h3 className="text-[14px] font-semibold uppercase tracking-wide text-medium-gray dark:text-gray-400">
              Suppliers
            </h3>
            <p className="mt-0.5 text-[12px] text-medium-gray dark:text-gray-500">
              Click to run analysis
            </p>
          </div>

          {loadingSuppliers ? (
            <div className="flex items-center gap-2 py-4 text-[13px] text-medium-gray dark:text-gray-400">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-light border-t-transparent" />
              Loading…
            </div>
          ) : suppliers.length === 0 ? (
            <p className="py-4 text-[13px] text-medium-gray dark:text-gray-400">
              No suppliers found.
            </p>
          ) : (
            <ul className="flex flex-col gap-1 max-h-[480px] overflow-y-auto -mx-1 px-1">
              {suppliers.map((s) => {
                const isSelected = s.id === selectedId;
                const isRunningThis = isSelected && running;
                return (
                  <li key={s.id}>
                    <button
                      onClick={() => handleSelectSupplier(s)}
                      disabled={running}
                      className={`w-full flex flex-col gap-1 rounded-xl border px-3 py-2.5 text-left transition-all hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-60 ${
                        isSelected
                          ? 'border-primary-dark dark:border-primary-light bg-primary-dark/5 dark:bg-primary-light/10 ring-1 ring-primary-dark dark:ring-primary-light'
                          : 'border-transparent hover:border-light-gray dark:hover:border-gray-600 hover:bg-light-gray/40 dark:hover:bg-gray-700/40'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 min-w-0">
                        <span className="text-[13px] font-semibold leading-tight text-dark-gray dark:text-gray-100 truncate">
                          {s.name}
                        </span>
                        {isRunningThis && (
                          <span className="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-primary-dark dark:border-primary-light border-t-transparent" />
                        )}
                        {isSelected && !running && data && (
                          <span className="h-2 w-2 shrink-0 rounded-full bg-green-500" />
                        )}
                      </div>
                      {(s.city || s.country) && (
                        <span className="text-[11px] text-medium-gray dark:text-gray-500 truncate">
                          {[s.city, s.country].filter(Boolean).join(', ')}
                        </span>
                      )}
                      {s.latestRiskLevel && (
                        <span className={`self-start rounded-full border px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide ${riskLevelClass(s.latestRiskLevel)}`}>
                          {s.latestRiskLevel}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Right column — analysis */}
        <div className="flex flex-col gap-6 min-w-0">
          {running && selectedSupplier && (
            <div className="flex items-center gap-3 rounded-xl border border-primary-light/30 dark:border-primary-light/20 bg-sky-blue/20 dark:bg-gray-700/40 px-4 py-3 text-[13px] text-primary-dark dark:text-primary-light">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-dark dark:border-primary-light border-t-transparent" />
              Analysing weather exposure for <span className="font-semibold ml-1">{selectedSupplier.name}</span>…
            </div>
          )}

          {error && (
            <p className="text-[14px] text-red-600 dark:text-red-400" role="alert">
              {error}
            </p>
          )}

          {!data && !running && !error && (
            <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 py-16 text-center">
              <span className="text-3xl">🌤️</span>
              <p className="text-[14px] font-medium text-dark-gray dark:text-gray-300">
                Select a supplier to begin
              </p>
              <p className="text-[12px] text-medium-gray dark:text-gray-500">
                Weather exposure analysis will appear here
              </p>
            </div>
          )}

          {data && <ShipmentExposureSummary data={data} />}
        </div>

      </div>
    </main>
  );
}
