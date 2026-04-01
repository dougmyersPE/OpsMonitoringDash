import type { IntervalInfo } from "../../api/usage";

const WORKER_DISPLAY_NAMES: Record<string, string> = {
  poll_prophetx: "ProphetX",
  poll_sports_data: "SportsDataIO",
  poll_odds_api: "Odds API",
  poll_espn: "ESPN",
};

interface ProjectionCardProps {
  projections: {
    monthly_total: number;
    per_worker: Record<string, number>;
  };
  intervals: Record<string, IntervalInfo>;
}

export default function ProjectionCard({ projections, intervals }: ProjectionCardProps) {
  return (
    <div className="rounded-lg bg-zinc-900 border border-zinc-800 p-5 flex flex-col">
      <h3 className="text-sm font-medium text-zinc-400 mb-3">Monthly Projection</h3>

      <p className="text-3xl font-bold text-zinc-100 mb-1">
        {projections.monthly_total.toLocaleString()}
      </p>
      <p className="text-sm text-zinc-500 mb-4">calls / month</p>

      <div className="space-y-2 border-t border-zinc-800 pt-3">
        {Object.entries(projections.per_worker).map(([worker, count]) => {
          const interval = intervals[worker]?.current;
          return (
            <div key={worker} className="flex items-center justify-between text-sm">
              <span className="text-zinc-300">
                {WORKER_DISPLAY_NAMES[worker] ?? worker}
              </span>
              <span className="text-zinc-400">
                {count.toLocaleString()}
                {interval !== undefined && (
                  <span className="text-zinc-600 ml-1">(every {interval}s)</span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
