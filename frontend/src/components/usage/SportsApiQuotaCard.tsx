import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { SportQuota } from "../../api/usage";

const SPORT_DISPLAY_NAMES: Record<string, string> = {
  basketball: "Basketball",
  hockey: "Hockey",
  baseball: "Baseball",
  "american-football": "American Football",
  soccer: "Soccer",
};

interface SportsApiQuotaCardProps {
  quota: Record<string, SportQuota>;
}

export default function SportsApiQuotaCard({ quota }: SportsApiQuotaCardProps) {
  const [expanded, setExpanded] = useState(false);

  // Aggregate totals across all sports
  let totalRemaining = 0;
  let totalLimit = 0;
  let hasAnyData = false;

  for (const sport of Object.values(quota)) {
    if (sport.remaining !== null) {
      totalRemaining += sport.remaining;
      hasAnyData = true;
    }
    if (sport.limit !== null) {
      totalLimit += sport.limit;
    }
  }

  const usagePercent =
    hasAnyData && totalLimit > 0
      ? ((totalLimit - totalRemaining) / totalLimit) * 100
      : 0;

  function getBarColor(pct: number): string {
    if (pct > 80) return "bg-red-500";
    if (pct > 50) return "bg-amber-500";
    return "bg-emerald-500";
  }

  return (
    <div className="rounded-lg bg-zinc-900 border border-zinc-800 p-5">
      <button
        type="button"
        className="flex items-center justify-between w-full text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <h3 className="text-sm font-medium text-zinc-400">Sports API</h3>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-zinc-500" />
        ) : (
          <ChevronDown className="h-4 w-4 text-zinc-500" />
        )}
      </button>

      {!hasAnyData ? (
        <p className="text-2xl font-semibold text-zinc-100 mt-3">&mdash;</p>
      ) : (
        <div className="mt-3">
          {/* Aggregate progress bar */}
          <div className="h-2.5 rounded-full bg-zinc-800 mb-3">
            <div
              className={`h-full rounded-full transition-all ${getBarColor(usagePercent)}`}
              style={{ width: `${Math.min(usagePercent, 100)}%` }}
            />
          </div>

          {/* Aggregate numbers */}
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-zinc-100">
              {totalRemaining.toLocaleString()}
            </span>
            <span className="text-sm text-zinc-400">remaining</span>
            {totalLimit > 0 && (
              <>
                <span className="text-zinc-600 mx-1">/</span>
                <span className="text-2xl font-semibold text-zinc-100">
                  {totalLimit.toLocaleString()}
                </span>
                <span className="text-sm text-zinc-400">limit</span>
              </>
            )}
          </div>

          {/* Expanded per-sport breakdown */}
          {expanded && (
            <div className="mt-4 space-y-2 border-t border-zinc-800 pt-3">
              {Object.entries(quota).map(([sport, sportQuota]) => (
                <div key={sport} className="flex items-center justify-between text-sm">
                  <span className="text-zinc-300">
                    {SPORT_DISPLAY_NAMES[sport] ?? sport}
                  </span>
                  <span className="text-zinc-400">
                    {sportQuota.remaining !== null
                      ? `${sportQuota.remaining.toLocaleString()} remaining`
                      : "\u2014"}
                    {sportQuota.limit !== null && (
                      <span className="text-zinc-600">
                        {" "}/ {sportQuota.limit.toLocaleString()}
                      </span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
