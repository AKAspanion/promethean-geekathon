/** Types for Shipment Weather Exposure API */

export type RiskLevel = "low" | "moderate" | "high" | "critical";

export interface RiskFactor {
  factor: string;
  level: RiskLevel;
  score: number;
  summary: string;
  details?: string | null;
  mitigation?: string | null;
}

export interface RiskSummary {
  overall_level: RiskLevel;
  overall_score: number;
  factors: RiskFactor[];
  primary_concerns: string[];
  suggested_actions: string[];
}

export interface ShipmentInput {
  supplier_city: string;
  oem_city: string;
  shipment_start_date: string;
  transit_days: number;
}

export interface DayWeatherSnapshot {
  date: string;
  day_number: number;
  location_name: string;
  estimated_location: string;
  condition: string;
  temp_c: number;
  min_temp_c?: number | null;
  max_temp_c?: number | null;
  wind_kph: number;
  precip_mm: number;
  vis_km: number;
  humidity: number;
  is_historical: boolean;
}

export interface DayRiskSnapshot {
  date: string;
  day_number: number;
  location_name: string;
  weather: DayWeatherSnapshot;
  risk: RiskSummary;
  risk_summary_text: string;
}

export interface ShipmentWeatherExposureResponse {
  supplier_city: string;
  oem_city: string;
  shipment_start_date: string;
  transit_days: number;
  days: DayRiskSnapshot[];
  overall_exposure_level: RiskLevel;
  overall_exposure_score: number;
  risk_analysis_payload: Record<string, unknown>;
  agent_summary?: string | null;
}
