import axios from "axios";
import type {
  WeatherRiskResponse,
  ShipmentInput,
  ShipmentWeatherExposureResponse,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common["Authorization"];
  }
}

/** Call when backend returns 401 so auth state is cleared globally */
export const AUTH_UNAUTHORIZED_EVENT = "auth:unauthorized";

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401 && typeof window !== "undefined") {
      setAuthToken(null);
      localStorage.removeItem("oem_token");
      localStorage.removeItem("oem_user");
      window.dispatchEvent(new CustomEvent(AUTH_UNAUTHORIZED_EVENT));
    }
    return Promise.reject(err);
  },
);

// Types
export interface AgentStatus {
  id: string;
  status:
    | "idle"
    | "monitoring"
    | "analyzing"
    | "processing"
    | "completed"
    | "error";
  currentTask?: string;
  lastProcessedData?: Record<string, unknown>;
  lastDataSource?: string;
  errorMessage?: string;
  risksDetected: number;
  opportunitiesIdentified: number;
  plansGenerated: number;
  riskScore?: number | null;
  supplierName?: string;
  oemName?: string;
  lastUpdated: string;
  createdAt: string;
}

export interface Risk {
  id: string;
  title: string;
  description: string;
  severity: "low" | "medium" | "high" | "critical";
  status:
    | "detected"
    | "analyzing"
    | "mitigating"
    | "resolved"
    | "false_positive";
  sourceType: string;
  sourceData?: Record<string, unknown>;
  affectedRegion?: string;
  affectedSupplier?: string;
  estimatedImpact?: string;
  estimatedCost?: number;
  supplierId?: string;
  oemId?: string;
  mitigationPlans?: MitigationPlan[];
  createdAt: string;
  updatedAt: string;
}

export interface Opportunity {
  id: string;
  title: string;
  description: string;
  type:
    | "cost_saving"
    | "time_saving"
    | "quality_improvement"
    | "market_expansion"
    | "supplier_diversification";
  status: "identified" | "evaluating" | "implementing" | "realized" | "expired";
  sourceType: string;
  sourceData?: Record<string, unknown>;
  affectedRegion?: string;
  potentialBenefit?: string;
  estimatedValue?: number;
  mitigationPlans?: MitigationPlan[];
  createdAt: string;
  updatedAt: string;
}

export interface MitigationPlan {
  id: string;
  title: string;
  description: string;
  actions: string[];
  status: "draft" | "approved" | "in_progress" | "completed" | "cancelled";
  riskId?: string;
  opportunityId?: string;
  risk?: Risk;
  opportunity?: Opportunity;
  metadata?: Record<string, unknown>;
  assignedTo?: string;
  dueDate?: string;
  createdAt: string;
  updatedAt: string;
}

export interface SupplyChainRiskScore {
  id: string;
  oemId: string;
  overallScore: number;
  breakdown: Record<string, number> | null;
  severityCounts: Record<string, number> | null;
  summary: string | null;
  createdAt: string | null;
}

export interface SupplierRiskSummary {
  count: number;
  bySeverity: Record<string, number>;
  latest: { id: string; severity: string; title: string } | null;
}

export type SwarmAgentType = "WEATHER" | "SHIPPING" | "NEWS";

export type SwarmRiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface SwarmAgentResult {
  agentType: SwarmAgentType;
  score: number;
  riskLevel: SwarmRiskLevel;
  signals: string[];
  interpretedRisks: string[];
  confidence: number;
  metadata?: Record<string, unknown>;
}

export interface SupplierSwarmSummary {
  finalScore: number;
  riskLevel: SwarmRiskLevel;
  topDrivers: string[];
  mitigationPlan: string[];
  agents: SwarmAgentResult[];
}

export interface Oem {
  id: string;
  name: string;
  email: string;
  location?: string | null;
  city?: string | null;
  country?: string | null;
  countryCode?: string | null;
  region?: string | null;
  commodities?: string | null;
  metadata?: Record<string, string> | null;
  createdAt: string;
  updatedAt: string;
}

export interface OemUpdatePayload {
  name?: string;
  email?: string;
  location?: string;
  city?: string;
  country?: string;
  countryCode?: string;
  region?: string;
  commodities?: string;
}

export interface Supplier {
  id: string;
  name: string;
  location?: string | null;
  city?: string | null;
  country?: string | null;
  region?: string | null;
  commodities?: string | null;
  metadata?: Record<string, string> | null;
  latestRiskScore?: number | null;
  latestRiskLevel?: SwarmRiskLevel | null;
  createdAt: string;
  updatedAt: string;
  riskSummary: SupplierRiskSummary;
  aiReasoning?: string | null;
  swarm?: SupplierSwarmSummary | null;
}

// API functions
export const agentApi = {
  getStatus: () =>
    api.get<AgentStatus>("/agent/status").then((res) => res.data),
  triggerAnalysis: () => api.post("/agent/trigger").then((res) => res.data),
  triggerAnalysisV2: () =>
    api.post("/agent/trigger/v2").then((res) => res.data),
  triggerNewsAnalysis: (oemId?: string, supplierId?: string) =>
    api
      .post<{
        message: string;
        oemId: string;
        risksCreated: number;
        opportunitiesCreated: number;
      }>("/agent/trigger/news", {
        ...(oemId ? { oemId } : {}),
        ...(supplierId ? { supplierId } : {}),
      })
      .then((res) => res.data),
};

export const risksApi = {
  getAll: (params?: {
    status?: string;
    severity?: string;
    sourceType?: string;
    supplierId?: string;
  }) => api.get<Risk[]>("/risks", { params }).then((res) => res.data),
  getById: (id: string) =>
    api.get<Risk>(`/risks/${id}`).then((res) => res.data),
  getStats: () => api.get("/risks/stats/summary").then((res) => res.data),
  getSupplyChainScore: () =>
    api
      .get<SupplyChainRiskScore | null>("/risks/supply-chain-score")
      .then((res) => res.data),
};

export const opportunitiesApi = {
  getAll: (params?: { status?: string; type?: string }) =>
    api
      .get<Opportunity[]>("/opportunities", { params })
      .then((res) => res.data),
  getById: (id: string) =>
    api.get<Opportunity>(`/opportunities/${id}`).then((res) => res.data),
  getStats: () =>
    api.get("/opportunities/stats/summary").then((res) => res.data),
};

export const mitigationPlansApi = {
  getAll: (params?: {
    riskId?: string;
    opportunityId?: string;
    status?: string;
  }) =>
    api
      .get<MitigationPlan[]>("/mitigation-plans", { params })
      .then((res) => res.data),
  getById: (id: string) =>
    api.get<MitigationPlan>(`/mitigation-plans/${id}`).then((res) => res.data),
};

export const oemsApi = {
  register: (name: string, email: string) =>
    api
      .post<{ oem: Oem; token: string }>("/oems/register", { name, email })
      .then((res) => res.data),
  login: (email: string) =>
    api
      .post<{ oem: Oem; token: string }>("/oems/login", { email })
      .then((res) => res.data),
  getProfile: () => api.get<Oem>("/oems/me").then((res) => res.data),
  updateProfile: (data: OemUpdatePayload) =>
    api.put<Oem>("/oems/me", data).then((res) => res.data),
  deleteAccount: () => api.delete("/oems/me"),
};

// Weather agent API (from POC: city risk + shipment weather exposure)
export async function fetchWeatherRisk(
  city: string,
): Promise<WeatherRiskResponse> {
  const url = `${API_BASE_URL}/api/v1/weather/risk?city=${encodeURIComponent(city.trim())}`;
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message = body?.detail ?? `Request failed with ${res.status}`;
    throw new Error(message);
  }
  return res.json();
}

export async function fetchShipmentWeatherExposure(
  input: ShipmentInput,
): Promise<ShipmentWeatherExposureResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/shipment/weather-exposure`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message = body?.detail ?? `Request failed with ${res.status}`;
    throw new Error(message);
  }
  return res.json();
}

export interface SupplierUpdatePayload {
  name?: string;
  location?: string;
  city?: string;
  country?: string;
  region?: string;
  commodities?: string;
}

export interface TrendInsightItem {
  id: string;
  scope: string;
  entity_name: string | null;
  risk_opportunity: string;
  title: string;
  description: string | null;
  predicted_impact: string | null;
  time_horizon: string | null;
  severity: string | null;
  recommended_actions: string[];
  source_articles: string[];
  confidence: number | null;
  oem_name: string | null;
  llm_provider: string | null;
  createdAt: string;
}

export interface TrendInsightRunResult {
  message: string;
  insights_generated: number;
  oem_name: string;
  llm_provider: string;
  insights: TrendInsightItem[];
}

export const trendInsightsApi = {
  runForSupplier: (supplierId: string) =>
    api
      .post<TrendInsightRunResult>(`/trend-insights/run/supplier/${supplierId}`)
      .then((res) => res.data),
  getAll: (params?: {
    scope?: string;
    entity_name?: string;
    severity?: string;
    limit?: number;
  }) =>
    api
      .get<TrendInsightItem[]>("/trend-insights", { params })
      .then((res) => res.data),
};

export const suppliersApi = {
  uploadCsv: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return api
      .post<{ created: number; errors: string[] }>(
        "/suppliers/upload",
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        },
      )
      .then((res) => res.data);
  },
  getAll: () => api.get<Supplier[]>("/suppliers").then((res) => res.data),
  getById: (id: string) =>
    api.get<Supplier | null>(`/suppliers/${id}`).then((res) => res.data),
  update: (id: string, data: SupplierUpdatePayload) =>
    api.put<Supplier>(`/suppliers/${id}`, data).then((res) => res.data),
  delete: (id: string) => api.delete(`/suppliers/${id}`),
};

// Shipping Risk Intelligence
export interface ShippingRiskResult {
  shipping_risk_score: number;
  risk_level: string;
  delay_risk?: { score: number; label: string } | null;
  stagnation_risk?: { score: number; label: string } | null;
  velocity_risk?: { score: number; label: string } | null;
  risk_factors: string[];
  recommended_actions: string[];
  shipment_metadata?: Record<string, unknown> | null;
}

export interface TrackingActivity {
  supplier_name?: string;
  status?: string;
  date?: string;
  activity?: string;
  location?: string;
  sequence?: number;
  planned_arrival?: string;
  actual_arrival?: string;
  departure_time?: string;
  transport_mode?: string;
  [key: string]: unknown;
}

export interface ShipmentMeta {
  awb_code?: string;
  shipment_id?: number;
  current_status?: string;
  origin_city?: string;
  origin_country?: string;
  destination_city?: string;
  destination_country?: string;
  pickup_date?: string;
  etd?: string;
  transit_days_estimated?: number;
  current_checkpoint_sequence?: number;
}

export interface TrackingResponse {
  timeline: TrackingActivity[];
  meta: ShipmentMeta | null;
}

const MOCK_SERVER_URL =
  process.env.NEXT_PUBLIC_MOCK_SERVER_URL || "http://localhost:4000";

export const shippingRiskApi = {
  // Uses the main suppliers endpoint — scoped to the authenticated OEM
  getSuppliers: () => api.get<Supplier[]>("/suppliers").then((res) => res.data),

  // supplierId is a UUID string
  runRisk: (supplierId: string) =>
    api
      .post<ShippingRiskResult>(`/shipping/shipping-risk/${supplierId}`)
      .then((res) => res.data),

  // Fetches tracking via backend proxy (backend calls mock server).
  // Same response shape as before: { items: [...] } from proxy, then we build TrackingResponse.
  getTracking: (supplierId: string): Promise<TrackingResponse> =>
    api
      .get<{ items?: { data: Record<string, unknown> }[] }>(
        `/shipping/tracking/by-supplier/${encodeURIComponent(supplierId)}`,
      )
      .then((res) => res.data)
      .then((payload) => {
        const items = (payload.items ?? []) as {
          data: Record<string, unknown>;
        }[];
        const out: TrackingActivity[] = [];
        let shipmentMeta: ShipmentMeta | null = null;

        for (const item of items) {
          const data = item.data ?? {};
          const td = data.tracking_data as Record<string, unknown> | undefined;
          const routePlan = Array.isArray(td?.route_plan)
            ? (td!.route_plan as Record<string, unknown>[])
            : null;
          const meta = (td?.shipment_meta ?? {}) as Record<string, unknown>;

          // Extract shipment metadata from the first item
          if (!shipmentMeta && Object.keys(meta).length > 0) {
            const origin = meta.origin as Record<string, unknown> | undefined;
            const dest = meta.destination as Record<string, unknown> | undefined;
            shipmentMeta = {
              awb_code: meta.awb_code as string | undefined,
              shipment_id: meta.shipment_id as number | undefined,
              current_status: meta.current_status as string | undefined,
              origin_city: origin?.city as string | undefined,
              origin_country: origin?.country as string | undefined,
              destination_city: dest?.city as string | undefined,
              destination_country: dest?.country as string | undefined,
              pickup_date: meta.pickup_date as string | undefined,
              etd: meta.etd as string | undefined,
              transit_days_estimated: meta.transit_days_estimated as number | undefined,
              current_checkpoint_sequence: meta.current_checkpoint_sequence as number | undefined,
            };
          }

          if (routePlan && routePlan.length > 0) {
            // Sort checkpoints by sequence
            const sorted = [...routePlan].sort(
              (a, b) =>
                ((a.sequence as number) ?? 0) - ((b.sequence as number) ?? 0),
            );

            for (const cp of sorted) {
              const loc = cp.location as
                | Record<string, unknown>
                | undefined;
              const city = loc?.city ?? "";
              const country = loc?.country ?? "";
              const locationStr = [city, country]
                .filter(Boolean)
                .join(", ");

              out.push({
                supplier_name: data.supplier_name as string | undefined,
                status: cp.status as string | undefined,
                activity: cp.transport_mode as string | undefined,
                location: locationStr || undefined,
                date:
                  (cp.actual_arrival as string) ??
                  (cp.planned_arrival as string) ??
                  undefined,
                sequence: cp.sequence as number | undefined,
                planned_arrival: cp.planned_arrival as string | undefined,
                actual_arrival: cp.actual_arrival as string | undefined,
                departure_time: cp.departure_time as string | undefined,
                transport_mode: cp.transport_mode as string | undefined,
              });
            }
          } else {
            // Flat structure — use the record directly, skip nested objects
            const flat: TrackingActivity = {};
            for (const [k, v] of Object.entries(data)) {
              if (typeof v !== "object" || v === null) flat[k] = v;
            }
            out.push(flat);
          }
        }

        return { timeline: out, meta: shipmentMeta };
      }),
};
