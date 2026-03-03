import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

export function useSse() {
  const queryClient = useQueryClient();
  const esRef = useRef<EventSource | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const url = `/api/v1/stream`;
    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("update", () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["events"] });
        queryClient.invalidateQueries({ queryKey: ["markets"] });
        queryClient.invalidateQueries({ queryKey: ["notifications"] });
      }, 300);
    });

    // onerror: browser auto-reconnects per SSE spec; SseProvider shows banner
    es.onerror = () => {
      // Silent — reconnect state tracked in SseProvider via es.readyState
    };

    return () => {
      es.close();
      esRef.current = null;
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [queryClient]);

  return esRef;
}
