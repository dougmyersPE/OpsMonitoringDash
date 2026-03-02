import type { HistoryEntry, IntervalInfo } from "../../api/usage";
import CallVolumeChart from "./CallVolumeChart";
import ProjectionCard from "./ProjectionCard";

interface CallVolumeSectionProps {
  history: HistoryEntry[];
  projections: {
    monthly_total: number;
    per_worker: Record<string, number>;
  };
  intervals: Record<string, IntervalInfo>;
}

export default function CallVolumeSection({
  history,
  projections,
  intervals,
}: CallVolumeSectionProps) {
  // Check if there is any data to chart
  const hasChartData =
    history.length > 0 &&
    history.some((entry) =>
      Object.entries(entry).some(
        ([key, val]) => key !== "date" && typeof val === "number" && val > 0
      )
    );

  return (
    <section>
      <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-3">
        Call Volume
      </h2>

      <div className="flex flex-col lg:flex-row gap-4">
        {/* Chart area */}
        <div className="flex-[7] rounded-lg bg-zinc-900 border border-zinc-800 p-5">
          {hasChartData ? (
            <CallVolumeChart data={history} />
          ) : (
            <div className="flex items-center justify-center h-[320px] text-zinc-500 text-sm">
              Collecting data &mdash; chart populates as polls run
            </div>
          )}
        </div>

        {/* Projection sidebar */}
        <div className="flex-[3]">
          <ProjectionCard projections={projections} intervals={intervals} />
        </div>
      </div>
    </section>
  );
}
