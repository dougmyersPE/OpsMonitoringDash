import type { OddsQuota, SportQuota } from "../../api/usage";
import OddsApiQuotaCard from "./OddsApiQuotaCard";
import SportsApiQuotaCard from "./SportsApiQuotaCard";

interface QuotaSectionProps {
  quota: {
    odds_api: OddsQuota;
    sports_api: Record<string, SportQuota>;
  };
}

export default function QuotaSection({ quota }: QuotaSectionProps) {
  return (
    <section>
      <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-3">
        Provider Quotas
      </h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <OddsApiQuotaCard quota={quota.odds_api} />
        <SportsApiQuotaCard quota={quota.sports_api} />
      </div>
    </section>
  );
}
