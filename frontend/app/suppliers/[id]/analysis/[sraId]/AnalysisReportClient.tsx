"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  suppliersApi,
  type MetricsRisk,
  type MetricsOpportunity,
  type SwarmAgentResult,
  type MetricsMitigationPlan,
  type ShippingRiskResult,
  type TrackingActivity,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDate } from "@/lib/format-date";
import { ExposureOverview } from "@/components/ShipmentExposureSummary";
import { ShipmentTimeline } from "@/components/ShipmentTimeline";
import {
  ShippingRiskOverview,
  TrackingTimelineView,
} from "@/components/ShippingRiskDashboard";
import type { WeatherRisk, DayRiskSnapshot } from "@/lib/types";

/* ------------------------------------------------------------------ */
/* Badge class maps (same as SupplierDetailClient.tsx)                  */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/* Reusable sub-components (same as SupplierDetailClient.tsx)           */
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
        {risk.affectedRegion ? (
          <span className="px-1.5 py-0.5 rounded bg-off-white dark:bg-gray-700">
            {risk.affectedRegion}
          </span>
        ) : null}
        {risk.estimatedCost != null ? (
          <span className="px-1.5 py-0.5 rounded bg-off-white dark:bg-gray-700">
            ${risk.estimatedCost.toLocaleString()}
          </span>
        ) : null}
      </div>
    </div>
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
      {agent.signals.length > 0 ? (
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
      ) : null}
      <div className="text-[10px] text-medium-gray dark:text-gray-500">
        Confidence: {(agent.confidence * 100).toFixed(0)}%
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Agent state panels                                                   */
/* ------------------------------------------------------------------ */

function WeatherStatePanel({ state }: { state: Record<string, unknown> }) {
  const dailyTimeline = (state.daily_timeline ?? state.day_results) as
    | DayRiskSnapshot[]
    | undefined;
  const supplierCity = state.supplier_city as string | undefined;
  const oemCity = state.oem_city as string | undefined;
  const routePlan = state.route_plan as Record<string, unknown>[] | undefined;
  const summary = state.agent_summary as string | undefined;
  const weatherItems = state.weather_items as
    | Record<string, unknown>[]
    | undefined;

  // Extract route-level risk for ExposureOverview
  const risks = (state.risks ?? []) as WeatherRisk[];
  const routeRisk = risks.find(
    (r) => r.sourceData?.weatherExposure?.route != null,
  );

  return (
    <Card>
      <div className="flex items-center gap-3 mb-4">
        <SectionHeading>Weather Agent State</SectionHeading>
        {supplierCity && oemCity ? (
          <span className="text-xs text-medium-gray dark:text-gray-400">
            {supplierCity} → {oemCity}
          </span>
        ) : null}
      </div>

      {summary ? (
        <p className="text-sm text-dark-gray/80 dark:text-gray-300 mb-4">
          {summary}
        </p>
      ) : null}

      {/* Exposure Overview (reused from ShipmentExposureSummary) */}
      {routeRisk ? <ExposureOverview risk={routeRisk} /> : null}

      {weatherItems && weatherItems.length > 0 ? (
        <div className="mb-4">
          <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-2">
            Weather Observations ({weatherItems.length})
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {weatherItems.map((item, i) => (
              <div
                key={i}
                className="border border-light-gray dark:border-gray-700 rounded-lg p-3 text-xs"
              >
                <p className="font-medium text-dark-gray dark:text-gray-200">
                  {String(item.city || "")}
                  {item.country ? `, ${String(item.country)}` : ""}
                </p>
                <p className="text-medium-gray dark:text-gray-400">
                  {String(item.condition || "")} —{" "}
                  {String(item.description || "")}
                </p>
                <div className="flex gap-3 mt-1 text-[10px] text-medium-gray dark:text-gray-500">
                  {item.temperature != null ? (
                    <span>Temp: {String(item.temperature)}°C</span>
                  ) : null}
                  {item.humidity != null ? (
                    <span>Humidity: {String(item.humidity)}%</span>
                  ) : null}
                  {item.windSpeed != null ? (
                    <span>Wind: {String(item.windSpeed)} km/h</span>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Day-by-day timeline (reused from ShipmentTimeline) */}
      {dailyTimeline && dailyTimeline.length > 0 ? (
        <div className="mt-4">
          <ShipmentTimeline days={dailyTimeline} />
        </div>
      ) : null}

      {routePlan && routePlan.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-2">
            Route Plan ({routePlan.length} waypoints)
          </p>
          <div className="flex flex-wrap gap-2">
            {routePlan.map((wp, i) => {
              const loc = wp.location as Record<string, unknown> | undefined;
              return (
                <span
                  key={i}
                  className="px-2 py-1 rounded bg-off-white dark:bg-gray-700 text-[10px] text-dark-gray dark:text-gray-300"
                >
                  {loc
                    ? `${String(loc.city ?? "")}${loc.country ? `, ${String(loc.country)}` : ""}`
                    : `Waypoint ${i + 1}`}
                </span>
              );
            })}
          </div>
        </div>
      ) : null}
    </Card>
  );
}

interface NewsRiskItem {
  title?: string;
  severity?: string;
  description?: string;
  sourceType?: string;
  affectedRegion?: string;
  affectedSupplier?: string;
  estimatedCost?: number | null;
  estimatedImpact?: string;
  sourceData?: Record<string, unknown>;
}
interface NewsOppItem {
  title?: string;
  type?: string;
  description?: string;
  affectedRegion?: string;
  estimatedValue?: number | null;
  potentialBenefit?: string;
}
interface NewsArticleItem {
  title?: string;
  source?: string;
  description?: string;
  publishedAt?: string;
  author?: string;
  url?: string | null;
}
interface NewsRawItem {
  data?: {
    title?: string;
    source?: string;
    description?: string;
    publishedAt?: string;
  };
  [key: string]: unknown;
}

function extractNewsData(state: Record<string, unknown> | undefined) {
  if (!state)
    return {
      newsItems: [] as NewsArticleItem[],
      newsapiRaw: [] as NewsRawItem[],
      gdeltRaw: [] as NewsRawItem[],
      risks: [] as NewsRiskItem[],
      opportunities: [] as NewsOppItem[],
    };
  return {
    newsItems: (state.news_items ?? []) as NewsArticleItem[],
    newsapiRaw: (state.newsapi_raw ?? []) as NewsRawItem[],
    gdeltRaw: (state.gdelt_raw ?? []) as NewsRawItem[],
    risks: (state.risks ?? []) as NewsRiskItem[],
    opportunities: (state.opportunities ?? []) as NewsOppItem[],
  };
}

const NEWS_PAGE_SIZE = 5;

function PaginationBar({
  page,
  totalPages,
  onPrev,
  onNext,
}: {
  page: number;
  totalPages: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex items-center justify-between mt-3">
      <span className="text-[10px] text-medium-gray dark:text-gray-500">
        Page {page} of {totalPages}
      </span>
      <div className="flex gap-1.5">
        <button
          type="button"
          onClick={onPrev}
          disabled={page <= 1}
          className="px-2.5 py-1 rounded text-[11px] font-medium border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Prev
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={page >= totalPages}
          className="px-2.5 py-1 rounded text-[11px] font-medium border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function NewsSourceContent({ data }: { data: ReturnType<typeof extractNewsData> }) {
  const allRawItems = [
    ...data.newsapiRaw.map((raw) => ({ type: "newsapi" as const, raw })),
    ...data.gdeltRaw.map((raw) => ({ type: "gdelt" as const, raw })),
  ];

  const hasContent =
    data.newsItems.length > 0 || allRawItems.length > 0;

  const [articlesPage, setArticlesPage] = useState(1);
  const articlesTotalPages = Math.max(1, Math.ceil(data.newsItems.length / NEWS_PAGE_SIZE));
  const articlesSlice = data.newsItems.slice(
    (articlesPage - 1) * NEWS_PAGE_SIZE,
    articlesPage * NEWS_PAGE_SIZE,
  );

  const [rawPage, setRawPage] = useState(1);
  const rawTotalPages = Math.max(1, Math.ceil(allRawItems.length / NEWS_PAGE_SIZE));
  const rawSlice = allRawItems.slice(
    (rawPage - 1) * NEWS_PAGE_SIZE,
    rawPage * NEWS_PAGE_SIZE,
  );

  if (!hasContent) {
    return (
      <p className="text-xs text-medium-gray dark:text-gray-400 mt-3">
        No news data available.
      </p>
    );
  }

  return (
    <div className="mt-4 space-y-5">
      {/* News Articles (paginated) */}
      {data.newsItems.length > 0 ? (
        <div>
          <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-2">
            News Articles ({data.newsItems.length})
          </p>
          <div className="space-y-2">
            {articlesSlice.map((item, i) => {
              const globalIdx = (articlesPage - 1) * NEWS_PAGE_SIZE + i;
              return (
                <div
                  key={globalIdx}
                  className="border border-light-gray dark:border-gray-700 rounded-lg p-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs font-medium text-dark-gray dark:text-gray-200 leading-snug">
                      {String(item.title || `Article ${globalIdx + 1}`)}
                    </p>
                    {item.source ? (
                      <span className="shrink-0 px-1.5 py-0.5 rounded bg-off-white dark:bg-gray-700 text-[10px] text-medium-gray dark:text-gray-400">
                        {String(item.source)}
                      </span>
                    ) : null}
                  </div>
                  {item.description ? (
                    <p className="text-[11px] text-medium-gray dark:text-gray-400 mt-1">
                      {String(item.description)}
                    </p>
                  ) : null}
                  <div className="flex flex-wrap gap-3 mt-1.5 text-[10px] text-medium-gray dark:text-gray-500">
                    {item?.publishedAt ? (
                      <span>
                        {formatDate(
                          String(item.publishedAt),
                          "MMM d, yyyy HH:mm",
                        )}
                      </span>
                    ) : null}
                    {item.author ? <span>By {String(item.author)}</span> : null}
                    {item.url ? (
                      <a
                        href={String(item.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary-dark dark:text-primary-light hover:underline"
                      >
                        Read article
                      </a>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
          {articlesTotalPages > 1 ? (
            <PaginationBar
              page={articlesPage}
              totalPages={articlesTotalPages}
              onPrev={() => setArticlesPage((p) => Math.max(1, p - 1))}
              onNext={() => setArticlesPage((p) => Math.min(articlesTotalPages, p + 1))}
            />
          ) : null}
        </div>
      ) : null}

      {/* Raw API data (paginated) */}
      {allRawItems.length > 0 ? (
        <div>
          <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-2">
            Raw API Data ({allRawItems.length})
          </p>
          <div className="space-y-2">
            {rawSlice.map((entry, i) => {
              const globalIdx = (rawPage - 1) * NEWS_PAGE_SIZE + i;
              const entryData = (
                entry.type === "newsapi"
                  ? (entry.raw.data ?? entry.raw)
                  : ((entry.raw as Record<string, unknown>).data ?? entry.raw)
              ) as Record<string, unknown>;
              return (
                <div
                  key={`${entry.type}-${globalIdx}`}
                  className="border border-light-gray dark:border-gray-700 rounded-lg p-3"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase ${
                        entry.type === "newsapi"
                          ? "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400"
                          : "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400"
                      }`}
                    >
                      {entry.type === "newsapi" ? "NewsAPI" : "GDELT"}
                    </span>
                    <p className="text-xs font-medium text-dark-gray dark:text-gray-200 line-clamp-1">
                      {String(entryData.title || `Raw article ${globalIdx + 1}`)}
                    </p>
                  </div>
                  {entryData.description ? (
                    <p className="text-[10px] text-medium-gray dark:text-gray-400 mt-0.5">
                      {String(entryData.description)}
                    </p>
                  ) : null}
                  {entry.type === "newsapi" ? (
                    <div className="flex gap-2 mt-1 text-[10px] text-medium-gray dark:text-gray-500">
                      {entryData.source ? (
                        <span>Source: {String(entryData.source)}</span>
                      ) : null}
                      {entryData.publishedAt ? (
                        <span>
                          {formatDate(
                            String(entryData.publishedAt),
                            "MMM d, yyyy HH:mm",
                          )}
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
          {rawTotalPages > 1 ? (
            <PaginationBar
              page={rawPage}
              totalPages={rawTotalPages}
              onPrev={() => setRawPage((p) => Math.max(1, p - 1))}
              onNext={() => setRawPage((p) => Math.min(rawTotalPages, p + 1))}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

type NewsTab = "supplier" | "global";

function NewsCombinedPanel({
  supplierState,
  globalState,
}: {
  supplierState?: Record<string, unknown>;
  globalState?: Record<string, unknown>;
}) {
  const supplierData = extractNewsData(supplierState);
  const globalData = extractNewsData(globalState);

  const availableTabs: NewsTab[] = [];
  if (supplierState) availableTabs.push("supplier");
  if (globalState) availableTabs.push("global");

  const [activeTab, setActiveTab] = useState<NewsTab>(
    availableTabs[0] ?? "supplier",
  );

  if (availableTabs.length === 0) return null;

  return (
    <Card>
      <div className="flex items-center gap-3 mb-2">
        <SectionHeading>News Agent State</SectionHeading>
      </div>

      {/* Inner tabs for Supplier / Global */}
      <div className="flex shrink-0 rounded-lg border border-light-gray dark:border-gray-600 overflow-hidden text-[12px] font-medium w-fit">
        {availableTabs.map((tab, i) => {
          const tabData = tab === "supplier" ? supplierData : globalData;
          const articleCount = tabData.newsItems.length + tabData.newsapiRaw.length + tabData.gdeltRaw.length;
          return (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 transition ${i > 0 ? "border-l border-light-gray dark:border-gray-600" : ""} ${
                activeTab === tab
                  ? "bg-primary-dark text-white dark:bg-primary-light dark:text-gray-900"
                  : "bg-white dark:bg-gray-800 text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-700"
              }`}
            >
              {tab === "supplier" ? "Supplier" : "Global"}
              {articleCount > 0 ? (
                <span className="ml-1.5 opacity-70">({articleCount})</span>
              ) : null}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      {activeTab === "supplier" ? (
        <NewsSourceContent key="supplier" data={supplierData} />
      ) : null}
      {activeTab === "global" ? (
        <NewsSourceContent key="global" data={globalData} />
      ) : null}
    </Card>
  );
}

function ShippingStatePanel({ state }: { state: Record<string, unknown> }) {
  const trackingRecords = state.tracking_records as
    | Record<string, unknown>[]
    | undefined;
  const supplierData = state.supplier_data as
    | Record<string, unknown>
    | undefined;
  const riskResult = state.shipping_risk_result as
    | ShippingRiskResult
    | undefined;

  // Convert checkpoint-based tracking records to TrackingActivity[] for the timeline
  const timelineActivities: TrackingActivity[] = [];
  if (trackingRecords) {
    for (const rec of trackingRecords) {
      const checkpoints = rec.checkpoints as
        | Record<string, unknown>[]
        | undefined;
      if (checkpoints && Array.isArray(checkpoints)) {
        for (const cp of checkpoints) {
          const loc = cp.location as Record<string, unknown> | undefined;
          const locationStr = loc
            ? [loc.city, loc.country].filter(Boolean).join(", ")
            : undefined;
          timelineActivities.push({
            status: cp.status as string | undefined,
            location: locationStr,
            sequence: cp.sequence as number | undefined,
            planned_arrival: cp.planned_arrival as string | undefined,
            actual_arrival: cp.actual_arrival as string | undefined,
            departure_time: cp.departure_time as string | undefined,
            transport_mode: cp.transport_mode as string | undefined,
          });
        }
      }
    }
  }

  return (
    <Card>
      <SectionHeading>Shipping Agent State</SectionHeading>

      {supplierData ? (
        <div className="flex flex-wrap gap-2 mt-3 mb-4 text-[10px] text-medium-gray dark:text-gray-500">
          {supplierData.name ? (
            <span className="px-1.5 py-0.5 rounded bg-off-white dark:bg-gray-700">
              {String(supplierData.name)}
            </span>
          ) : null}
          {supplierData.city ? (
            <span className="px-1.5 py-0.5 rounded bg-off-white dark:bg-gray-700">
              {String(supplierData.city)}
              {supplierData.country ? `, ${String(supplierData.country)}` : ""}
            </span>
          ) : null}
        </div>
      ) : null}

      {/* Risk overview — reused from ShippingRiskDashboard */}
      {riskResult ? (
        <div className="mb-5">
          <ShippingRiskOverview result={riskResult} />
        </div>
      ) : null}

      {/* Tracking timeline — reused from ShippingRiskDashboard */}
      {timelineActivities.length > 0 ? (
        <TrackingTimelineView timeline={timelineActivities} />
      ) : null}

      {timelineActivities.length === 0 && !riskResult ? (
        <p className="text-xs text-medium-gray dark:text-gray-400 mt-3">
          No shipping data available.
        </p>
      ) : null}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Agent data tabs                                                       */
/* ------------------------------------------------------------------ */

type AgentTab = "weather" | "news" | "shipping";

const agentTabMeta: Record<AgentTab, { label: string; icon: string }> = {
  weather: { label: "Weather", icon: "🌤" },
  news: { label: "News", icon: "📰" },
  shipping: { label: "Shipping", icon: "🚢" },
};

function AgentDataTabs({
  agentStates,
}: {
  agentStates: Record<string, unknown>;
}) {
  const availableTabs: AgentTab[] = [];
  if (agentStates.weather) availableTabs.push("weather");
  if (agentStates.news_supplier || agentStates.news_global)
    availableTabs.push("news");
  if (agentStates.shipping) availableTabs.push("shipping");

  const [activeTab, setActiveTab] = useState<AgentTab>(
    availableTabs[0] ?? "weather",
  );

  if (availableTabs.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-4 mb-4">
        <h2 className="text-sm font-semibold text-dark-gray dark:text-gray-200 uppercase tracking-wider">
          Agent Data
        </h2>
        <div className="flex shrink-0 rounded-lg border border-light-gray dark:border-gray-600 overflow-hidden text-[12px] font-medium">
          {availableTabs.map((tab, i) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 transition ${i > 0 ? "border-l border-light-gray dark:border-gray-600" : ""} ${
                activeTab === tab
                  ? "bg-primary-dark text-white dark:bg-primary-light dark:text-gray-900"
                  : "bg-white dark:bg-gray-800 text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-700"
              }`}
            >
              <span className="mr-1.5">{agentTabMeta[tab].icon}</span>
              {agentTabMeta[tab].label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "weather" && agentStates.weather ? (
        <WeatherStatePanel
          state={agentStates.weather as Record<string, unknown>}
        />
      ) : null}

      {activeTab === "news" ? (
        <NewsCombinedPanel
          supplierState={
            agentStates.news_supplier as Record<string, unknown> | undefined
          }
          globalState={
            agentStates.news_global as Record<string, unknown> | undefined
          }
        />
      ) : null}

      {activeTab === "shipping" && agentStates.shipping ? (
        <ShippingStatePanel
          state={agentStates.shipping as Record<string, unknown>}
        />
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                       */
/* ------------------------------------------------------------------ */

export function AnalysisReportClient({
  supplierId,
  sraId,
}: {
  supplierId: string;
  sraId: string;
}) {
  const { isLoggedIn, hydrated } = useAuth();

  const {
    data: report,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["analysis-report", supplierId, sraId],
    queryFn: () => suppliersApi.getAnalysisReport(supplierId, sraId),
    enabled: hydrated && isLoggedIn === true,
  });

  if (!hydrated || !isLoggedIn) return null;

  return (
    <div className="min-h-screen bg-off-white dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 shadow-sm border-b border-light-gray dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center gap-4">
            <Link
              href={`/suppliers/${supplierId}`}
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
              Back
            </Link>
            <div>
              <h1 className="heading-3 text-primary-dark dark:text-primary-light">
                Analysis Report
              </h1>
              {report ? (
                <p className="body-text text-medium-gray dark:text-gray-400">
                  {report.supplier.name}
                  {report.workflowRun?.runIndex != null
                    ? ` — Run #${report.workflowRun.runIndex}`
                    : null}
                  {report.workflowRun?.runDate
                    ? ` — ${formatDate(report.workflowRun.runDate, "MMM d, yyyy")}`
                    : null}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {isLoading ? (
          <div className="animate-pulse space-y-4">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-32 bg-light-gray dark:bg-gray-700 rounded-xl"
              />
            ))}
          </div>
        ) : isError || !report ? (
          <Card>
            <p className="text-sm text-medium-gray dark:text-gray-400">
              Could not load analysis data for this run.
            </p>
          </Card>
        ) : (
          <div className="space-y-6">
            {/* AI Risk Analysis Score */}
            {report.riskAnalysis ? (
              <Card className="border-violet-200 dark:border-violet-800">
                <div className="flex items-center gap-3 mb-3">
                  <span className="rounded-md bg-violet-100 dark:bg-violet-900/30 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-400">
                    AI Risk Analysis
                  </span>
                  <span className="text-sm font-semibold text-dark-gray dark:text-gray-200">
                    Score: {report.riskAnalysis.riskScore.toFixed(1)}/100
                  </span>
                </div>
                {report.riskAnalysis.description ? (
                  <p className="text-sm leading-relaxed text-dark-gray/80 dark:text-gray-300">
                    {report.riskAnalysis.description}
                  </p>
                ) : null}
              </Card>
            ) : null}

            {/* Swarm Analysis */}
            {report.swarmAnalysis ? (
              <Card>
                <div className="flex items-center gap-3 mb-4">
                  <SectionHeading>Swarm Analysis</SectionHeading>
                  <span
                    className={`inline-flex items-center px-2.5 py-0.5 rounded-lg text-xs font-semibold ${swarmLevelBadgeClasses[report.swarmAnalysis.riskLevel] ?? "bg-light-gray/50 text-dark-gray"}`}
                  >
                    {report.swarmAnalysis.riskLevel}
                  </span>
                  <span className="text-xs text-medium-gray dark:text-gray-400">
                    Score: {report.swarmAnalysis.finalScore}/100
                  </span>
                </div>

                {report.swarmAnalysis.topDrivers.length > 0 ? (
                  <div className="mb-4">
                    <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-2">
                      Top Risk Drivers
                    </p>
                    <ul className="space-y-1">
                      {report.swarmAnalysis.topDrivers.map((d, i) => (
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
                ) : null}

                {report.swarmAnalysis.mitigationPlan.length > 0 ? (
                  <div className="mb-4">
                    <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-2">
                      Suggested Mitigations
                    </p>
                    <ul className="space-y-1">
                      {report.swarmAnalysis.mitigationPlan.map((m, i) => (
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
                ) : null}

                {report.swarmAnalysis.agents.length > 0 ? (
                  <div>
                    <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-2">
                      Agent Breakdown
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      {report.swarmAnalysis.agents.map((agent) => (
                        <AgentBreakdownCard
                          key={agent.agentType}
                          agent={agent}
                        />
                      ))}
                    </div>
                  </div>
                ) : null}
              </Card>
            ) : null}

            {/* Agent Data (tabbed) */}
            {report.agentStates &&
            Object.keys(report.agentStates).length > 0 ? (
              <AgentDataTabs agentStates={report.agentStates} />
            ) : null}

            {/* Risks */}
            <Card>
              <div className="flex items-center justify-between mb-4">
                <SectionHeading>
                  Risks ({report.risksSummary.total})
                </SectionHeading>
                {Object.keys(report.risksSummary.bySeverity).length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(report.risksSummary.bySeverity)
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
              {report.risks.length === 0 ? (
                <p className="text-sm text-medium-gray dark:text-gray-400">
                  No risks detected in this workflow run.
                </p>
              ) : (
                <div className="grid grid-cols-1 gap-3">
                  {report.risks.map((r) => (
                    <RiskCard key={r.id} risk={r} />
                  ))}
                </div>
              )}
            </Card>

            {/* Opportunities */}
            {report.opportunities.length > 0 ? (
              <Card>
                <SectionHeading>
                  Opportunities ({report.opportunities.length})
                </SectionHeading>
                <div className="grid grid-cols-1 gap-3 mt-4">
                  {report.opportunities.map((o: MetricsOpportunity) => (
                    <div
                      key={o.id}
                      className="border border-light-gray dark:border-gray-700 rounded-lg p-4"
                    >
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <h4 className="text-sm font-medium text-dark-gray dark:text-gray-200 leading-snug">
                          {o.title}
                        </h4>
                        <span className="shrink-0 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
                          {o.type.replace(/_/g, " ")}
                        </span>
                      </div>
                      <p className="text-xs text-medium-gray dark:text-gray-400 line-clamp-2">
                        {o.description}
                      </p>
                    </div>
                  ))}
                </div>
              </Card>
            ) : null}

            {/* Mitigation Plans */}
            {report.mitigationPlans.length > 0 ? (
              <Card>
                <SectionHeading>
                  Mitigation Plans ({report.mitigationPlans.length})
                </SectionHeading>
                <div className="space-y-3 mt-4">
                  {report.mitigationPlans.map((mp: MetricsMitigationPlan) => (
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
                      {mp.actions.length > 0 ? (
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
                      ) : null}
                    </div>
                  ))}
                </div>
              </Card>
            ) : null}
          </div>
        )}
      </main>
    </div>
  );
}
