import { useQuery } from "@tanstack/react-query";
import { fetchMarkets } from "../api/markets";
import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function MarketsTable() {
  const { data: markets = [], isLoading, error } = useQuery({
    queryKey: ["markets"],
    queryFn: fetchMarkets,
  });

  if (isLoading)
    return (
      <section>
        <SectionHeader title="Markets" count={null} />
        <p className="text-zinc-600 text-sm py-8 text-center">Loading…</p>
      </section>
    );

  if (error)
    return (
      <section>
        <SectionHeader title="Markets" count={null} />
        <p className="text-red-400 text-sm py-8 text-center">Failed to load markets.</p>
      </section>
    );

  return (
    <section>
      <SectionHeader title="Markets" count={`${markets.length}`} />

      <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800 hover:bg-transparent">
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Event</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Market</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Liquidity</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Threshold</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {markets.map((market) => (
              <TableRow
                key={market.id}
                className={cn(
                  "border-zinc-800/60 transition-colors",
                  market.below_threshold
                    ? "bg-red-500/5 border-l-2 border-l-red-500 hover:bg-red-500/8"
                    : "hover:bg-zinc-800/30"
                )}
              >
                <TableCell className="text-zinc-400 text-sm">
                  {market.event_name ?? <span className="text-zinc-700">—</span>}
                </TableCell>
                <TableCell className="text-zinc-200 font-medium text-sm">{market.name}</TableCell>
                <TableCell className="font-mono text-xs text-zinc-300">
                  {market.current_liquidity ?? <span className="text-zinc-700">—</span>}
                </TableCell>
                <TableCell className="font-mono text-xs text-zinc-500">
                  {market.min_liquidity_threshold ?? <span className="text-zinc-600">Global default</span>}
                </TableCell>
                <TableCell>
                  {market.below_threshold ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">
                      <span className="h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
                      Low Liquidity
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shrink-0" />
                      OK
                    </span>
                  )}
                </TableCell>
              </TableRow>
            ))}

            {markets.length === 0 && (
              <TableRow className="hover:bg-transparent border-0">
                <TableCell colSpan={5} className="text-center text-zinc-600 py-12 text-sm">
                  No markets yet
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}

function SectionHeader({ title, count }: { title: string; count: string | null }) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider shrink-0">{title}</h2>
      <div className="flex-1 h-px bg-zinc-800" />
      {count !== null && (
        <span className="text-xs text-zinc-600 shrink-0">{count}</span>
      )}
    </div>
  );
}
