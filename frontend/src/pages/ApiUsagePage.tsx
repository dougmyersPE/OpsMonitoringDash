import { useQuery } from "@tanstack/react-query";
import Layout from "../components/Layout";
import { fetchUsageData } from "../api/usage";
import QuotaSection from "../components/usage/QuotaSection";
import CallVolumeSection from "../components/usage/CallVolumeSection";
import IntervalSection from "../components/usage/IntervalSection";
import { useAuthStore } from "../stores/auth";

export default function ApiUsagePage() {
  const role = useAuthStore((s) => s.role);
  const { data, isLoading, error } = useQuery({
    queryKey: ["usage"],
    queryFn: fetchUsageData,
    refetchInterval: 30_000,
  });

  return (
    <Layout>
      <div className="space-y-6">
        <h1 className="text-xl font-semibold text-zinc-100">API Usage</h1>

        {isLoading && (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-48 rounded-lg bg-zinc-900 animate-pulse" />
            ))}
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-red-950/50 border border-red-800 p-4 text-red-300 text-sm">
            Failed to load usage data. Retrying...
          </div>
        )}

        {data && (
          <>
            <QuotaSection quota={data.quota} />
            <CallVolumeSection
              history={data.history}
              projections={data.projections}
              intervals={data.intervals}
            />
            {role === "admin" && (
              <IntervalSection intervals={data.intervals} />
            )}
          </>
        )}
      </div>
    </Layout>
  );
}
