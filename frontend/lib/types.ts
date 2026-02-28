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

export interface DayWeatherSnapshot {
  date: string;
  day_number: number;
  location_name: string;
  estimated_location: string;
  condition: string;
  condition_code?: number;
  temp_c: number;
  feelslike_c?: number | null;
  min_temp_c?: number | null;
  max_temp_c?: number | null;
  wind_kph: number;
  gust_kph?: number | null;
  precip_mm: number;
  snow_cm?: number;
  vis_km: number;
  humidity: number;
  pressure_mb?: number | null;
  uv?: number | null;
  is_historical: boolean;
  is_estimated?: boolean;
}

export interface DayRiskSnapshot {
  date: string;
  day_number: number;
  location_name: string;
  weather: DayWeatherSnapshot;
  risk: RiskSummary;
  risk_summary_text: string;
}

/** New graph-based response shapes */

export interface WeatherRisk {
  title: string;
  description: string;
  severity: "low" | "moderate" | "medium" | "high" | "critical";
  affectedRegion: string | null;
  affectedSupplier: string | null;
  estimatedImpact: string | null;
  estimatedCost: number | null;
  sourceType: string;
  sourceData: {
    weatherExposure?: {
      weather_exposure_score?: number;
      peak_risk_score?: number;
      peak_risk_day?: number | null;
      peak_risk_date?: string | null;
      high_risk_day_count?: number;
      estimated_day_count?: number;
      dominant_risk_factor?: string;
      dominant_risk_factor_score?: number;
      route?: string;
      day_number?: number;
      date?: string;
      location?: string;
      is_estimated?: boolean;
      weather_snapshot?: Record<string, unknown>;
    };
    risk_factors_max?: Record<string, number>;
  };
}

export interface WeatherOpportunity {
  title: string;
  description: string;
  type: string;
  affectedRegion: string | null;
  potentialBenefit: string | null;
  estimatedValue: number | null;
  sourceType: string;
  sourceData: Record<string, unknown> | null;
}

export interface WeatherGraphResponse {
  risks: WeatherRisk[];
  opportunities: WeatherOpportunity[];
  daily_timeline: DayRiskSnapshot[];
}
