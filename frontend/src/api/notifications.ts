import apiClient from "./client";

export interface Notification {
  id: string;
  type: string;
  entity_type: string | null;
  entity_id: string | null;
  message: string;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: Notification[];
  unread_count: number;
}

export async function fetchNotifications(): Promise<NotificationListResponse> {
  const { data } = await apiClient.get<NotificationListResponse>("/notifications");
  return data;
}

export async function markRead(notificationId: string): Promise<void> {
  await apiClient.patch(`/notifications/${notificationId}/read`);
}

export async function markAllRead(): Promise<void> {
  await apiClient.patch("/notifications/mark-all-read");
}

export async function fetchAlertsEnabled(): Promise<{ enabled: boolean }> {
  const { data } = await apiClient.get<{ enabled: boolean }>("/notifications/alerts-enabled");
  return data;
}

export async function toggleAlertsEnabled(): Promise<{ enabled: boolean }> {
  const { data } = await apiClient.patch<{ enabled: boolean }>("/notifications/alerts-enabled");
  return data;
}
