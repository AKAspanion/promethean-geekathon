'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  WeatherRiskForm,
  LocationWeatherCard,
  RiskSummaryCard,
  AgentSummaryCard,
  RiskFactorsGrid,
  ShipmentForm,
  ShipmentTimeline,
  ShipmentExposureSummary,
} from '@/components/WeatherAgentComponents';
import { fetchWeatherRisk, fetchShipmentWeatherExposure } from '@/lib/api';
import type {
  WeatherRiskResponse,
  ShipmentInput,
  ShipmentWeatherExposureResponse,
} from '@/lib/types';

const today = new Date().toISOString().split('T')[0];

export default function WeatherPage() {
  const [city, setCity] = useState('New Delhi');
  const [cityLoading, setCityLoading] = useState(false);
  const [cityError, setCityError] = useState<string | null>(null);
  const [cityData, setCityData] = useState<WeatherRiskResponse | null>(null);

  const [shipmentInput, setShipmentInput] = useState<ShipmentInput>({
    supplier_city: 'Chennai',
    oem_city: 'Stuttgart',
    shipment_start_date: today,
    transit_days: 5,
  });
  const [shipmentLoading, setShipmentLoading] = useState(false);
  const [shipmentError, setShipmentError] = useState<string | null>(null);
  const [shipmentData, setShipmentData] = useState<ShipmentWeatherExposureResponse | null>(null);
  const [payloadCopied, setPayloadCopied] = useState(false);

  async function handleCitySubmit(e: React.FormEvent) {
    e.preventDefault();
    setCityLoading(true);
    setCityError(null);
    setCityData(null);
    try {
      const result = await fetchWeatherRisk(city);
      setCityData(result);
    } catch (err) {
      setCityError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setCityLoading(false);
    }
  }

  async function handleShipmentSubmit(e: React.FormEvent) {
    e.preventDefault();
    setShipmentLoading(true);
    setShipmentError(null);
    setShipmentData(null);
    setPayloadCopied(false);
    try {
      const result = await fetchShipmentWeatherExposure(shipmentInput);
      setShipmentData(result);
    } catch (err) {
      setShipmentError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setShipmentLoading(false);
    }
  }

  function handleCopyPayload() {
    if (!shipmentData) return;
    navigator.clipboard
      .writeText(JSON.stringify(shipmentData.risk_analysis_payload, null, 2))
      .then(() => {
        setPayloadCopied(true);
        setTimeout(() => setPayloadCopied(false), 2500);
      });
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
            Analyze weather exposure across your shipment timeline from Supplier to OEM - day by day.
          </p>
        </div>
      </aside>
      <div className="flex flex-1 flex-col gap-6">
        <div className="flex flex-col gap-4 rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm">
          <h3 className="text-[18px] font-semibold text-dark-gray dark:text-gray-200">Shipment Exposure</h3>
          <ShipmentForm
            input={shipmentInput}
            onChange={setShipmentInput}
            onSubmit={handleShipmentSubmit}
            loading={shipmentLoading}
            error={shipmentError}
          />
        </div>
        {shipmentData && (
          <>
            <ShipmentExposureSummary
              data={shipmentData}
              onCopyPayload={handleCopyPayload}
              payloadCopied={payloadCopied}
            />
            <ShipmentTimeline days={shipmentData.days} />
            <RiskFactorsGrid
              factors={
                shipmentData.days.reduce<ShipmentWeatherExposureResponse['days'][0]>(
                  (best, d) =>
                    d.risk.overall_score > best.risk.overall_score ? d : best,
                  shipmentData.days[0]
                )?.risk.factors ?? []
              }
            />
          </>
        )}
        <div className="flex flex-col gap-4 rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm">
          <h3 className="text-[18px] font-semibold text-dark-gray dark:text-gray-200">City Risk</h3>
          <WeatherRiskForm
            city={city}
            onCityChange={setCity}
            onSubmit={handleCitySubmit}
            loading={cityLoading}
            error={cityError}
          />
        </div>
        {cityData && (
          <div className="space-y-5">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-[1.4fr,1.6fr]">
              <LocationWeatherCard location={cityData.location} weather={cityData.weather} />
              <RiskSummaryCard
                overallLevel={cityData.risk.overall_level}
                overallScore={cityData.risk.overall_score}
                primaryConcerns={cityData.risk.primary_concerns}
              />
            </div>
            {cityData.agent_summary && (
              <AgentSummaryCard summary={cityData.agent_summary} />
            )}
            <RiskFactorsGrid factors={cityData.risk.factors} />
          </div>
        )}
      </div>
    </main>
  );
}
