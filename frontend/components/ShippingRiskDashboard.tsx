"use client";

import { useEffect, useState } from "react";
import {
  shippingRiskApi,
  suppliersApi,
  type Supplier,
  type ShippingRiskResult,
  type RiskDimension,
  type TrackingActivity,
  type ShipmentMeta,
} from "@/lib/api";
import { useTheme } from "@/lib/theme-context";

export function riskLevelClass(level: string): string {
  const l = (level || "").toLowerCase();
  if (l === "low")
    return "border-cyan-blue/60 bg-cyan-blue/10 text-primary-dark dark:text-primary-light";
  if (l === "medium")
    return "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400";
  if (l === "high" || l === "critical")
    return "border-red-500/60 bg-red-500/10 text-red-700 dark:text-red-400";
  return "border-light-gray dark:border-gray-600 bg-light-gray/50 dark:bg-gray-700 text-medium-gray dark:text-gray-400";
}

function scoreLabel(risk: RiskDimension | null | undefined): string {
  if (!risk) return "n/a";
  return `${risk.score} (${risk.label})`;
}

export function trackingDotClass(status?: string): string {
  const s = (status || "").toLowerCase();
  if (s.includes("delay") || s.includes("exception")) return "bg-red-500";
  if (
    s.includes("delivered") ||
    s.includes("completed") ||
    s.includes("complete")
  )
    return "bg-green-500";
  if (
    s.includes("current") ||
    s.includes("transit") ||
    s.includes("dispatch") ||
    s.includes("shipped")
  )
    return "bg-primary-light";
  if (s.includes("upcoming")) return "bg-medium-gray";
  return "bg-medium-gray";
}

// Render any extra fields from a tracking record that aren't the standard display fields
const STANDARD_FIELDS = new Set([
  "supplier_id",
  "supplier_name",
  "status",
  "activity",
  "date",
  "location",
  "sequence",
  "planned_arrival",
  "actual_arrival",
  "departure_time",
  "transport_mode",
  "awb_code",
  "current_status",
  "daysWithoutMovement",
]);

function ExtraFields({ record }: { record: TrackingActivity }) {
  const extras = Object.entries(record).filter(
    ([k, v]) => !STANDARD_FIELDS.has(k) && v != null && v !== "",
  );
  if (extras.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
      {extras.map(([k, v]) => (
        <span key={k} className="text-xs text-medium-gray dark:text-gray-400">
          <span className="font-medium">{k}:</span> {String(v)}
        </span>
      ))}
    </div>
  );
}

// ─── Reusable presentational components ─────────────────────────────────────

/**
 * Risk score gauge + dimension breakdown + risk factors / recommended actions.
 * Renders the shipping risk result without any fetching logic.
 */
export function ShippingRiskOverview({
  result,
}: {
  result: ShippingRiskResult;
}) {
  const { theme } = useTheme();
  const scoreToDeg = (score: number) => Math.max(0, Math.min(1, score)) * 360;

  return (
    <div className="space-y-5">
      {/* Score gauge + level badge */}
      <div className="flex flex-wrap items-center gap-4">
        <div
          className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full border-4 border-primary-dark dark:border-primary-light"
          style={{
            background: `conic-gradient(#4A90E2 0deg, #4A90E2 ${scoreToDeg(result.shipping_risk_score)}deg, ${theme === "dark" ? "#1f2937" : "#f9fafb"} ${scoreToDeg(result.shipping_risk_score)}deg)`,
          }}
        >
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white dark:bg-gray-800">
            <div className="text-center">
              <span className="block text-lg font-semibold text-dark-gray dark:text-gray-200">
                {(result.shipping_risk_score * 100).toFixed(0)}%
              </span>
              <span className="text-[10px] text-medium-gray dark:text-gray-400">
                risk
              </span>
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <span
            className={`inline-flex w-fit rounded-full border px-2 py-0.5 text-xs ${riskLevelClass(result.risk_level)}`}
          >
            Risk level: {result.risk_level || "Medium"}
          </span>
        </div>
      </div>

      {/* Risk dimension breakdown */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {(
          [
            { label: "Delay", data: result.delay_risk },
            { label: "Stagnation", data: result.stagnation_risk },
            { label: "Velocity", data: result.velocity_risk },
          ] as { label: string; data: RiskDimension | null | undefined }[]
        ).map(({ label, data }) => (
          <div
            key={label}
            className={`rounded-xl border p-3 ${riskLevelClass(data?.label || "")}`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold uppercase tracking-wider">
                {label}
              </span>
              <span className="text-sm font-bold">
                {data ? data.score : "—"}
              </span>
            </div>
            {data?.reason && (
              <p className="text-xs leading-relaxed opacity-90">
                {data.reason}
              </p>
            )}
            {!data?.reason && (
              <p className="text-xs opacity-60">{scoreLabel(data)}</p>
            )}
          </div>
        ))}
      </div>

      {/* Risk factors + Recommended actions */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {result.risk_factors?.length > 0 && (
          <div>
            <strong className="mb-2 block text-xs uppercase tracking-wider text-medium-gray dark:text-gray-400">
              Risk factors
            </strong>
            <ul className="list-inside list-disc space-y-1 text-sm text-dark-gray dark:text-gray-300">
              {result.risk_factors.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </div>
        )}
        {result.recommended_actions?.length > 0 && (
          <div>
            <strong className="mb-2 block text-xs uppercase tracking-wider text-medium-gray dark:text-gray-400">
              Recommended actions
            </strong>
            <ul className="list-inside list-disc space-y-1 text-sm text-dark-gray dark:text-gray-300">
              {result.recommended_actions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Vertical tracking timeline. Works with TrackingActivity[] records.
 */
export function TrackingTimelineView({
  timeline,
}: {
  timeline: TrackingActivity[];
}) {
  if (timeline.length === 0) return null;

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <strong className="text-xs uppercase tracking-wider text-medium-gray dark:text-gray-400">
          Tracking Timeline
        </strong>
        <span className="ml-auto rounded-full bg-primary-dark/10 px-2 py-0.5 text-xs text-primary-dark dark:text-primary-light">
          {timeline.length} checkpoint{timeline.length !== 1 ? "s" : ""}
        </span>
      </div>
      <ol className="relative border-l-2 border-light-gray dark:border-gray-600 pl-6">
        {timeline.map((act, i) => {
          const statusLower = (act.status || "").toLowerCase();
          const isDelayed =
            statusLower.includes("delay") || statusLower.includes("exception");
          const isCompleted =
            statusLower.includes("completed") ||
            statusLower.includes("delivered") ||
            statusLower.includes("complete");
          const isCurrent = statusLower.includes("current");

          return (
            <li key={i} className="mb-6 last:mb-0">
              <span
                className={`absolute -left-2.25 mt-1 flex h-4 w-4 items-center justify-center rounded-full ring-2 ring-white dark:ring-gray-800 ${trackingDotClass(act.status)}`}
              />
              <div
                className={`rounded-xl border p-3 ${
                  isCurrent
                    ? "border-primary-light/50 bg-sky-blue/20 dark:bg-primary-dark/20"
                    : "border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  {act.status && (
                    <span
                      className={`rounded-full border px-2 py-0.5 text-xs font-medium ${riskLevelClass(
                        isDelayed
                          ? "high"
                          : isCompleted
                            ? "low"
                            : isCurrent
                              ? "medium"
                              : "",
                      )}`}
                    >
                      {act.status}
                    </span>
                  )}
                  {act.transport_mode && (
                    <span className="rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700 px-2 py-0.5 text-xs text-medium-gray dark:text-gray-400">
                      {act.transport_mode}
                    </span>
                  )}
                  {act.sequence != null && (
                    <span className="text-xs text-medium-gray dark:text-gray-400">
                      #{act.sequence}
                    </span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-medium-gray dark:text-gray-400">
                  {act.location && <span>📍 {act.location}</span>}
                  {act.actual_arrival && (
                    <span>
                      🕐 Arrived:{" "}
                      {new Date(act.actual_arrival).toLocaleDateString()}
                    </span>
                  )}
                  {act.departure_time && (
                    <span>
                      🚀 Departed:{" "}
                      {new Date(act.departure_time).toLocaleDateString()}
                    </span>
                  )}
                  {act.planned_arrival && (
                    <span>
                      📅 Planned:{" "}
                      {new Date(act.planned_arrival).toLocaleDateString()}
                    </span>
                  )}
                  {act.actual_arrival &&
                    act.planned_arrival &&
                    new Date(act.actual_arrival) >
                      new Date(act.planned_arrival) && (
                      <span className="text-amber-600 dark:text-amber-400">
                        ⚠ Arrived{" "}
                        {Math.ceil(
                          (new Date(act.actual_arrival).getTime() -
                            new Date(act.planned_arrival).getTime()) /
                            (1000 * 60 * 60 * 24),
                        )}
                        d late
                      </span>
                    )}
                </div>
                <ExtraFields record={act} />
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ─── Full page dashboard ────────────────────────────────────────────────────

export function ShippingRiskDashboard() {
  const { theme } = useTheme();
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loadingSuppliers, setLoadingSuppliers] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusText, setStatusText] = useState(
    "Select a supplier to run the Shipment Agent.",
  );
  const [statusMeta, setStatusMeta] = useState("Idle");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ShippingRiskResult | null>(null);
  const [resultSupplierName, setResultSupplierName] = useState<string>("");
  const [timeline, setTimeline] = useState<TrackingActivity[]>([]);
  const [shipmentMeta, setShipmentMeta] = useState<ShipmentMeta | null>(null);
  const [trackingLabel, setTrackingLabel] = useState("");
  const [loadingTracking, setLoadingTracking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoadingSuppliers(true);
    suppliersApi
      .getAll()
      .then((data) => {
        if (!cancelled) setSuppliers(Array.isArray(data) ? data : []);
      })
      .catch(() => {
        if (!cancelled) setSuppliers([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingSuppliers(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleRunRisk = async (id: string, name: string) => {
    if (running) return;
    setSelectedId(id);
    setRunning(true);
    setStatusText(`Running Shipment Agent for ${name}...`);
    setStatusMeta("Running");
    setResult(null);
    setTimeline([]);
    setShipmentMeta(null);
    setTrackingLabel(name);
    try {
      const data = await shippingRiskApi.runRisk(id);
      setResult(data);
      setResultSupplierName(name);
      setStatusText(`Shipment Agent complete for ${name}.`);
      setStatusMeta("OK");
      // Automatically load tracking timeline for this supplier
      setLoadingTracking(true);
      try {
        const res = await shippingRiskApi.getTracking(id);
        setTimeline(Array.isArray(res.timeline) ? res.timeline : []);
        setShipmentMeta(res.meta);
      } catch {
        setTimeline([]);
        setShipmentMeta(null);
      } finally {
        setLoadingTracking(false);
      }
    } catch {
      setStatusText("Failed to run Shipment Agent.");
      setStatusMeta("Error");
    } finally {
      setRunning(false);
    }
  };

  const handleViewTracking = async (id: string, name: string) => {
    setTrackingLabel(name);
    setTimeline([]);
    setShipmentMeta(null);
    setLoadingTracking(true);
    try {
      const res = await shippingRiskApi.getTracking(id);
      setTimeline(Array.isArray(res.timeline) ? res.timeline : []);
      setShipmentMeta(res.meta);
    } catch {
      setTimeline([]);
      setShipmentMeta(null);
    } finally {
      setLoadingTracking(false);
    }
  };

  const scoreToDeg = (score: number) => Math.max(0, Math.min(1, score)) * 360;

  return (
    <main className="mx-auto grid grid-cols-1 gap-6 py-6 lg:grid-cols-[minmax(280px,360px)_1fr]">
      {/* ── Supplier list ─────────────────────────────────────────── */}
      <section className="rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="heading-3 text-dark-gray dark:text-gray-200 uppercase tracking-wider">
            Suppliers
          </h2>
          <span className="rounded-full border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50 px-2 py-0.5 text-xs text-medium-gray dark:text-gray-400">
            Live data
          </span>
        </div>
        <div className="max-h-[calc(100vh-200px)] overflow-y-auto pr-2">
          {loadingSuppliers ? (
            <div className="flex items-center gap-2 py-4 text-medium-gray dark:text-gray-400">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-dark border-t-transparent dark:border-primary-light dark:border-t-transparent" />
              <span className="body-text">Loading suppliers...</span>
            </div>
          ) : suppliers.length === 0 ? (
            <p className="body-text text-medium-gray dark:text-gray-400">
              No suppliers found for this OEM.
            </p>
          ) : (
            suppliers.map((s) => (
              <div
                key={s.id}
                className={`mb-2 cursor-pointer rounded-xl border p-3 transition hover:border-primary-light/50 hover:bg-sky-blue/20 dark:hover:bg-gray-700/50 ${
                  selectedId === s.id
                    ? "border-primary-dark bg-sky-blue/30 dark:bg-gray-700"
                    : "border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-800"
                }`}
                onClick={() => setSelectedId(s.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && setSelectedId(s.id)}
              >
                <div className="mb-1 flex justify-between gap-2">
                  <span className="text-sm font-medium text-dark-gray dark:text-gray-200">
                    {s.name}
                  </span>
                </div>
                <div className="mb-2 flex flex-wrap gap-1 text-xs text-medium-gray dark:text-gray-400">
                  {s.city && <span>{s.city}</span>}
                  {s.country && <span>· {s.country}</span>}
                  {s.region && <span>· {s.region}</span>}
                  {s.commodities && <span>· {s.commodities}</span>}
                </div>
                <div className="flex justify-between gap-2">
                  <button
                    type="button"
                    disabled={running}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRunRisk(s.id, s.name);
                    }}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-primary-dark px-3 py-2 text-sm font-medium text-white shadow transition hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {running && selectedId === s.id ? (
                      <>
                        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                        Running...
                      </>
                    ) : (
                      "Run Shipment Agent"
                    )}
                  </button>
                  <button
                    type="button"
                    disabled={loadingTracking}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleViewTracking(s.id, s.name);
                    }}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700 px-3 py-2 text-sm text-dark-gray dark:text-gray-200 transition hover:bg-sky-blue/20 dark:hover:bg-gray-600 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {loadingTracking && trackingLabel === s.name ? (
                      <>
                        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-dark dark:border-primary-light border-t-transparent" />
                        Loading...
                      </>
                    ) : (
                      "View Tracking"
                    )}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {/* ── Right panel ────────────────────────────────────────────── */}
      <section className="flex flex-col gap-6 rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-4 shadow-sm">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="heading-3 text-dark-gray dark:text-gray-200 uppercase tracking-wider">
            Risk & Tracking
          </h2>
          <div className="flex items-center gap-2 text-xs text-medium-gray dark:text-gray-400">
            {running ? (
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-primary-dark dark:border-primary-light border-t-transparent" />
            ) : (
              <span className="h-1.5 w-1.5 rounded-full bg-primary-light" />
            )}
            <span>{statusMeta}</span>
          </div>
        </div>
        <p className="body-text text-medium-gray dark:text-gray-400 -mt-4">
          {statusText}
        </p>

        {/* Current supplier context (whose risks/tracking are shown) */}
        {(resultSupplierName || trackingLabel) && (
          <div className="rounded-xl border border-primary-dark/30 dark:border-primary-light/30 bg-sky-blue/10 dark:bg-primary-dark/10 px-4 py-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-medium-gray dark:text-gray-400">
              Viewing supplier
            </span>
            <p className="mt-0.5 text-base font-semibold text-dark-gray dark:text-gray-200">
              {resultSupplierName || trackingLabel}
            </p>
            {resultSupplierName &&
              trackingLabel &&
              resultSupplierName !== trackingLabel && (
                <p className="mt-1 text-xs text-medium-gray dark:text-gray-400">
                  Risk result: {resultSupplierName} · Tracking: {trackingLabel}
                </p>
              )}
          </div>
        )}

        {/* ── Risk result ── */}
        {result && (
          <>
            <div className="flex flex-wrap items-center gap-4">
              <div
                className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full border-4 border-primary-dark dark:border-primary-light"
                style={{
                  background: `conic-gradient(#4A90E2 0deg, #4A90E2 ${scoreToDeg(result.shipping_risk_score)}deg, ${theme === "dark" ? "#1f2937" : "#f9fafb"} ${scoreToDeg(result.shipping_risk_score)}deg)`,
                }}
              >
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white dark:bg-gray-800">
                  <div className="text-center">
                    <span className="block text-lg font-semibold text-dark-gray dark:text-gray-200">
                      {(result.shipping_risk_score * 100).toFixed(0)}%
                    </span>
                    <span className="text-[10px] text-medium-gray dark:text-gray-400">
                      risk
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span
                  className={`inline-flex w-fit rounded-full border px-2 py-0.5 text-xs ${riskLevelClass(result.risk_level)}`}
                >
                  Risk level: {result.risk_level || "Medium"}
                </span>
              </div>
            </div>

            {/* Risk dimension breakdown with reasons */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {(
                [
                  { label: "Delay", data: result.delay_risk },
                  { label: "Stagnation", data: result.stagnation_risk },
                  { label: "Velocity", data: result.velocity_risk },
                ] as { label: string; data: RiskDimension | null | undefined }[]
              ).map(({ label, data }) => (
                <div
                  key={label}
                  className={`rounded-xl border p-3 ${riskLevelClass(data?.label || "")}`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold uppercase tracking-wider">
                      {label}
                    </span>
                    <span className="text-sm font-bold">
                      {data ? data.score : "—"}
                    </span>
                  </div>
                  {data?.reason && (
                    <p className="text-xs leading-relaxed opacity-90">
                      {data.reason}
                    </p>
                  )}
                  {!data?.reason && (
                    <p className="text-xs opacity-60">{scoreLabel(data)}</p>
                  )}
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <strong className="mb-2 block text-xs uppercase tracking-wider text-medium-gray dark:text-gray-400">
                  Risk factors
                </strong>
                <ul className="list-inside list-disc space-y-1 text-sm text-dark-gray dark:text-gray-300">
                  {(result.risk_factors || []).map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
              <div>
                <strong className="mb-2 block text-xs uppercase tracking-wider text-medium-gray dark:text-gray-400">
                  Recommended actions
                </strong>
                <ul className="list-inside list-disc space-y-1 text-sm text-dark-gray dark:text-gray-300">
                  {(result.recommended_actions || []).map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </div>
            </div>
          </>
        )}

        {/* ── Shipment overview card ── */}
        {shipmentMeta && (
          <div className="rounded-xl border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50 p-4">
            <div className="mb-3 flex items-center justify-between">
              <strong className="text-xs uppercase tracking-wider text-medium-gray dark:text-gray-400">
                Shipment Overview
              </strong>
              {shipmentMeta.current_status && (
                <span
                  className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                    shipmentMeta.current_status === "IN_TRANSIT"
                      ? "border-primary-light/60 bg-primary-light/10 text-primary-dark dark:text-primary-light"
                      : shipmentMeta.current_status === "DELIVERED"
                        ? "border-green-500/60 bg-green-500/10 text-green-700 dark:text-green-400"
                        : "border-light-gray dark:border-gray-600 bg-light-gray/50 dark:bg-gray-700 text-medium-gray dark:text-gray-400"
                  }`}
                >
                  {shipmentMeta.current_status}
                </span>
              )}
            </div>

            <div className="mb-3 flex items-center gap-2 text-sm text-dark-gray dark:text-gray-200">
              <span className="font-medium">
                {[shipmentMeta.origin_city, shipmentMeta.origin_country]
                  .filter(Boolean)
                  .join(", ") || "—"}
              </span>
              <span className="text-medium-gray dark:text-gray-400">→</span>
              <span className="font-medium">
                {[
                  shipmentMeta.destination_city,
                  shipmentMeta.destination_country,
                ]
                  .filter(Boolean)
                  .join(", ") || "—"}
              </span>
            </div>

            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-medium-gray dark:text-gray-400">
              {shipmentMeta.awb_code && (
                <span>
                  <span className="font-medium">AWB:</span>{" "}
                  {shipmentMeta.awb_code}
                </span>
              )}
              {shipmentMeta.shipment_id != null && (
                <span>
                  <span className="font-medium">Shipment ID:</span>{" "}
                  {shipmentMeta.shipment_id}
                </span>
              )}
              {shipmentMeta.pickup_date && (
                <span>
                  <span className="font-medium">Pickup:</span>{" "}
                  {new Date(shipmentMeta.pickup_date).toLocaleDateString()}
                </span>
              )}
              {shipmentMeta.etd && (
                <span>
                  <span className="font-medium">ETD:</span>{" "}
                  {new Date(shipmentMeta.etd).toLocaleDateString()}
                </span>
              )}
              {shipmentMeta.transit_days_estimated != null && (
                <span>
                  <span className="font-medium">Transit:</span>{" "}
                  {shipmentMeta.transit_days_estimated} days
                </span>
              )}
              {shipmentMeta.current_checkpoint_sequence != null && (
                <span>
                  <span className="font-medium">Checkpoint:</span>{" "}
                  {shipmentMeta.current_checkpoint_sequence} of{" "}
                  {timeline.length}
                </span>
              )}
            </div>
          </div>
        )}

        {/* ── Tracking timeline ── */}
        <div>
          <div className="mb-3 flex items-center gap-2">
            <strong className="text-xs uppercase tracking-wider text-medium-gray dark:text-gray-400">
              Tracking Timeline
            </strong>
            {trackingLabel && (
              <span className="rounded-full border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700 px-2 py-0.5 text-xs text-medium-gray dark:text-gray-400">
                {trackingLabel}
              </span>
            )}
            {timeline.length > 0 && (
              <span className="ml-auto rounded-full bg-primary-dark/10 px-2 py-0.5 text-xs text-primary-dark dark:text-primary-light">
                {timeline.length} event{timeline.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {loadingTracking ? (
            <div className="flex items-center gap-2 rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50 p-4">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-dark dark:border-primary-light border-t-transparent" />
              <span className="text-sm text-medium-gray dark:text-gray-400">
                Loading tracking data...
              </span>
            </div>
          ) : timeline.length === 0 ? (
            <p className="rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50 p-4 text-sm text-medium-gray dark:text-gray-400">
              {trackingLabel
                ? "No tracking records found."
                : 'Click "View Tracking" on a supplier to load the timeline.'}
            </p>
          ) : (
            <ol className="relative border-l-2 border-light-gray dark:border-gray-600 pl-6">
              {timeline.map((act, i) => {
                const statusLower = (act.status || "").toLowerCase();
                const isDelayed =
                  statusLower.includes("delay") ||
                  statusLower.includes("exception");
                const isCompleted =
                  statusLower.includes("completed") ||
                  statusLower.includes("delivered") ||
                  statusLower.includes("complete");
                const isCurrent = statusLower.includes("current");

                return (
                  <li key={i} className="mb-6 last:mb-0">
                    {/* dot on the line */}
                    <span
                      className={`absolute -left-2.25 mt-1 flex h-4 w-4 items-center justify-center rounded-full ring-2 ring-white dark:ring-gray-800 ${trackingDotClass(act.status)}`}
                    />

                    <div
                      className={`rounded-xl border p-3 ${
                        isCurrent
                          ? "border-primary-light/50 bg-sky-blue/20 dark:bg-primary-dark/20"
                          : "border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50"
                      }`}
                    >
                      {/* Status + transport mode */}
                      <div className="flex flex-wrap items-center gap-2">
                        {act.status && (
                          <span
                            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${riskLevelClass(
                              isDelayed
                                ? "high"
                                : isCompleted
                                  ? "low"
                                  : isCurrent
                                    ? "medium"
                                    : "",
                            )}`}
                          >
                            {act.status}
                          </span>
                        )}
                        {act.transport_mode && (
                          <span className="rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700 px-2 py-0.5 text-xs text-medium-gray dark:text-gray-400">
                            {act.transport_mode}
                          </span>
                        )}
                        {act.sequence != null && (
                          <span className="text-xs text-medium-gray dark:text-gray-400">
                            #{act.sequence}
                          </span>
                        )}
                      </div>

                      {/* Location + dates */}
                      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-medium-gray dark:text-gray-400">
                        {act.location && <span>📍 {act.location}</span>}
                        {act.actual_arrival && (
                          <span>
                            🕐 Arrived:{" "}
                            {new Date(act.actual_arrival).toLocaleDateString()}
                          </span>
                        )}
                        {act.departure_time && (
                          <span>
                            🚀 Departed:{" "}
                            {new Date(act.departure_time).toLocaleDateString()}
                          </span>
                        )}
                        {act.planned_arrival && (
                          <span>
                            📅 Planned:{" "}
                            {new Date(act.planned_arrival).toLocaleDateString()}
                          </span>
                        )}
                        {act.actual_arrival &&
                          act.planned_arrival &&
                          new Date(act.actual_arrival) >
                            new Date(act.planned_arrival) && (
                            <span className="text-amber-600 dark:text-amber-400">
                              ⚠ Arrived{" "}
                              {Math.ceil(
                                (new Date(act.actual_arrival).getTime() -
                                  new Date(act.planned_arrival).getTime()) /
                                  (1000 * 60 * 60 * 24),
                              )}
                              d late
                            </span>
                          )}
                      </div>

                      {/* Any extra fields stored in the record */}
                      <ExtraFields record={act} />
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>

        {/* ── Shipment metadata JSON ── */}
        {result?.shipment_metadata && (
          <div>
            <strong className="mb-1 block text-xs uppercase tracking-wider text-medium-gray dark:text-gray-400">
              Shipment metadata (JSON)
            </strong>
            <pre className="max-h-40 overflow-auto rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50 p-2 text-xs text-dark-gray dark:text-gray-300">
              {JSON.stringify(result.shipment_metadata, null, 2)}
            </pre>
          </div>
        )}
      </section>
    </main>
  );
}
