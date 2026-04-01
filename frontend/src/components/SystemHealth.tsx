import { useQuery } from "@tanstack/react-query";
import apiClient from "../api/client";
import { cn } from "@/lib/utils";

interface WorkerHealth {
  poll_prophetx: boolean;
  poll_sports_data: boolean;
  poll_odds_api: boolean;
  poll_espn: boolean;
}

async function fetchWorkerHealth(): Promise<WorkerHealth> {
  const { data } = await apiClient.get<WorkerHealth>("/health/workers");
  return data;
}

const WORKERS: { key: keyof WorkerHealth; label: string }[] = [
  { key: "poll_prophetx",    label: "ProphetX" },
  { key: "poll_sports_data", label: "SDIO" },
  { key: "poll_odds_api",    label: "Odds API" },
  { key: "poll_espn",        label: "ESPN" },
];

export default function SystemHealth() {
  const { data } = useQuery({
    queryKey: ["worker-health"],
    queryFn: fetchWorkerHealth,
    refetchInterval: 30_000,
    retry: false,
  });

  if (!data) {
    return (
      <span className="text-zinc-600 text-xs font-medium">Workers: checking…</span>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      {WORKERS.map(({ key, label }) => {
        const active = data[key];
        return (
          <span
            key={key}
            title={`${label}: ${active ? "healthy" : "offline"}`}
            className={cn(
              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border",
              active
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                : "bg-red-500/10 text-red-400 border-red-500/20"
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full shrink-0",
                active ? "bg-emerald-400 animate-pulse" : "bg-red-500"
              )}
            />
            {label}
          </span>
        );
      })}
    </div>
  );
}
