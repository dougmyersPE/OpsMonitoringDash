import { useQuery } from "@tanstack/react-query";
import apiClient from "../api/client";

interface WorkerHealth {
  poll_prophetx: boolean;
  poll_sports_data: boolean;
}

async function fetchWorkerHealth(): Promise<WorkerHealth> {
  const { data } = await apiClient.get<WorkerHealth>("/health/workers");
  return data;
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full mr-1 ${active ? "bg-green-500" : "bg-red-500"}`}
    />
  );
}

export default function SystemHealth() {
  const { data } = useQuery({
    queryKey: ["worker-health"],
    queryFn: fetchWorkerHealth,
    refetchInterval: 30_000,
    retry: false,
  });

  if (!data) return <span className="text-slate-400 text-xs">Workers: checking...</span>;

  return (
    <div className="flex items-center gap-4 text-xs text-slate-600">
      <span>
        <StatusDot active={data.poll_prophetx} />
        ProphetX poller
      </span>
      <span>
        <StatusDot active={data.poll_sports_data} />
        SDIO poller
      </span>
    </div>
  );
}
