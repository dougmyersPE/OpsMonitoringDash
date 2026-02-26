import { useEffect, useRef, useState } from "react";
import { useSse } from "../hooks/useSse";

// Grace period in ms before the reconnect banner appears.
// Browser SSE auto-reconnect delay is typically 3-5 seconds (spec default).
// 15 seconds covers brief blips without false-positive banners.
const DISCONNECT_GRACE_MS = 15_000;

export default function SseProvider() {
  const esRef = useSse();
  const [disconnected, setDisconnected] = useState(false);

  // Track the timestamp of the last OPEN state observation.
  // Initialized to Date.now() so the banner doesn't fire on first mount
  // before the connection has had a chance to open.
  const lastOpenRef = useRef<number>(Date.now());

  useEffect(() => {
    const interval = setInterval(() => {
      const es = esRef.current;
      if (!es) return;

      if (es.readyState === EventSource.OPEN) {
        // Connection is healthy — reset the last-seen-open timestamp and clear banner
        lastOpenRef.current = Date.now();
        setDisconnected(false);
      } else {
        // readyState is CONNECTING (0) or CLOSED (2)
        // Show banner only after the grace period has elapsed since last OPEN
        const elapsed = Date.now() - lastOpenRef.current;
        if (elapsed >= DISCONNECT_GRACE_MS) {
          setDisconnected(true);
        }
      }
    }, 2_000); // Check every 2 seconds for faster recovery detection

    return () => clearInterval(interval);
  }, [esRef]);

  if (!disconnected) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-amber-500 text-white text-center py-2 text-sm font-medium">
      Connection lost — reconnecting...
    </div>
  );
}
