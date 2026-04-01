import apiClient from "./client";

// TypeScript interfaces for the usage endpoint response

export interface OddsQuota {
  remaining: number | null;
  used: number | null;
  limit: number | null;
  updated_at: string | null;
}

export interface IntervalInfo {
  current: number;
  minimum: number;
}

export interface HistoryEntry {
  date: string;
  [worker: string]: string | number;
}

export interface UsageData {
  date: string;
  calls_today: Record<string, number>;
  history: HistoryEntry[];
  quota: {
    odds_api: OddsQuota;
  };
  intervals: Record<string, IntervalInfo>;
  projections: {
    monthly_total: number;
    per_worker: Record<string, number>;
  };
  sources_enabled: Record<string, boolean>;
}

export async function fetchUsageData(): Promise<UsageData> {
  const { data } = await apiClient.get<UsageData>("/usage");
  return data;
}

export async function updateInterval(
  key: string,
  value: string
): Promise<void> {
  await apiClient.patch(`/config/${key}`, { value });
}
