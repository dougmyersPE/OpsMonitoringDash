import apiClient from "./client";

export interface MarketRow {
  id: string;
  event_id: string;
  event_name: string | null;
  name: string;
  current_liquidity: number | null;
  min_liquidity_threshold: number | null;
  below_threshold: boolean;
}

export async function fetchMarkets(): Promise<MarketRow[]> {
  const { data } = await apiClient.get<{ markets: MarketRow[] }>("/markets");
  return data.markets;
}
