import type { OddsQuota } from "../../api/usage";
import OddsApiQuotaCard from "./OddsApiQuotaCard";

interface QuotaSectionProps {
  quota: {
    odds_api: OddsQuota;
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
      </div>
    </section>
  );
}
