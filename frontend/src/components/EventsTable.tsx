import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { fetchEvents } from "../api/events";
import { useAuthStore } from "../stores/auth";
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
import { Button } from "@/components/ui/button";
import { syncEventStatus } from "../api/events";

function ToggleButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Button
      size="sm"
      variant={active ? "default" : "outline"}
      onClick={onClick}
      className="h-7 px-2.5 text-xs"
    >
      {children}
    </Button>
  );
}

export default function EventsTable() {
  const queryClient = useQueryClient();
  const role = useAuthStore((s) => s.role);
  const canSync = role === "admin" || role === "operator";

  const { data: events = [], isLoading, error } = useQuery({
    queryKey: ["events"],
    queryFn: fetchEvents,
  });

  const syncMutation = useMutation({
    mutationFn: syncEventStatus,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["events"] }),
  });

  // --- filter state ---
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());
  const [sportFilter, setSportFilter] = useState<Set<string>>(new Set());
  const [mismatchOnly, setMismatchOnly] = useState(false);
  const [flaggedOnly, setFlaggedOnly] = useState(false);

  const availableStatuses = useMemo(
    () =>
      [...new Set(events.map((e) => e.prophetx_status).filter(Boolean) as string[])].sort(),
    [events]
  );

  const availableSports = useMemo(
    () => [...new Set(events.map((e) => e.sport).filter(Boolean))].sort(),
    [events]
  );

  function toggleSet(set: Set<string>, value: string): Set<string> {
    const next = new Set(set);
    next.has(value) ? next.delete(value) : next.add(value);
    return next;
  }

  const filtered = useMemo(() => {
    return events.filter((e) => {
      if (statusFilter.size > 0 && !statusFilter.has(e.prophetx_status ?? "")) return false;
      if (sportFilter.size > 0 && !sportFilter.has(e.sport)) return false;
      if (mismatchOnly && e.status_match !== false) return false;
      if (flaggedOnly && !e.is_flagged) return false;
      return true;
    });
  }, [events, statusFilter, sportFilter, mismatchOnly, flaggedOnly]);

  if (isLoading) return <p className="text-slate-500">Loading events...</p>;
  if (error) return <p className="text-red-600">Failed to load events.</p>;

  const hasActiveFilters =
    statusFilter.size > 0 || sportFilter.size > 0 || mismatchOnly || flaggedOnly;

  return (
    <section>
      <h2 className="text-lg font-semibold text-slate-800 mb-3">Events</h2>

      {/* Filters */}
      <div className="mb-3 space-y-2">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {/* PX Status */}
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-slate-500 shrink-0">Status</span>
            <div className="flex gap-1">
              {availableStatuses.map((s) => (
                <ToggleButton
                  key={s}
                  active={statusFilter.has(s)}
                  onClick={() => setStatusFilter(toggleSet(statusFilter, s))}
                >
                  {s}
                </ToggleButton>
              ))}
            </div>
          </div>

          {/* Sport */}
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-slate-500 shrink-0">Sport</span>
            <div className="flex flex-wrap gap-1">
              {availableSports.map((s) => (
                <ToggleButton
                  key={s}
                  active={sportFilter.has(s)}
                  onClick={() => setSportFilter(toggleSet(sportFilter, s))}
                >
                  {s}
                </ToggleButton>
              ))}
            </div>
          </div>

          {/* Mismatch / Flagged */}
          <div className="flex items-center gap-1">
            <ToggleButton active={mismatchOnly} onClick={() => setMismatchOnly((v) => !v)}>
              Mismatches
            </ToggleButton>
            <ToggleButton active={flaggedOnly} onClick={() => setFlaggedOnly((v) => !v)}>
              Flagged
            </ToggleButton>
          </div>

          {/* Clear */}
          {hasActiveFilters && (
            <button
              className="text-xs text-slate-400 hover:text-slate-600 underline"
              onClick={() => {
                setStatusFilter(new Set());
                setSportFilter(new Set());
                setMismatchOnly(false);
                setFlaggedOnly(false);
              }}
            >
              Clear filters
            </button>
          )}
        </div>

        {hasActiveFilters && (
          <p className="text-xs text-slate-500">
            Showing {filtered.length} of {events.length} events
          </p>
        )}
      </div>

      <div className="rounded-lg border bg-white overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>PX Event ID</TableHead>
              <TableHead>Event</TableHead>
              <TableHead>Sport</TableHead>
              <TableHead>ProphetX Status</TableHead>
              <TableHead>Odds API</TableHead>
              <TableHead>Sports API</TableHead>
              <TableHead>SDIO</TableHead>
              <TableHead>ESPN</TableHead>
              <TableHead>Flagged</TableHead>
              <TableHead>Last Checked</TableHead>
              {canSync && <TableHead>Action</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((event) => (
              <TableRow
                key={event.id}
                className={cn(
                  !event.status_match && "bg-red-50 border-l-4 border-l-red-500"
                )}
              >
                <TableCell className="font-mono text-xs text-slate-500">{event.prophetx_event_id}</TableCell>
                <TableCell className="font-medium">{event.name}</TableCell>
                <TableCell>{event.sport}</TableCell>
                <TableCell>
                  <Badge variant={event.status_match ? "secondary" : "destructive"}>
                    {event.prophetx_status ?? "—"}
                  </Badge>
                </TableCell>
                <TableCell>{event.odds_api_status ?? "—"}</TableCell>
                <TableCell>{event.sports_api_status ?? "—"}</TableCell>
                <TableCell>{event.sdio_status ?? "—"}</TableCell>
                <TableCell>{event.espn_status ?? "—"}</TableCell>
                <TableCell>{event.is_flagged ? "Yes" : "—"}</TableCell>
                <TableCell className="text-slate-500 text-xs">
                  {event.last_prophetx_poll
                    ? format(new Date(event.last_prophetx_poll), "HH:mm:ss")
                    : "—"}
                </TableCell>
                {canSync && (
                  <TableCell>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => syncMutation.mutate(event.id)}
                      disabled={syncMutation.isPending}
                    >
                      Sync
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={canSync ? 11 : 10} className="text-center text-slate-400 py-8">
                  {hasActiveFilters ? "No events match the current filters" : "No events yet"}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}
