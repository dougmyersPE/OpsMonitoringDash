import { useEffect, useState } from "react";
import { useSse } from "../hooks/useSse";

export default function SseProvider() {
  const esRef = useSse();
  const [disconnected, setDisconnected] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      const es = esRef.current;
      // EventSource.CLOSED = 2; CONNECTING = 0; OPEN = 1
      if (es && es.readyState === EventSource.CLOSED) {
        setDisconnected(true);
      } else if (es && es.readyState === EventSource.OPEN) {
        setDisconnected(false);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [esRef]);

  if (!disconnected) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-amber-500 text-white text-center py-2 text-sm font-medium">
      Connection lost — reconnecting...
    </div>
  );
}
