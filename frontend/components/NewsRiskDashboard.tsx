'use client';

import { useEffect, useState, useCallback } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { risksApi, suppliersApi, agentApi, trendInsightsApi, type Risk, type Supplier, type TrendInsightItem, type TrendInsightRunResult } from '@/lib/api';

// ── Colour maps (same tokens as RisksList) ────────────────────────────────────

const severityColors: Record<string, string> = {
  low: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  high: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const severityDot: Record<string, string> = {
  low: 'bg-green-500',
  medium: 'bg-yellow-500',
  high: 'bg-orange-500',
  critical: 'bg-red-500',
};

const statusColors: Record<string, string> = {
  detected: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  analyzing: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  mitigating: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  resolved: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  false_positive: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
};

const riskTypeBadge: Record<string, string> = {
  factory_shutdown: 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400',
  labor_strike: 'bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-400',
  bankruptcy_risk: 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400',
  sanction_risk: 'bg-purple-50 text-purple-700 dark:bg-purple-900/20 dark:text-purple-400',
  port_congestion: 'bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400',
  natural_disaster: 'bg-teal-50 text-teal-700 dark:bg-teal-900/20 dark:text-teal-400',
  geopolitical_tension: 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-400',
  regulatory_change: 'bg-sky-50 text-sky-700 dark:bg-sky-900/20 dark:text-sky-400',
  infrastructure_failure: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400',
  commodity_shortage: 'bg-lime-50 text-lime-700 dark:bg-lime-900/20 dark:text-lime-400',
  cyber_incident: 'bg-rose-50 text-rose-700 dark:bg-rose-900/20 dark:text-rose-400',
};

const defaultBadge = 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';

// ── Context badge (supplier vs global) ───────────────────────────────────────

function contextLabel(sourceData?: Record<string, unknown> | null) {
  const ctx = sourceData?.context as string | undefined;
  if (ctx === 'global') return { label: 'Global', cls: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' };
  if (ctx === 'supplier') return { label: 'Supplier', cls: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400' };
  return null;
}

// ── Risk card ─────────────────────────────────────────────────────────────────

function NewsRiskCard({ risk }: { risk: Risk }) {
  const riskType = risk.sourceData?.risk_type as string | undefined;
  const source = risk.sourceData?.source as string | undefined;
  const ctx = contextLabel(risk.sourceData);

  return (
    <div className="rounded-xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-4 shadow-sm hover:shadow-md transition-shadow">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-start gap-2 min-w-0">
          <span
            className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${severityDot[risk.severity] ?? 'bg-gray-400'}`}
          />
          <h3 className="text-[14px] font-semibold leading-snug text-dark-gray dark:text-gray-100">
            {risk.title}
          </h3>
        </div>
        <div className="flex shrink-0 flex-wrap gap-1.5">
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${severityColors[risk.severity] ?? defaultBadge}`}>
            {risk.severity}
          </span>
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${statusColors[risk.status] ?? defaultBadge}`}>
            {risk.status.replace('_', ' ')}
          </span>
        </div>
      </div>

      {/* Description */}
      <p className="text-[13px] leading-relaxed text-medium-gray dark:text-gray-400 mb-3 line-clamp-3">
        {risk.description}
      </p>

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        {riskType && (
          <span className={`rounded-md px-2 py-0.5 font-medium ${riskTypeBadge[riskType] ?? defaultBadge}`}>
            {riskType.replace(/_/g, ' ')}
          </span>
        )}
        {ctx && (
          <span className={`rounded-md px-2 py-0.5 font-medium ${ctx.cls}`}>
            {ctx.label}
          </span>
        )}
        {risk.affectedRegion && (
          <span className="text-medium-gray dark:text-gray-400">
            📍 {risk.affectedRegion}
          </span>
        )}
        {risk.affectedSupplier && (
          <span className="text-medium-gray dark:text-gray-400">
            🏭 {risk.affectedSupplier}
          </span>
        )}
        {risk.estimatedCost != null && (
          <span className="text-medium-gray dark:text-gray-400">
            💰 ${Number(risk.estimatedCost).toLocaleString()}
          </span>
        )}
        {source && (
          <span className="text-medium-gray dark:text-gray-400 truncate max-w-[140px]" title={source}>
            📰 {source}
          </span>
        )}
        <span className="ml-auto text-medium-gray dark:text-gray-500 shrink-0">
          {formatDistanceToNow(new Date(risk.createdAt), { addSuffix: true })}
        </span>
      </div>
    </div>
  );
}

// ── Summary stats bar ─────────────────────────────────────────────────────────

function SeveritySummary({ risks }: { risks: Risk[] }) {
  const counts = risks.reduce<Record<string, number>>(
    (acc, r) => { acc[r.severity] = (acc[r.severity] ?? 0) + 1; return acc; },
    {}
  );
  const items = [
    { label: 'Critical', key: 'critical', cls: 'text-red-600 dark:text-red-400' },
    { label: 'High', key: 'high', cls: 'text-orange-600 dark:text-orange-400' },
    { label: 'Medium', key: 'medium', cls: 'text-yellow-600 dark:text-yellow-400' },
    { label: 'Low', key: 'low', cls: 'text-green-600 dark:text-green-400' },
  ];
  return (
    <div className="flex flex-wrap gap-4">
      <div className="text-[13px] font-semibold text-dark-gray dark:text-gray-200">
        {risks.length} risk{risks.length !== 1 ? 's' : ''}
      </div>
      {items.map(({ label, key, cls }) =>
        counts[key] ? (
          <span key={key} className={`text-[12px] font-medium ${cls}`}>
            {counts[key]} {label}
          </span>
        ) : null
      )}
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ supplierId }: { supplierId: string | null }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-light-gray dark:border-gray-600 py-16 text-center">
      <div className="rounded-full bg-sky-blue/30 dark:bg-gray-700/50 p-3">
        <svg className="h-8 w-8 text-primary-dark dark:text-primary-light" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z"
          />
        </svg>
      </div>
      <p className="text-[14px] font-medium text-dark-gray dark:text-gray-200">No news risks found</p>
      <p className="text-[12px] text-medium-gray dark:text-gray-400 max-w-xs">
        {supplierId
          ? 'No news-sourced risks for this supplier yet. Trigger the agent workflow to fetch the latest.'
          : 'No news-sourced risks yet. Trigger the agent workflow to fetch and analyse the latest supply chain news.'}
      </p>
    </div>
  );
}

// ── Dev JSON view ─────────────────────────────────────────────────────────────

function DevView({ risks, copied, onCopy }: { risks: Risk[]; copied: boolean; onCopy: () => void }) {
  return (
    <div className="rounded-xl border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50 p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div>
          <div className="text-[13px] font-semibold text-dark-gray dark:text-gray-200">
            Raw JSON — News Risk Payload
          </div>
          <div className="text-[11px] text-medium-gray dark:text-gray-400">
            {risks.length} risk record{risks.length !== 1 ? 's' : ''} · sourceType: news
          </div>
        </div>
        <button
          type="button"
          onClick={onCopy}
          className="shrink-0 rounded-lg border border-primary-light/40 bg-white dark:bg-gray-800 px-3 py-1.5 text-[12px] font-medium text-primary-dark dark:text-primary-light transition hover:bg-sky-blue/10"
        >
          {copied ? '✓ Copied!' : 'Copy JSON'}
        </button>
      </div>
      <pre className="overflow-auto rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-3 text-[11px] leading-relaxed text-dark-gray dark:text-gray-300 max-h-[60vh]">
        {JSON.stringify(risks, null, 2)}
      </pre>
    </div>
  );
}

// ── Trend insight helpers ─────────────────────────────────────────────────────

const scopeColors: Record<string, string> = {
  supplier: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400',
  material: 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400',
  global:   'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
};

const horizonColors: Record<string, string> = {
  short:  'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  long:   'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
};

function horizonKey(horizon: string | null | undefined) {
  if (!horizon) return '';
  const h = horizon.toLowerCase();
  if (h.includes('short') || h.includes('immediate') || h.includes('week')) return 'short';
  if (h.includes('long') || h.includes('year')) return 'long';
  return 'medium';
}

// ── Trend insight card ────────────────────────────────────────────────────────

function TrendInsightCard({ insight }: { insight: TrendInsightItem }) {
  const [expanded, setExpanded] = useState(false);
  const isRisk = insight.risk_opportunity === 'risk';
  const hKey = horizonKey(insight.time_horizon);

  return (
    <div className="rounded-xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-4 shadow-sm hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-start gap-2 min-w-0">
          <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
            isRisk
              ? (severityDot[insight.severity ?? ''] ?? 'bg-gray-400')
              : 'bg-emerald-500'
          }`} />
          <h3 className="text-[14px] font-semibold leading-snug text-dark-gray dark:text-gray-100">
            {insight.title}
          </h3>
        </div>
        <div className="flex shrink-0 flex-wrap gap-1.5">
          {/* risk / opportunity */}
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
            isRisk
              ? 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
              : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400'
          }`}>
            {isRisk ? '⚠ Risk' : '✦ Opportunity'}
          </span>
          {/* severity */}
          {insight.severity && (
            <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
              severityColors[insight.severity] ?? defaultBadge
            }`}>
              {insight.severity}
            </span>
          )}
        </div>
      </div>

      {/* Description */}
      {insight.description && (
        <p className="text-[13px] leading-relaxed text-medium-gray dark:text-gray-400 mb-3 line-clamp-3">
          {insight.description}
        </p>
      )}

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-2 text-[11px] mb-2">
        {insight.scope && (
          <span className={`rounded-md px-2 py-0.5 font-medium ${scopeColors[insight.scope] ?? defaultBadge}`}>
            {insight.scope}
          </span>
        )}
        {insight.entity_name && (
          <span className="text-medium-gray dark:text-gray-400">
            🏭 {insight.entity_name}
          </span>
        )}
        {insight.time_horizon && (
          <span className={`rounded-md px-2 py-0.5 font-medium ${horizonColors[hKey] ?? defaultBadge}`}>
            ⏱ {insight.time_horizon}
          </span>
        )}
        {insight.confidence != null && (
          <span className="text-medium-gray dark:text-gray-400">
            {Math.round(insight.confidence * 100)}% confidence
          </span>
        )}
        <span className="ml-auto text-medium-gray dark:text-gray-500 shrink-0">
          {formatDistanceToNow(new Date(insight.createdAt), { addSuffix: true })}
        </span>
      </div>

      {/* Predicted impact */}
      {insight.predicted_impact && (
        <div className="mb-2 rounded-lg bg-amber-50 dark:bg-amber-900/10 border border-amber-100 dark:border-amber-900/30 px-3 py-2 text-[12px] text-amber-800 dark:text-amber-300">
          <span className="font-semibold">Predicted impact: </span>{insight.predicted_impact}
        </div>
      )}

      {/* Recommended actions */}
      {insight.recommended_actions && insight.recommended_actions.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1.5 text-[11px] font-semibold text-primary-dark dark:text-primary-light hover:underline"
          >
            <svg
              className={`h-3 w-3 transition-transform ${expanded ? 'rotate-90' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            {expanded ? 'Hide' : 'Show'} {insight.recommended_actions.length} recommended action{insight.recommended_actions.length !== 1 ? 's' : ''}
          </button>
          {expanded && (
            <ul className="mt-2 space-y-1.5 pl-2">
              {insight.recommended_actions.map((action, i) => (
                <li key={i} className="flex gap-2 text-[12px] text-dark-gray dark:text-gray-300">
                  <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary-dark dark:bg-primary-light" />
                  {action}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ── Trend summary stats ───────────────────────────────────────────────────────

function TrendSummary({ insights }: { insights: TrendInsightItem[] }) {
  const risks = insights.filter((i) => i.risk_opportunity === 'risk').length;
  const opps = insights.filter((i) => i.risk_opportunity === 'opportunity').length;
  const byScope = insights.reduce<Record<string, number>>((acc, i) => {
    acc[i.scope] = (acc[i.scope] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="flex flex-wrap gap-4">
      <div className="text-[13px] font-semibold text-dark-gray dark:text-gray-200">
        {insights.length} insight{insights.length !== 1 ? 's' : ''}
      </div>
      {risks > 0 && (
        <span className="text-[12px] font-medium text-red-600 dark:text-red-400">
          {risks} risk{risks !== 1 ? 's' : ''}
        </span>
      )}
      {opps > 0 && (
        <span className="text-[12px] font-medium text-emerald-600 dark:text-emerald-400">
          {opps} opportunit{opps !== 1 ? 'ies' : 'y'}
        </span>
      )}
      {Object.entries(byScope).map(([scope, n]) => (
        <span key={scope} className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${scopeColors[scope] ?? defaultBadge}`}>
          {n} {scope}
        </span>
      ))}
    </div>
  );
}

// ── Trend dev view ────────────────────────────────────────────────────────────

function TrendDevView({ result, copied, onCopy }: { result: TrendInsightRunResult; copied: boolean; onCopy: () => void }) {
  return (
    <div className="rounded-xl border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50 p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div>
          <div className="text-[13px] font-semibold text-dark-gray dark:text-gray-200">
            Raw JSON — Trend Insights Payload
          </div>
          <div className="text-[11px] text-medium-gray dark:text-gray-400">
            {result.insights_generated} insight{result.insights_generated !== 1 ? 's' : ''} · provider: {result.llm_provider}
          </div>
        </div>
        <button
          type="button"
          onClick={onCopy}
          className="shrink-0 rounded-lg border border-primary-light/40 bg-white dark:bg-gray-800 px-3 py-1.5 text-[12px] font-medium text-primary-dark dark:text-primary-light transition hover:bg-sky-blue/10"
        >
          {copied ? '✓ Copied!' : 'Copy JSON'}
        </button>
      </div>
      <pre className="overflow-auto rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-3 text-[11px] leading-relaxed text-dark-gray dark:text-gray-300 max-h-[60vh]">
        {JSON.stringify(result, null, 2)}
      </pre>
    </div>
  );
}

// ── Main dashboard ────────────────────────────────────────────────────────────

export function NewsRiskDashboard() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loadingSuppliers, setLoadingSuppliers] = useState(true);
  const [selectedSupplierId, setSelectedSupplierId] = useState<string | null>(null);

  // ── Active tab ─────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<'news' | 'trends'>('news');

  // ── News risks ─────────────────────────────────────────────────────────────
  const [allRisks, setAllRisks] = useState<Risk[]>([]);
  const [loadingRisks, setLoadingRisks] = useState(true);
  const [newsDevView, setNewsDevView] = useState(false);
  const [newsCopied, setNewsCopied] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [lastNewsResult, setLastNewsResult] = useState<{ risksCreated: number; opportunitiesCreated: number } | null>(null);

  // ── Trend insights ─────────────────────────────────────────────────────────
  const [trendResult, setTrendResult] = useState<TrendInsightRunResult | null>(null);
  const [loadingTrends, setLoadingTrends] = useState(false);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [trendsDevView, setTrendsDevView] = useState(false);
  const [trendsCopied, setTrendsCopied] = useState(false);

  // ── Load suppliers on mount ────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    suppliersApi
      .getAll()
      .then((data) => { if (!cancelled) setSuppliers(Array.isArray(data) ? data : []); })
      .catch(() => { if (!cancelled) setSuppliers([]); })
      .finally(() => { if (!cancelled) setLoadingSuppliers(false); });
    return () => { cancelled = true; };
  }, []);

  // Reset trend results when supplier changes
  useEffect(() => {
    setTrendResult(null);
    setTrendError(null);
    setTrendsDevView(false);
  }, [selectedSupplierId]);

  // ── Fetch news risks ───────────────────────────────────────────────────────
  const fetchRisks = useCallback(() => {
    setLoadingRisks(true);
    risksApi
      .getAll({ sourceType: 'news' })
      .then((data) => setAllRisks(Array.isArray(data) ? data : []))
      .catch(() => setAllRisks([]))
      .finally(() => setLoadingRisks(false));
  }, []);

  useEffect(() => { fetchRisks(); }, [fetchRisks]);

  // ── Trigger news analysis ──────────────────────────────────────────────────
  async function handleRunAnalysis() {
    setIsAnalyzing(true);
    setAnalyzeError(null);
    setLastNewsResult(null);
    try {
      const result = await agentApi.triggerNewsAnalysis();
      setLastNewsResult({ risksCreated: result.risksCreated, opportunitiesCreated: result.opportunitiesCreated });
      fetchRisks();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Analysis failed. Check server logs.';
      setAnalyzeError(message);
    } finally {
      setIsAnalyzing(false);
    }
  }

  // ── Trigger trend analysis ─────────────────────────────────────────────────
  async function handleRunTrendAnalysis() {
    if (!selectedSupplierId) return;
    setLoadingTrends(true);
    setTrendError(null);
    setTrendResult(null);
    setTrendsDevView(false);
    try {
      const result = await trendInsightsApi.runForSupplier(selectedSupplierId);
      setTrendResult(result);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Trend analysis failed. Check server logs.';
      setTrendError(message);
    } finally {
      setLoadingTrends(false);
    }
  }

  function handleNewsCopy() {
    navigator.clipboard.writeText(JSON.stringify(risks, null, 2)).then(() => {
      setNewsCopied(true);
      setTimeout(() => setNewsCopied(false), 2500);
    });
  }

  function handleTrendsCopy() {
    if (!trendResult) return;
    navigator.clipboard.writeText(JSON.stringify(trendResult, null, 2)).then(() => {
      setTrendsCopied(true);
      setTimeout(() => setTrendsCopied(false), 2500);
    });
  }

  const selectedSupplier = suppliers.find((s) => s.id === selectedSupplierId) ?? null;

  const risks = selectedSupplier
    ? allRisks.filter(
        (r) =>
          (r.affectedSupplier &&
            r.affectedSupplier.toLowerCase() === selectedSupplier.name.toLowerCase()) ||
          r.supplierId === selectedSupplier.id
      )
    : allRisks;

  return (
    <main className="mx-auto grid grid-cols-1 gap-6 lg:grid-cols-[minmax(260px,320px)_1fr]">
      {/* ── Left: Supplier list ──────────────────────────────────────────── */}
      <section className="rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="heading-3 text-dark-gray dark:text-gray-200 uppercase tracking-wider">
            Suppliers
          </h2>
          <span className="rounded-full border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700/50 px-2 py-0.5 text-xs text-medium-gray dark:text-gray-400">
            News filter
          </span>
        </div>

        <div className="max-h-[calc(100vh-220px)] overflow-y-auto pr-1 space-y-1.5">
          {/* All suppliers option */}
          <button
            type="button"
            onClick={() => setSelectedSupplierId(null)}
            className={`w-full text-left rounded-xl border px-3 py-2.5 transition hover:border-primary-light/50 hover:bg-sky-blue/20 dark:hover:bg-gray-700/50 ${
              selectedSupplierId === null
                ? 'border-primary-dark bg-sky-blue/30 dark:bg-gray-700'
                : 'border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-800'
            }`}
          >
            <span className="text-[13px] font-semibold text-dark-gray dark:text-gray-200">
              All Suppliers
            </span>
            <p className="text-[11px] text-medium-gray dark:text-gray-400">Global + supplier risks</p>
          </button>

          {loadingSuppliers ? (
            <div className="space-y-2 pt-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="animate-pulse rounded-xl border border-light-gray dark:border-gray-700 p-3">
                  <div className="h-3 w-2/3 rounded bg-light-gray dark:bg-gray-700 mb-1.5" />
                  <div className="h-2.5 w-1/2 rounded bg-light-gray dark:bg-gray-700" />
                </div>
              ))}
            </div>
          ) : suppliers.length === 0 ? (
            <p className="pt-2 text-[12px] text-medium-gray dark:text-gray-400">No suppliers found.</p>
          ) : (
            suppliers.map((s) => {
              const level = (s.latestRiskLevel ?? '').toLowerCase();
              const levelDot =
                level === 'critical' ? 'bg-red-500' :
                level === 'high' ? 'bg-orange-500' :
                level === 'medium' ? 'bg-yellow-500' :
                level === 'low' ? 'bg-green-500' : 'bg-gray-400';

              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSelectedSupplierId(s.id)}
                  className={`w-full text-left rounded-xl border p-3 transition hover:border-primary-light/50 hover:bg-sky-blue/20 dark:hover:bg-gray-700/50 ${
                    selectedSupplierId === s.id
                      ? 'border-primary-dark bg-sky-blue/30 dark:bg-gray-700'
                      : 'border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-800'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${levelDot}`} />
                    <span className="text-[13px] font-medium text-dark-gray dark:text-gray-200 truncate">
                      {s.name}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-medium-gray dark:text-gray-400 pl-4">
                    {s.city && <span>{s.city}</span>}
                    {s.country && <span>{s.country}</span>}
                    {s.commodities && (
                      <span className="truncate max-w-[120px]" title={s.commodities}>
                        {s.commodities.split(',')[0].trim()}
                      </span>
                    )}
                  </div>
                </button>
              );
            })
          )}
        </div>
      </section>

      {/* ── Right: tabbed feed ───────────────────────────────────────────── */}
      <section className="flex flex-col gap-4 min-w-0">

        {/* ── Tab header ─────────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 px-5 py-4 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            {/* Title */}
            <div className="min-w-0">
              <h2 className="heading-3 text-dark-gray dark:text-gray-200 uppercase tracking-wider truncate">
                {selectedSupplier ? selectedSupplier.name : 'All Suppliers'}
              </h2>
              <p className="text-[12px] text-medium-gray dark:text-gray-400 mt-0.5">
                {selectedSupplier
                  ? `Analysis for ${selectedSupplier.name}`
                  : 'All news-sourced supply chain risks'}
              </p>
            </div>

            {/* Tab switcher */}
            <div className="flex shrink-0 rounded-lg border border-light-gray dark:border-gray-600 overflow-hidden text-[12px] font-medium self-start">
              <button
                type="button"
                onClick={() => setActiveTab('news')}
                className={`px-4 py-2 transition ${
                  activeTab === 'news'
                    ? 'bg-primary-dark text-white dark:bg-primary-light dark:text-gray-900'
                    : 'bg-white dark:bg-gray-800 text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-700'
                }`}
              >
                📰 News Risks
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('trends')}
                className={`px-4 py-2 border-l border-light-gray dark:border-gray-600 transition ${
                  activeTab === 'trends'
                    ? 'bg-primary-dark text-white dark:bg-primary-light dark:text-gray-900'
                    : 'bg-white dark:bg-gray-800 text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-700'
                }`}
              >
                ✦ Trend Insights
              </button>
            </div>
          </div>

          {/* Tab-specific toolbar */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {activeTab === 'news' && (
              <>
                {!loadingRisks && risks.length > 0 && <SeveritySummary risks={risks} />}
                <div className="ml-auto flex gap-2">
                  <button
                    type="button"
                    onClick={handleRunAnalysis}
                    disabled={isAnalyzing}
                    className="rounded-lg border border-primary-dark bg-primary-dark px-3 py-1.5 text-[12px] font-medium text-white transition hover:opacity-90 disabled:opacity-60 dark:bg-primary-light dark:border-primary-light dark:text-gray-900"
                  >
                    {isAnalyzing ? 'Analysing…' : 'Run News Analysis'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setNewsDevView((v) => !v)}
                    className={`rounded-lg border px-3 py-1.5 text-[12px] font-medium transition ${
                      newsDevView
                        ? 'border-primary-dark bg-primary-dark text-white dark:bg-primary-light dark:border-primary-light dark:text-gray-900'
                        : 'border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700 text-dark-gray dark:text-gray-200 hover:bg-sky-blue/10'
                    }`}
                  >
                    {newsDevView ? '← Card View' : 'Dev View { }'}
                  </button>
                </div>
              </>
            )}

            {activeTab === 'trends' && (
              <>
                {trendResult && !loadingTrends && (
                  <TrendSummary insights={trendResult.insights} />
                )}
                <div className="ml-auto flex gap-2">
                  <button
                    type="button"
                    onClick={handleRunTrendAnalysis}
                    disabled={loadingTrends || !selectedSupplierId}
                    title={!selectedSupplierId ? 'Select a supplier to run trend analysis' : undefined}
                    className="rounded-lg border border-primary-dark bg-primary-dark px-3 py-1.5 text-[12px] font-medium text-white transition hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed dark:bg-primary-light dark:border-primary-light dark:text-gray-900"
                  >
                    {loadingTrends ? (
                      <span className="flex items-center gap-1.5">
                        <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                        </svg>
                        Analysing…
                      </span>
                    ) : 'Run Trend Analysis'}
                  </button>
                  {trendResult && (
                    <button
                      type="button"
                      onClick={() => setTrendsDevView((v) => !v)}
                      className={`rounded-lg border px-3 py-1.5 text-[12px] font-medium transition ${
                        trendsDevView
                          ? 'border-primary-dark bg-primary-dark text-white dark:bg-primary-light dark:border-primary-light dark:text-gray-900'
                          : 'border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700 text-dark-gray dark:text-gray-200 hover:bg-sky-blue/10'
                      }`}
                    >
                      {trendsDevView ? '← Card View' : 'Dev View { }'}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {/* ── NEWS TAB ───────────────────────────────────────────────────── */}
        {activeTab === 'news' && (
          <>
            {isAnalyzing && (
              <div className="flex items-center gap-3 rounded-xl border border-sky-200 dark:border-sky-800 bg-sky-50 dark:bg-sky-900/20 px-4 py-3 text-[13px] text-sky-800 dark:text-sky-300">
                <svg className="h-4 w-4 animate-spin shrink-0" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Fetching news from NewsAPI &amp; GDELT and running LLM risk extraction — this may take 30–60 seconds…
              </div>
            )}
            {!isAnalyzing && lastNewsResult && (
              <div className="flex items-center gap-2 rounded-xl border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 px-4 py-3 text-[13px] text-green-800 dark:text-green-300">
                <span>✓</span>
                <span>
                  Analysis complete — <strong>{lastNewsResult.risksCreated}</strong> risk{lastNewsResult.risksCreated !== 1 ? 's' : ''} and{' '}
                  <strong>{lastNewsResult.opportunitiesCreated}</strong> opportunit{lastNewsResult.opportunitiesCreated !== 1 ? 'ies' : 'y'} created.
                </span>
              </div>
            )}
            {analyzeError && (
              <div className="flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-[13px] text-red-800 dark:text-red-300">
                <span className="shrink-0">⚠</span>
                <span>{analyzeError}</span>
              </div>
            )}
            {loadingRisks && (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="animate-pulse rounded-xl border border-light-gray dark:border-gray-700 p-4">
                    <div className="flex items-start justify-between mb-3">
                      <div className="h-3.5 w-2/3 rounded bg-light-gray dark:bg-gray-700" />
                      <div className="h-5 w-16 rounded bg-light-gray dark:bg-gray-700" />
                    </div>
                    <div className="space-y-1.5">
                      <div className="h-2.5 w-full rounded bg-light-gray dark:bg-gray-700" />
                      <div className="h-2.5 w-4/5 rounded bg-light-gray dark:bg-gray-700" />
                    </div>
                  </div>
                ))}
              </div>
            )}
            {!loadingRisks && (
              newsDevView ? (
                <DevView risks={risks} copied={newsCopied} onCopy={handleNewsCopy} />
              ) : risks.length === 0 ? (
                <EmptyState supplierId={selectedSupplierId} />
              ) : (
                <div className="space-y-3">
                  {risks.map((risk) => (
                    <NewsRiskCard key={risk.id} risk={risk} />
                  ))}
                </div>
              )
            )}
          </>
        )}

        {/* ── TRENDS TAB ────────────────────────────────────────────────── */}
        {activeTab === 'trends' && (
          <>
            {/* Select-supplier prompt */}
            {!selectedSupplierId && (
              <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-light-gray dark:border-gray-600 py-16 text-center">
                <div className="rounded-full bg-violet-100 dark:bg-violet-900/30 p-3">
                  <svg className="h-8 w-8 text-violet-600 dark:text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <p className="text-[14px] font-medium text-dark-gray dark:text-gray-200">Select a supplier</p>
                <p className="text-[12px] text-medium-gray dark:text-gray-400 max-w-xs">
                  Choose a supplier from the left panel to run an AI trend analysis scoped to their commodities and region.
                </p>
              </div>
            )}

            {/* Loading skeleton */}
            {loadingTrends && (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="animate-pulse rounded-xl border border-light-gray dark:border-gray-700 p-4">
                    <div className="flex items-start justify-between mb-3">
                      <div className="h-3.5 w-2/3 rounded bg-light-gray dark:bg-gray-700" />
                      <div className="h-5 w-20 rounded bg-light-gray dark:bg-gray-700" />
                    </div>
                    <div className="space-y-1.5">
                      <div className="h-2.5 w-full rounded bg-light-gray dark:bg-gray-700" />
                      <div className="h-2.5 w-4/5 rounded bg-light-gray dark:bg-gray-700" />
                      <div className="h-2.5 w-3/5 rounded bg-light-gray dark:bg-gray-700" />
                    </div>
                  </div>
                ))}
                <div className="rounded-xl border border-sky-200 dark:border-sky-800 bg-sky-50 dark:bg-sky-900/20 px-4 py-3 text-[13px] text-sky-800 dark:text-sky-300">
                  Running LLM trend analysis for {selectedSupplier?.name} — fetching news signals and generating structured insights…
                </div>
              </div>
            )}

            {/* Error */}
            {!loadingTrends && trendError && (
              <div className="flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-[13px] text-red-800 dark:text-red-300">
                <span className="shrink-0">⚠</span>
                <span>{trendError}</span>
              </div>
            )}

            {/* Idle prompt (supplier selected, not yet run) */}
            {!loadingTrends && !trendError && !trendResult && selectedSupplierId && (
              <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-violet-200 dark:border-violet-800 py-16 text-center bg-violet-50/30 dark:bg-violet-900/10">
                <p className="text-[14px] font-medium text-dark-gray dark:text-gray-200">
                  Ready to analyse <span className="text-primary-dark dark:text-primary-light">{selectedSupplier?.name}</span>
                </p>
                <p className="text-[12px] text-medium-gray dark:text-gray-400 max-w-xs">
                  Click <strong>Run Trend Analysis</strong> above to fetch live news signals and generate AI-powered trend insights for this supplier's commodities and region.
                </p>
              </div>
            )}

            {/* Results */}
            {!loadingTrends && trendResult && (
              trendsDevView ? (
                <TrendDevView result={trendResult} copied={trendsCopied} onCopy={handleTrendsCopy} />
              ) : trendResult.insights.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-light-gray dark:border-gray-600 py-16 text-center">
                  <p className="text-[14px] font-medium text-dark-gray dark:text-gray-200">No insights generated</p>
                  <p className="text-[12px] text-medium-gray dark:text-gray-400 max-w-xs">
                    The LLM could not generate insights for this supplier. Try again or check the server logs.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {trendResult.insights.map((insight) => (
                    <TrendInsightCard key={insight.id} insight={insight} />
                  ))}
                </div>
              )
            )}
          </>
        )}
      </section>
    </main>
  );
}
