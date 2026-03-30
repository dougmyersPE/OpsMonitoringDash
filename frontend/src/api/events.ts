import apiClient from "./client";

export interface EventRow {
  id: string;
  prophetx_event_id: string;
  name: string;
  sport: string;
  scheduled_start: string | null;
  prophetx_status: string | null;
  odds_api_status: string | null;
  sports_api_status: string | null;
  sdio_status: string | null;
  espn_status: string | null;
  oddsblaze_status: string | null;
  status_match: boolean;
  is_flagged: boolean;
  is_critical: boolean;
  last_prophetx_poll: string | null;
  last_real_world_poll: string | null;
}

export async function fetchEvents(): Promise<EventRow[]> {
  const { data } = await apiClient.get<{ events: EventRow[] }>("/events");
  return data.events;
}

export async function syncEventStatus(eventId: string): Promise<void> {
  await apiClient.post(`/events/${eventId}/sync-status`);
}

export async function refreshAllEvents(): Promise<void> {
  await apiClient.post("/events/refresh-all");
}
