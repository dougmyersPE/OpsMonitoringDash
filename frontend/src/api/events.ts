import apiClient from "./client";

export interface EventRow {
  id: string;
  name: string;
  sport: string;
  prophetx_status: string | null;
  real_world_status: string | null;
  status_match: boolean;
  is_flagged: boolean;
  last_prophetx_poll: string | null;
}

export async function fetchEvents(): Promise<EventRow[]> {
  const { data } = await apiClient.get<{ events: EventRow[] }>("/events");
  return data.events;
}

export async function syncEventStatus(eventId: string): Promise<void> {
  await apiClient.post(`/events/${eventId}/sync-status`);
}
