/** Types for Weather Risk and Shipment Weather Exposure API */

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

export interface LocationInfo {
  name: string;
  region?: string | null;
  country: string;
  lat: number;
  lon: number;
  tz_id?: string | null;
  localtime?: string | null;
}

export interface WeatherCondition {
  text: string;
  temp_c: number;
  feelslike_c: number;
  wind_kph: number;
  wind_degree?: number | null;
  pressure_mb: number;
  precip_mm: number;
  humidity: number;
  cloud: number;
  vis_km: number;
  uv?: number | null;
  gust_kph?: number | null;
  condition_code?: number | null;
}

export interface WeatherRiskResponse {
  location: LocationInfo;
  weather: WeatherCondition;
  risk: RiskSummary;
  agent_summary?: string | null;
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
