import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "../stores/auth";

export function useSse() {
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.token);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!token) return;

    const url = `/api/v1/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("update", () => {
      queryClient.invalidateQueries({ queryKey: ["events"] });
      queryClient.invalidateQueries({ queryKey: ["markets"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    });

    // onerror: browser auto-reconnects per SSE spec; SseProvider shows banner
    es.onerror = () => {
      // Silent — reconnect state tracked in SseProvider via es.readyState
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [token, queryClient]);

  return esRef;
}
