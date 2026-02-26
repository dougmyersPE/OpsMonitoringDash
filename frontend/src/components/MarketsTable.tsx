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
import { Badge } from "@/components/ui/badge";

export default function MarketsTable() {
  const { data: markets = [], isLoading, error } = useQuery({
    queryKey: ["markets"],
    queryFn: fetchMarkets,
  });

  if (isLoading) return <p className="text-slate-500">Loading markets...</p>;
  if (error) return <p className="text-red-600">Failed to load markets.</p>;

  return (
    <section>
      <h2 className="text-lg font-semibold text-slate-800 mb-3">Markets</h2>
      <div className="rounded-lg border bg-white overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Market</TableHead>
              <TableHead>Current Liquidity</TableHead>
              <TableHead>Threshold</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {markets.map((market) => (
              <TableRow
                key={market.id}
                className={cn(
                  market.below_threshold && "bg-red-50 border-l-4 border-l-red-500"
                )}
              >
                <TableCell className="font-medium">{market.name}</TableCell>
                <TableCell>{market.current_liquidity ?? "—"}</TableCell>
                <TableCell>{market.liquidity_threshold ?? "Global default"}</TableCell>
                <TableCell>
                  {market.below_threshold ? (
                    <Badge variant="destructive">Low Liquidity</Badge>
                  ) : (
                    <Badge variant="secondary">OK</Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {markets.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-slate-400 py-8">
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
