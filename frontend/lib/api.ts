import axios from "axios";
import type { ShipmentInput, ShipmentWeatherExposureResponse } from "@/lib/types";

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
  status: "idle" | "monitoring" | "analyzing" | "processing" | "completed" | "error";
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

export type SwarmAgentType = 'WEATHER' | 'SHIPPING' | 'NEWS';

export type SwarmRiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

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
  triggerAnalysisV2: () => api.post("/agent/trigger/v2").then((res) => res.data),
  triggerNewsAnalysis: (oemId?: string, supplierId?: string) =>
    api
      .post<{ message: string; oemId: string; risksCreated: number; opportunitiesCreated: number }>(
        "/agent/trigger/news",
        { ...(oemId ? { oemId } : {}), ...(supplierId ? { supplierId } : {}) }
      )
      .then((res) => res.data),
};

export const risksApi = {
  getAll: (params?: { status?: string; severity?: string; sourceType?: string; supplierId?: string }) =>
    api.get<Risk[]>("/risks", { params }).then((res) => res.data),
  getById: (id: string) =>
    api.get<Risk>(`/risks/${id}`).then((res) => res.data),
  getStats: () => api.get("/risks/stats/summary").then((res) => res.data),
  getSupplyChainScore: () =>
    api.get<SupplyChainRiskScore | null>("/risks/supply-chain-score").then((res) => res.data),
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
  getProfile: () =>
    api.get<Oem>("/oems/me").then((res) => res.data),
  updateProfile: (data: OemUpdatePayload) =>
    api.put<Oem>("/oems/me", data).then((res) => res.data),
  deleteAccount: () =>
    api.delete("/oems/me"),
};

// Weather agent API (shipment weather exposure)
export async function fetchShipmentWeatherExposure(
  input: ShipmentInput
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
  getAll: (params?: { scope?: string; entity_name?: string; severity?: string; limit?: number }) =>
    api.get<TrendInsightItem[]>("/trend-insights", { params }).then((res) => res.data),
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

// Shipping Risk Intelligence (from hackathon POC)
export interface ShippingSupplierItem {
  id: number;
  name: string;
  material_name: string;
  location_city: string | null;
  destination_city: string;
  latitude: number | null;
  longitude: number | null;
  shipping_mode: string;
  distance_km: number | null;
  avg_transit_days: number | null;
  historical_delay_percentage: number | null;
  port_used: string | null;
  alternate_route_available: boolean;
  is_critical_supplier: boolean;
  created_at: string;
  updated_at: string;
}

export interface ShippingRiskResult {
  shipping_risk_score: number;
  risk_level: string;
  delay_probability: number;
  delay_risk_score?: number | null;
  stagnation_risk_score?: number | null;
  velocity_risk_score?: number | null;
  risk_factors: string[];
  recommended_actions: string[];
  shipment_metadata?: Record<string, unknown> | null;
}

export interface TrackingActivity {
  date: string;
  status: string;
  activity: string;
  location: string;
}

export const shippingRiskApi = {
  getSuppliers: () =>
    api
      .get<ShippingSupplierItem[]>("/shipping/suppliers/")
      .then((res) => res.data),
  runRisk: (supplierId: number) =>
    api
      .post<ShippingRiskResult>(`/shipping/shipping-risk/${supplierId}`)
      .then((res) => res.data),
  getTracking: (awbCode: string) =>
    api
      .get<{ tracking_data?: { shipment_track_activities?: TrackingActivity[] } }>(
        `/shipping/tracking/${encodeURIComponent(awbCode)}`
      )
      .then((res) => res.data),
};
