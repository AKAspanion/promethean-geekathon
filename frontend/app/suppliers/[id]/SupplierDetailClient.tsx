"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  suppliersApi,
  type Supplier,
  type SupplierUpdatePayload,
  type SupplierMetrics,
  type MetricsRisk,
  type SwarmAgentResult,
  type RiskHistoryEntry,
} from "@/lib/api";
import { AppNav } from "@/components/AppNav";
import { useAuth } from "@/lib/auth-context";
import { formatDate, safeFormatDistanceToNow } from "@/lib/format-date";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

const severityBadgeClasses: Record<string, string> = {
  low: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  medium:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  critical: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

const swarmLevelBadgeClasses: Record<string, string> = {
  LOW: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  MEDIUM:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  HIGH: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  CRITICAL: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

const sourceTypeLabels: Record<string, string> = {
  news: "News",
  global_news: "Global News",
  weather: "Weather",
  shipping: "Shipping",
  traffic: "Traffic",
};

interface EditFormState {
  name: string;
  location: string;
  city: string;
  country: string;
  region: string;
  commodities: string;
}

function DeleteConfirmDialog({
  supplierName,
  onConfirm,
  onCancel,
  isPending,
}: {
  supplierName: string;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-light-gray dark:border-gray-700 p-6 max-w-md w-full mx-4">
        <h3 className="text-lg font-semibold text-dark-gray dark:text-gray-100 mb-2">
          Delete supplier
        </h3>
        <p className="text-sm text-medium-gray dark:text-gray-400 mb-6">
          Are you sure you want to delete{" "}
          <span className="font-medium text-dark-gray dark:text-gray-200">
            {supplierName}
          </span>
          ? This action cannot be undone.
        </p>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="px-4 py-2 rounded-lg text-sm font-medium text-dark-gray dark:text-gray-200 border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-off-white dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isPending}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-red-600 hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            {isPending ? "Deleting\u2026" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

function EditForm({
  supplier,
  onSave,
  onCancel,
  isPending,
}: {
  supplier: Supplier;
  onSave: (data: SupplierUpdatePayload) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [form, setForm] = useState<EditFormState>({
    name: supplier.name ?? "",
    location: supplier.location ?? "",
    city: supplier.city ?? "",
    country: supplier.country ?? "",
    region: supplier.region ?? "",
    commodities: supplier.commodities ?? "",
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: SupplierUpdatePayload = {};
    if (form.name) payload.name = form.name;
    if (form.location !== undefined)
      payload.location = form.location || undefined;
    if (form.city !== undefined) payload.city = form.city || undefined;
    if (form.country !== undefined) payload.country = form.country || undefined;
    if (form.region !== undefined) payload.region = form.region || undefined;
    if (form.commodities !== undefined)
      payload.commodities = form.commodities || undefined;
    onSave(payload);
  };

  const labelClass =
    "block text-xs font-medium text-medium-gray dark:text-gray-400 mb-1";
  const inputClass =
    "w-full rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-dark-gray dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-dark dark:focus:ring-primary-light";

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="sm:col-span-2">
          <label htmlFor="name" className={labelClass}>
            Name <span className="text-red-500">*</span>
          </label>
          <input
            id="name"
            name="name"
            type="text"
            required
            value={form.name}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="location" className={labelClass}>
            Location
          </label>
          <input
            id="location"
            name="location"
            type="text"
            value={form.location}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="city" className={labelClass}>
            City
          </label>
          <input
            id="city"
            name="city"
            type="text"
            value={form.city}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="country" className={labelClass}>
            Country
          </label>
          <input
            id="country"
            name="country"
            type="text"
            value={form.country}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="region" className={labelClass}>
            Region
          </label>
          <input
            id="region"
            name="region"
            type="text"
            value={form.region}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="commodities" className={labelClass}>
            Commodities
          </label>
          <input
            id="commodities"
            name="commodities"
            type="text"
            value={form.commodities}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
      </div>
      <div className="flex justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={isPending}
          className="px-4 py-2 rounded-lg text-sm font-medium text-dark-gray dark:text-gray-200 border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-off-white dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isPending || !form.name}
          className="px-5 py-2 rounded-lg text-sm font-semibold text-white bg-primary-dark hover:bg-primary-light disabled:bg-light-gray dark:disabled:bg-gray-600 disabled:cursor-not-allowed transition-colors"
        >
          {isPending ? "Saving\u2026" : "Save changes"}
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* Metric sub-components                                               */
/* ------------------------------------------------------------------ */

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-sm font-semibold text-dark-gray dark:text-gray-200 uppercase tracking-wider">
      {children}
    </h3>
  );
}

function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-light-gray dark:border-gray-700 p-6 ${className}`}
    >
      {children}
    </div>
  );
}

function RiskCard({ risk }: { risk: MetricsRisk }) {
  return (
    <div className="border border-light-gray dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-start justify-between gap-3 mb-2">
        <h4 className="text-sm font-medium text-dark-gray dark:text-gray-200 leading-snug">
          {risk.title}
        </h4>
        <span
          className={`shrink-0 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${severityBadgeClasses[risk.severity] ?? "bg-light-gray/50 text-dark-gray"}`}
        >
          {risk.severity}
        </span>
      </div>
      <p className="text-xs text-medium-gray dark:text-gray-400 line-clamp-2 mb-2">
        {risk.description}
      </p>
      <div className="flex flex-wrap gap-2 text-[10px] text-medium-gray dark:text-gray-500">
        <span className="px-1.5 py-0.5 rounded bg-off-white dark:bg-gray-700">
          {sourceTypeLabels[risk.sourceType] ?? risk.sourceType}
        </span>
        {risk.affectedRegion && (
          <span className="px-1.5 py-0.5 rounded bg-off-white dark:bg-gray-700">
            {risk.affectedRegion}
          </span>
        )}
        {risk.estimatedCost != null && (
          <span className="px-1.5 py-0.5 rounded bg-off-white dark:bg-gray-700">
            ${risk.estimatedCost.toLocaleString()}
          </span>
        )}
      </div>
    </div>
  );
}

const VISIBLE_RISKS = 2;

function RisksSection({
  risks,
  risksSummary,
}: {
  risks: MetricsRisk[];
  risksSummary: { total: number; bySeverity: Record<string, number> };
}) {
  const [expanded, setExpanded] = useState(false);
  const hiddenCount = risks.length - VISIBLE_RISKS;
  const visibleRisks =
    expanded || risks.length <= VISIBLE_RISKS
      ? risks
      : risks.slice(0, VISIBLE_RISKS);

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <SectionHeading>Risks ({risksSummary.total})</SectionHeading>
        {Object.keys(risksSummary.bySeverity).length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(risksSummary.bySeverity)
              .filter(([, n]) => n > 0)
              .map(([sev, count]) => (
                <span
                  key={sev}
                  className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${severityBadgeClasses[sev] ?? "bg-light-gray/50 text-dark-gray"}`}
                >
                  {sev}: {count}
                </span>
              ))}
          </div>
        ) : null}
      </div>
      {risks.length === 0 ? (
        <p className="text-sm text-medium-gray dark:text-gray-400">
          No risks detected in this workflow run.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3">
            {visibleRisks.map((r) => (
              <RiskCard key={r.id} risk={r} />
            ))}
          </div>
          {hiddenCount > 0 ? (
            <button
              type="button"
              onClick={() => setExpanded((prev) => !prev)}
              className="mt-3 w-full text-center text-xs font-medium text-primary-dark dark:text-primary-light hover:underline py-2 rounded-lg border border-light-gray dark:border-gray-700 bg-off-white/50 dark:bg-gray-700/30 transition-colors hover:bg-off-white dark:hover:bg-gray-700/60"
            >
              {expanded
                ? "Show less"
                : `Show ${hiddenCount} more risk${hiddenCount !== 1 ? "s" : ""}`}
            </button>
          ) : null}
        </>
      )}
    </Card>
  );
}

function AgentBreakdownCard({ agent }: { agent: SwarmAgentResult }) {
  return (
    <div className="border border-light-gray dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-dark-gray dark:text-gray-200 uppercase tracking-wider">
          {agent.agentType}
        </span>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${swarmLevelBadgeClasses[agent.riskLevel] ?? "bg-light-gray/50 text-dark-gray"}`}
          >
            {agent.riskLevel}
          </span>
          <span className="text-xs text-medium-gray dark:text-gray-400">
            {agent.score}/100
          </span>
        </div>
      </div>
      {agent.signals.length > 0 && (
        <ul className="space-y-0.5 mb-2">
          {agent.signals.slice(0, 3).map((s, i) => (
            <li
              key={i}
              className="text-xs text-medium-gray dark:text-gray-400 truncate"
            >
              - {s}
            </li>
          ))}
        </ul>
      )}
      <div className="text-[10px] text-medium-gray dark:text-gray-500">
        Confidence: {(agent.confidence * 100).toFixed(0)}%
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Risk score history chart + list                                     */
/* ------------------------------------------------------------------ */

interface ChartDataPoint {
  label: string;
  riskScore: number;
  swarmScore: number | null;
  risks: number;
  date: string;
}

function RiskScoreChart({ history }: { history: RiskHistoryEntry[] }) {
  // Reverse so oldest is on the left
  const data: ChartDataPoint[] = [...history].reverse().map((h) => {
    const dateStr = h.workflowRun?.runDate ?? h.createdAt;
    const d = dateStr ? new Date(dateStr) : null;
    return {
      label: h.workflowRun?.runIndex
        ? `Run #${h.workflowRun.runIndex}`
        : d
          ? formatDate(d, "MMM d")
          : "—",
      riskScore: h.riskScore,
      swarmScore: h.swarmSummary?.finalScore ?? null,
      risks: h.risksSummary.total,
      date: d ? formatDate(d, "MMM d, yyyy", "") : "",
    };
  });

  if (data.length < 2) return null;

  return (
    <Card>
      <SectionHeading>Risk Score Trend</SectionHeading>
      <div className="h-64 mt-4">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 8, right: 16, left: -8, bottom: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--color-light-gray, #e5e7eb)"
            />
            <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="#9ca3af" />
            <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} stroke="#9ca3af" />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                borderRadius: 8,
                border: "1px solid #e5e7eb",
              }}
              formatter={(value: unknown, name: unknown) => [
                typeof value === "number"
                  ? value.toFixed(1)
                  : String(value ?? ""),
                name === "riskScore" ? "Risk Score" : "Swarm Score",
              ]}
              labelFormatter={(label, payload) => {
                const point = payload?.[0]?.payload as
                  | ChartDataPoint
                  | undefined;
                return point?.date
                  ? `${String(label)} — ${point.date}`
                  : String(label);
              }}
            />
            {/* Threshold lines */}
            <ReferenceLine
              y={25}
              stroke="#22c55e"
              strokeDasharray="4 4"
              strokeOpacity={0.5}
            />
            <ReferenceLine
              y={50}
              stroke="#eab308"
              strokeDasharray="4 4"
              strokeOpacity={0.5}
            />
            <ReferenceLine
              y={75}
              stroke="#f97316"
              strokeDasharray="4 4"
              strokeOpacity={0.5}
            />
            <Line
              type="monotone"
              dataKey="riskScore"
              stroke="#7c3aed"
              strokeWidth={2}
              dot={{ r: 4, fill: "#7c3aed" }}
              activeDot={{ r: 6 }}
              name="riskScore"
            />
            <Line
              type="monotone"
              dataKey="swarmScore"
              stroke="#0ea5e9"
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={{ r: 3, fill: "#0ea5e9" }}
              name="swarmScore"
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center gap-4 mt-3 text-[10px] text-medium-gray dark:text-gray-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-violet-600 rounded" /> Risk
          Score
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-3 h-0.5 bg-sky-500 rounded border-dashed"
            style={{ borderBottom: "1px dashed #0ea5e9", height: 0, width: 12 }}
          />{" "}
          Swarm Score
        </span>
        <span className="ml-auto flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-500" /> &le;25
          <span className="w-2 h-2 rounded-full bg-yellow-500" /> &le;50
          <span className="w-2 h-2 rounded-full bg-orange-500" /> &le;75
          <span className="w-2 h-2 rounded-full bg-red-500" /> &gt;75
        </span>
      </div>
    </Card>
  );
}

function RiskHistoryList({
  history,
  supplierId,
}: {
  history: RiskHistoryEntry[];
  supplierId: string;
}) {
  if (history.length === 0) return null;

  return (
    <Card>
      <SectionHeading>Analysis Report ({history.length})</SectionHeading>
      <div className="mt-4 space-y-3">
        {history.map((h, idx) => {
          const dateStr = h.workflowRun?.runDate ?? h.createdAt;
          const d = dateStr ? new Date(dateStr) : null;
          const level = h.swarmSummary?.riskLevel;

          return (
            <Link
              key={h.id}
              href={`/suppliers/${supplierId}/analysis/${h.id}`}
              className={`block cursor-pointer border rounded-lg p-4 transition-colors hover:shadow-md hover:border-violet-200 dark:hover:border-violet-700 ${idx === 0 ? "border-violet-200 dark:border-violet-800 bg-violet-50/30 dark:bg-violet-900/10" : "border-light-gray dark:border-gray-700"}`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {idx === 0 && (
                    <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
                      Latest
                    </span>
                  )}
                  {h.workflowRun?.runIndex != null && (
                    <span className="text-xs font-medium text-dark-gray dark:text-gray-200">
                      Run #{h.workflowRun.runIndex}
                    </span>
                  )}
                  {d && (
                    <span className="text-xs text-medium-gray dark:text-gray-400">
                      {formatDate(d, "MMM d, yyyy")}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {level && (
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${swarmLevelBadgeClasses[level] ?? "bg-light-gray/50 text-dark-gray"}`}
                    >
                      {level}
                    </span>
                  )}
                  <span className="text-sm font-semibold text-dark-gray dark:text-gray-200">
                    {h.riskScore.toFixed(1)}
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap gap-3 text-[10px] text-medium-gray dark:text-gray-500">
                <span>
                  {h.risksSummary.total} risk
                  {h.risksSummary.total !== 1 ? "s" : ""}
                </span>
                {Object.entries(h.risksSummary.bySeverity)
                  .filter(([, n]) => n > 0)
                  .map(([sev, count]) => (
                    <span
                      key={sev}
                      className={`px-1.5 py-0.5 rounded ${severityBadgeClasses[sev] ?? "bg-light-gray/50 text-dark-gray"}`}
                    >
                      {sev}: {count}
                    </span>
                  ))}
                {h.opportunitiesCount > 0 && (
                  <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
                    {h.opportunitiesCount} opp
                    {h.opportunitiesCount !== 1 ? "s" : ""}
                  </span>
                )}
              </div>

              {h.description && (
                <p className="text-xs text-medium-gray dark:text-gray-400 mt-2 line-clamp-2">
                  {h.description}
                </p>
              )}
            </Link>
          );
        })}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Metrics dashboard section                                           */
/* ------------------------------------------------------------------ */

function MetricsDashboard({ metrics }: { metrics: SupplierMetrics }) {
  const {
    workflowRun,
    riskAnalysis,
    risks,
    risksSummary,
    swarmAnalysis,
    mitigationPlans,
  } = metrics;

  if (!workflowRun) {
    return (
      <Card>
        <p className="text-sm text-medium-gray dark:text-gray-400">
          No workflow run data available yet. Trigger an analysis to see
          metrics.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Workflow Run info */}
      {/* <Card className="border-primary-dark/20 dark:border-primary-light/20">
        <div className="flex items-center gap-3 mb-3">
          <span className="rounded-md bg-blue-100 dark:bg-blue-900/30 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-blue-700 dark:text-blue-400">
            Workflow Run
          </span>
          {workflowRun.runIndex != null && (
            <span className="text-xs text-medium-gray dark:text-gray-400">
              Run #{workflowRun.runIndex}
            </span>
          )}
          {workflowRun.runDate && (
            <span className="text-xs text-medium-gray dark:text-gray-400">
              {formatDate(workflowRun.runDate, "MMM d, yyyy")}
            </span>
          )}
        </div>
        <div className="text-[10px] font-mono text-medium-gray dark:text-gray-500 break-all">
          ID: {workflowRun.id}
        </div>
      </Card> */}

      {/* Risk Analysis Score + AI Reasoning */}
      {riskAnalysis && (
        <Card className="border-violet-200 dark:border-violet-800">
          <div className="flex items-center gap-3 mb-3">
            <span className="rounded-md bg-violet-100 dark:bg-violet-900/30 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-400">
              AI Risk Analysis
            </span>
            <span className="text-sm font-semibold text-dark-gray dark:text-gray-200">
              Score: {riskAnalysis.riskScore.toFixed(1)}/100
            </span>
          </div>
          {riskAnalysis.description && (
            <p className="text-sm leading-relaxed text-dark-gray/80 dark:text-gray-300">
              {riskAnalysis.description}
            </p>
          )}
        </Card>
      )}

      {/* Swarm Analysis */}
      {swarmAnalysis && (
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <SectionHeading>Swarm Analysis</SectionHeading>
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-lg text-xs font-semibold ${swarmLevelBadgeClasses[swarmAnalysis.riskLevel] ?? "bg-light-gray/50 text-dark-gray"}`}
            >
              {swarmAnalysis.riskLevel}
            </span>
            <span className="text-xs text-medium-gray dark:text-gray-400">
              Score: {swarmAnalysis.finalScore}/100
            </span>
          </div>

          {/* Top Drivers */}
          {swarmAnalysis.topDrivers.length > 0 && (
            <div className="mb-4">
              <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-2">
                Top Risk Drivers
              </p>
              <ul className="space-y-1">
                {swarmAnalysis.topDrivers.map((d, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-xs text-dark-gray dark:text-gray-300"
                  >
                    <span className="shrink-0 w-5 h-5 rounded-full bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 flex items-center justify-center text-[10px] font-semibold mt-0.5">
                      {i + 1}
                    </span>
                    {d}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Mitigation Plan from Swarm */}
          {swarmAnalysis.mitigationPlan.length > 0 && (
            <div className="mb-4">
              <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-2">
                Suggested Mitigations
              </p>
              <ul className="space-y-1">
                {swarmAnalysis.mitigationPlan.map((m, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-xs text-dark-gray dark:text-gray-300"
                  >
                    <span className="shrink-0 text-emerald-500 mt-0.5">
                      &#10003;
                    </span>
                    {m}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Agent Breakdown */}
          {swarmAnalysis.agents.length > 0 && (
            <div>
              <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-2">
                Agent Breakdown
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {swarmAnalysis.agents.map((agent) => (
                  <AgentBreakdownCard key={agent.agentType} agent={agent} />
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Risks */}
      <RisksSection risks={risks} risksSummary={risksSummary} />

      {/* Mitigation Plans */}
      {mitigationPlans.length > 0 && (
        <Card>
          <SectionHeading>
            Mitigation Plans ({mitigationPlans.length})
          </SectionHeading>
          <div className="space-y-3">
            {mitigationPlans.map((mp) => (
              <div
                key={mp.id}
                className="border border-light-gray dark:border-gray-700 rounded-lg p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-medium text-dark-gray dark:text-gray-200">
                    {mp.title}
                  </h4>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
                    {mp.status.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-xs text-medium-gray dark:text-gray-400 mb-2">
                  {mp.description}
                </p>
                {mp.actions.length > 0 && (
                  <ul className="space-y-0.5">
                    {mp.actions.map((a, i) => (
                      <li
                        key={i}
                        className="text-xs text-dark-gray dark:text-gray-300"
                      >
                        - {a}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                      */
/* ------------------------------------------------------------------ */

export function SupplierDetailClient({ id }: { id: string }) {
  const router = useRouter();
  const { isLoggedIn, hydrated } = useAuth();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const { data: supplier, isLoading } = useQuery({
    queryKey: ["supplier", id],
    queryFn: () => suppliersApi.getById(id),
    enabled: hydrated && isLoggedIn === true,
  });

  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ["supplier-metrics", id],
    queryFn: () => suppliersApi.getMetrics(id),
    enabled: hydrated && isLoggedIn === true,
  });

  const { data: history } = useQuery({
    queryKey: ["supplier-history", id],
    queryFn: () => suppliersApi.getHistory(id),
    enabled: hydrated && isLoggedIn === true,
  });

  const updateMutation = useMutation({
    mutationFn: (data: SupplierUpdatePayload) => suppliersApi.update(id, data),
    onSuccess: (updated) => {
      queryClient.setQueryData(["supplier", id], updated);
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
      setIsEditing(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => suppliersApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
      router.push("/suppliers");
    },
  });

  if (!hydrated || !isLoggedIn) return null;

  return (
    <div className="min-h-screen bg-off-white dark:bg-gray-900">
      <header className="bg-white dark:bg-gray-800 shadow-sm border-b border-light-gray dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link
                href="/suppliers"
                className="inline-flex items-center gap-1.5 rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm font-medium text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-600 transition-colors"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M10 19l-7-7m0 0l7-7m-7 7h18"
                  />
                </svg>
                Suppliers
              </Link>
              <h1 className="heading-3 text-primary-dark dark:text-primary-light">
                {isLoading ? (
                  "Loading\u2026"
                ) : (
                  <div>
                    <h1 className="heading-3 text-primary-dark dark:text-primary-light">
                      {supplier?.name ?? "Supplier"}
                    </h1>
                    <p className="body-text text-medium-gray dark:text-gray-400">
                      Details with risk analysis
                    </p>
                  </div>
                )}
              </h1>
            </div>
            <AppNav />
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {isLoading ? (
          <div className="animate-pulse space-y-4">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-16 bg-light-gray dark:bg-gray-700 rounded-xl"
              />
            ))}
          </div>
        ) : !supplier ? (
          <div className="text-center py-16">
            <p className="body-text text-medium-gray dark:text-gray-400">
              Supplier not found.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Supplier info card */}
            <SupplierInfoCard
              supplier={supplier}
              isEditing={isEditing}
              setIsEditing={setIsEditing}
              setShowDeleteDialog={setShowDeleteDialog}
              updateMutation={updateMutation}
            />

            {/* Full Metrics Dashboard */}
            {!isEditing && (
              <>
                {metricsLoading ? (
                  <div className="animate-pulse space-y-4">
                    {[1, 2, 3, 4].map((i) => (
                      <div
                        key={i}
                        className="h-32 bg-light-gray dark:bg-gray-700 rounded-xl"
                      />
                    ))}
                  </div>
                ) : metrics ? (
                  <MetricsDashboard metrics={metrics} />
                ) : null}

                {/* Risk Score Chart & History */}
                {history && history.length > 0 && (
                  <>
                    <RiskScoreChart history={history} />
                    <RiskHistoryList history={history} supplierId={id} />
                  </>
                )}
              </>
            )}
          </div>
        )}
      </main>

      {showDeleteDialog && supplier && (
        <DeleteConfirmDialog
          supplierName={supplier.name}
          onConfirm={() => deleteMutation.mutate()}
          onCancel={() => setShowDeleteDialog(false)}
          isPending={deleteMutation.isPending}
        />
      )}
    </div>
  );
}

function DetailField({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  return (
    <div>
      <dt className="text-xs font-medium text-medium-gray dark:text-gray-400 uppercase tracking-wider mb-0.5">
        {label}
      </dt>
      <dd className="text-sm text-dark-gray dark:text-gray-200">
        {value || (
          <span className="text-medium-gray dark:text-gray-500">&mdash;</span>
        )}
      </dd>
    </div>
  );
}

function SupplierInfoCard({
  supplier,
  isEditing,
  setIsEditing,
  setShowDeleteDialog,
  updateMutation,
}: {
  supplier: Supplier;
  isEditing: boolean;
  setIsEditing: (v: boolean) => void;
  setShowDeleteDialog: (v: boolean) => void;
  updateMutation: {
    mutate: (data: SupplierUpdatePayload) => void;
    reset: () => void;
    isError: boolean;
    isPending: boolean;
  };
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-light-gray dark:border-gray-700 p-6">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h2 className="text-xl font-semibold text-dark-gray dark:text-gray-100">
            {supplier.name}
          </h2>
          <p className="text-sm text-medium-gray dark:text-gray-400 mt-0.5">
            Added{" "}
            {safeFormatDistanceToNow(supplier.createdAt, {
              addSuffix: true,
            })}
          </p>
        </div>

        {!isEditing ? (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-dark-gray dark:text-gray-200 border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-off-white dark:hover:bg-gray-600 transition-colors"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
              Edit
            </button>
            <button
              type="button"
              onClick={() => setShowDeleteDialog(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800 bg-white dark:bg-gray-700 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
              Delete
            </button>
          </div>
        ) : null}
      </div>

      {/* Quick summary row (always visible when not editing) */}
      {!isEditing ? (
        <div className="flex flex-wrap items-center gap-2 mt-3 text-xs text-medium-gray dark:text-gray-400">
          {supplier.city || supplier.country ? (
            <span className="px-2 py-0.5 rounded bg-off-white dark:bg-gray-700 text-dark-gray dark:text-gray-300">
              {[supplier.city, supplier.country].filter(Boolean).join(", ")}
            </span>
          ) : null}
          {supplier.region ? (
            <span className="px-2 py-0.5 rounded bg-off-white dark:bg-gray-700 text-dark-gray dark:text-gray-300">
              {supplier.region}
            </span>
          ) : null}
          {supplier.latestRiskLevel ? (
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${swarmLevelBadgeClasses[supplier.latestRiskLevel] ?? "bg-light-gray/50 text-dark-gray"}`}
            >
              {supplier.latestRiskLevel}
              {supplier.latestRiskScore != null
                ? ` (${supplier.latestRiskScore})`
                : ""}
            </span>
          ) : null}
        </div>
      ) : null}

      {isEditing ? (
        <div className="mt-4">
          {updateMutation.isError ? (
            <div className="mb-4 rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-800 dark:text-red-300">
              Failed to save changes. Please try again.
            </div>
          ) : null}
          <EditForm
            supplier={supplier}
            onSave={(data) => updateMutation.mutate(data)}
            onCancel={() => {
              setIsEditing(false);
              updateMutation.reset();
            }}
            isPending={updateMutation.isPending}
          />
        </div>
      ) : (
        <>
          <button
            type="button"
            onClick={() => setDetailsOpen((prev) => !prev)}
            className="mt-3 flex items-center gap-1.5 text-xs font-medium text-primary-dark dark:text-primary-light hover:underline"
          >
            <svg
              className={`h-3.5 w-3.5 transition-transform ${detailsOpen ? "rotate-90" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
            {detailsOpen ? "Hide details" : "Show details"}
          </button>

          {detailsOpen ? (
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4 mt-4 pt-4 border-t border-light-gray dark:border-gray-700">
              <DetailField label="Location" value={supplier.location} />
              <DetailField label="City" value={supplier.city} />
              <DetailField label="Country" value={supplier.country} />
              <DetailField label="Region" value={supplier.region} />
              <div className="sm:col-span-2">
                <DetailField label="Commodities" value={supplier.commodities} />
              </div>
              {supplier.latestRiskLevel ? (
                <div className="sm:col-span-2">
                  <dt className="text-xs font-medium text-medium-gray dark:text-gray-400 uppercase tracking-wider mb-1">
                    Latest risk level
                  </dt>
                  <dd>
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-lg text-xs font-semibold ${swarmLevelBadgeClasses[supplier.latestRiskLevel] ?? "bg-light-gray/50 text-dark-gray"}`}
                    >
                      {supplier.latestRiskLevel}
                    </span>
                    {supplier.latestRiskScore != null ? (
                      <span className="ml-2 text-sm text-medium-gray dark:text-gray-400">
                        Score: {supplier.latestRiskScore}
                      </span>
                    ) : null}
                  </dd>
                </div>
              ) : null}
            </dl>
          ) : null}
        </>
      )}
    </div>
  );
}
