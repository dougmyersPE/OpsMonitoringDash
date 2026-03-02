import type { OddsQuota } from "../../api/usage";

function getBarColor(usagePercent: number): string {
  if (usagePercent > 80) return "bg-red-500";
  if (usagePercent > 50) return "bg-amber-500";
  return "bg-emerald-500";
}

export default function OddsApiQuotaCard({ quota }: { quota: OddsQuota }) {
  const hasData = quota.remaining !== null || quota.used !== null;

  let usagePercent = 0;
  if (hasData && quota.used !== null) {
    const total =
      quota.limit !== null
        ? quota.limit
        : (quota.used ?? 0) + (quota.remaining ?? 0);
    usagePercent = total > 0 ? ((quota.used ?? 0) / total) * 100 : 0;
  }

  return (
    <div className="rounded-lg bg-zinc-900 border border-zinc-800 p-5">
      <h3 className="text-sm font-medium text-zinc-400 mb-3">Odds API</h3>

      {!hasData ? (
        <p className="text-2xl font-semibold text-zinc-100">&mdash;</p>
      ) : (
        <>
          {/* Progress bar */}
          <div className="h-2.5 rounded-full bg-zinc-800 mb-3">
            <div
              className={`h-full rounded-full transition-all ${getBarColor(usagePercent)}`}
              style={{ width: `${Math.min(usagePercent, 100)}%` }}
            />
          </div>

          {/* Numbers */}
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-zinc-100">
              {quota.used !== null ? quota.used.toLocaleString() : "\u2014"}
            </span>
            <span className="text-sm text-zinc-400">used</span>
            <span className="text-zinc-600 mx-1">/</span>
            <span className="text-2xl font-semibold text-zinc-100">
              {quota.remaining !== null
                ? quota.remaining.toLocaleString()
                : "\u2014"}
            </span>
            <span className="text-sm text-zinc-400">remaining</span>
          </div>

          {quota.limit !== null && (
            <p className="text-xs text-zinc-500 mt-1">
              of {quota.limit.toLocaleString()} total
            </p>
          )}
        </>
      )}
    </div>
  );
}
