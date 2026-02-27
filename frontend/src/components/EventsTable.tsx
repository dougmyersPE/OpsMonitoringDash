import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { GripVertical } from "lucide-react";
import { fetchEvents, type EventRow } from "../api/events";
import { useAuthStore } from "../stores/auth";
import { cn } from "@/lib/utils";
import { normalizeStatus } from "@/lib/statusDisplay";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { syncEventStatus } from "../api/events";

/* ─── Status pill components ─── */

function PxStatusPill({
  status,
  isMismatch,
}: {
  status: string | null | undefined;
  isMismatch: boolean;
}) {
  const display = normalizeStatus(status);

  if (isMismatch) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">
        <span className="h-1.5 w-1.5 rounded-full bg-red-400 shrink-0" />
        {display}
      </span>
    );
  }

  if (display === "Live") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
        Live
      </span>
    );
  }

  if (display === "Ended") {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-zinc-800/80 text-zinc-500 border border-zinc-700/50">
        Ended
      </span>
    );
  }

  if (display === "—") {
    return <span className="text-zinc-700">—</span>;
  }

  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-zinc-800/80 text-zinc-400 border border-zinc-700/50">
      {display}
    </span>
  );
}

function SourceStatus({ status }: { status: string | null | undefined }) {
  if (!status) {
    return <span className="text-zinc-600 text-xs italic select-none">Not Listed</span>;
  }
  const display = normalizeStatus(status);
  if (display === "Live")
    return <span className="text-emerald-400 text-xs font-medium">Live</span>;
  if (display === "Ended")
    return <span className="text-zinc-400 text-xs">Ended</span>;
  if (display === "Not Started")
    return <span className="text-sky-400 text-xs">Not Started</span>;
  // Flag-worthy statuses (Canceled, Postponed, etc.) — show raw value in amber
  return <span className="text-amber-400 text-xs font-medium">{display}</span>;
}

function FlaggedBadge({ flagged }: { flagged: boolean }) {
  if (!flagged) return <span className="text-zinc-700 select-none">—</span>;
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
      ⚑ Flag
    </span>
  );
}

/* ─── Toggle filter button ─── */

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
    <button
      onClick={onClick}
      className={cn(
        "h-7 px-3 rounded-lg text-xs font-medium border transition-colors",
        active
          ? "bg-indigo-600/20 text-indigo-300 border-indigo-500/40"
          : "bg-zinc-900 text-zinc-500 border-zinc-700 hover:text-zinc-300 hover:border-zinc-600"
      )}
    >
      {children}
    </button>
  );
}

/* ─── Status group order chip ─── */

const STATUS_CHIP_STYLES: Record<string, string> = {
  "Live":        "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
  "Not Started": "bg-zinc-800/60 text-zinc-400 border-zinc-700",
  "Ended":       "bg-zinc-900 text-zinc-600 border-zinc-700/50",
};

const STATUS_DOT_STYLES: Record<string, string> = {
  "Live":        "bg-emerald-400 animate-pulse",
  "Not Started": "bg-zinc-500",
  "Ended":       "bg-zinc-700",
};

const ALL_STATUS_GROUPS = ["Live", "Not Started", "Ended"];

function GroupOrderControl({
  order,
  onChange,
}: {
  order: string[];
  onChange: (next: string[]) => void;
}) {
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);

  function onDragStart(idx: number) {
    setDragFrom(idx);
  }

  function onDragOver(e: React.DragEvent, idx: number) {
    e.preventDefault();
    setDragOver(idx);
  }

  function onDrop(idx: number) {
    if (dragFrom !== null && dragFrom !== idx) {
      const next = [...order];
      const [item] = next.splice(dragFrom, 1);
      next.splice(idx, 0, item);
      onChange(next);
    }
    setDragFrom(null);
    setDragOver(null);
  }

  function onDragEnd() {
    setDragFrom(null);
    setDragOver(null);
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider mr-0.5">
        Group order
      </span>
      {order.map((status, idx) => (
        <div
          key={status}
          draggable
          onDragStart={() => onDragStart(idx)}
          onDragOver={(e) => onDragOver(e, idx)}
          onDrop={() => onDrop(idx)}
          onDragEnd={onDragEnd}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border cursor-grab active:cursor-grabbing select-none transition-all",
            STATUS_CHIP_STYLES[status] ?? "bg-zinc-800 text-zinc-400 border-zinc-700",
            dragFrom === idx && "opacity-30",
            dragOver === idx && dragFrom !== idx && "ring-1 ring-inset ring-indigo-400/50"
          )}
        >
          <GripVertical className="h-3 w-3 opacity-40 shrink-0" />
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full shrink-0",
              STATUS_DOT_STYLES[status] ?? "bg-zinc-600"
            )}
          />
          <span className="text-[11px]">{status}</span>
          <span className="text-[9px] opacity-40 ml-0.5">{idx + 1}</span>
        </div>
      ))}
    </div>
  );
}

/* ─── Sort logic ─── */

function sortEvents(events: EventRow[], statusOrder: string[]): EventRow[] {
  const now = Date.now();

  // Bucket by normalized status
  const buckets = new Map<string, EventRow[]>();
  const other: EventRow[] = [];

  for (const ev of events) {
    const display = normalizeStatus(ev.prophetx_status);
    if (statusOrder.includes(display)) {
      if (!buckets.has(display)) buckets.set(display, []);
      buckets.get(display)!.push(ev);
    } else {
      other.push(ev);
    }
  }

  // Within each group: sort by closest scheduled_start to now
  const byClosestStart = (a: EventRow, b: EventRow) => {
    const aMs = a.scheduled_start
      ? Math.abs(new Date(a.scheduled_start).getTime() - now)
      : Number.MAX_SAFE_INTEGER;
    const bMs = b.scheduled_start
      ? Math.abs(new Date(b.scheduled_start).getTime() - now)
      : Number.MAX_SAFE_INTEGER;
    return aMs - bMs;
  };

  const result: EventRow[] = [];
  for (const status of statusOrder) {
    result.push(...(buckets.get(status) ?? []).sort(byClosestStart));
  }
  result.push(...other.sort(byClosestStart));

  return result;
}

/* ─── Main component ─── */

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

  const [statusFilter, setStatusFilter] = useState("");
  const [sportFilter, setSportFilter] = useState("");
  const [mismatchOnly, setMismatchOnly] = useState(false);
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [statusOrder, setStatusOrder] = useState<string[]>(ALL_STATUS_GROUPS);

  const availableStatuses = useMemo(
    () =>
      [...new Set(events.map((e) => e.prophetx_status).filter(Boolean) as string[])].sort(),
    [events]
  );

  const availableSports = useMemo(
    () => [...new Set(events.map((e) => e.sport).filter(Boolean))].sort(),
    [events]
  );

  const filtered = useMemo(() => {
    return events.filter((e) => {
      if (statusFilter && e.prophetx_status !== statusFilter) return false;
      if (sportFilter && e.sport !== sportFilter) return false;
      if (mismatchOnly && e.status_match !== false) return false;
      if (flaggedOnly && !e.is_flagged) return false;
      return true;
    });
  }, [events, statusFilter, sportFilter, mismatchOnly, flaggedOnly]);

  const sorted = useMemo(
    () => sortEvents(filtered, statusOrder),
    [filtered, statusOrder]
  );

  const hasActiveFilters = !!statusFilter || !!sportFilter || mismatchOnly || flaggedOnly;

  const selectClass =
    "h-7 rounded-lg border border-zinc-700 bg-zinc-900 px-3 text-xs text-zinc-300 focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/20 cursor-pointer appearance-none";

  if (isLoading)
    return (
      <section>
        <SectionHeader title="Events" count={null} />
        <p className="text-zinc-600 text-sm py-8 text-center">Loading…</p>
      </section>
    );

  if (error)
    return (
      <section>
        <SectionHeader title="Events" count={null} />
        <p className="text-red-400 text-sm py-8 text-center">Failed to load events.</p>
      </section>
    );

  return (
    <section>
      <SectionHeader
        title="Events"
        count={hasActiveFilters ? `${sorted.length} / ${events.length}` : `${events.length}`}
      />

      {/* Filter + sort controls */}
      <div className="mb-3 space-y-2">
        {/* Row 1: filters */}
        <div className="flex flex-wrap items-center gap-2">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={selectClass}>
            <option value="">All Statuses</option>
            {availableStatuses.map((s) => (
              <option key={s} value={s}>{normalizeStatus(s)}</option>
            ))}
          </select>

          <select value={sportFilter} onChange={(e) => setSportFilter(e.target.value)} className={selectClass}>
            <option value="">All Sports</option>
            {availableSports.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          <div className="h-4 w-px bg-zinc-800" />

          <ToggleButton active={mismatchOnly} onClick={() => setMismatchOnly((v) => !v)}>
            Mismatches
          </ToggleButton>
          <ToggleButton active={flaggedOnly} onClick={() => setFlaggedOnly((v) => !v)}>
            Flagged
          </ToggleButton>

          {hasActiveFilters && (
            <button
              className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors ml-1"
              onClick={() => {
                setStatusFilter("");
                setSportFilter("");
                setMismatchOnly(false);
                setFlaggedOnly(false);
              }}
            >
              Clear
            </button>
          )}
        </div>

        {/* Row 2: group order */}
        <GroupOrderControl order={statusOrder} onChange={setStatusOrder} />
      </div>

      {/* Table */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800 hover:bg-transparent">
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider px-3">PX ID</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Event</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Sport</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Starts</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">ProphetX</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Odds API</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Sports API</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">SDIO</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">ESPN</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Flag</TableHead>
              <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider">Checked</TableHead>
              {canSync && <TableHead className="text-zinc-500 text-[11px] font-medium uppercase tracking-wider" />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((event) => (
              <TableRow
                key={event.id}
                className={cn(
                  "border-zinc-800/60 transition-colors",
                  event.status_match === false
                    ? "bg-red-500/5 border-l-2 border-l-red-500 hover:bg-red-500/8"
                    : event.is_flagged
                    ? "bg-amber-500/5 hover:bg-amber-500/8"
                    : "hover:bg-zinc-800/30"
                )}
              >
                <TableCell className="px-3 font-mono text-[11px] text-zinc-600 whitespace-nowrap">
                  {event.prophetx_event_id}
                </TableCell>
                <TableCell className="text-zinc-200 font-medium text-sm">
                  {event.name}
                </TableCell>
                <TableCell className="text-zinc-400 text-xs">{event.sport}</TableCell>
                <TableCell className="font-mono text-[11px] text-zinc-500 whitespace-nowrap">
                  {event.scheduled_start
                    ? format(new Date(event.scheduled_start), "MM/dd HH:mm")
                    : <span className="text-zinc-700">—</span>}
                </TableCell>
                <TableCell>
                  <PxStatusPill status={event.prophetx_status} isMismatch={event.status_match === false} />
                </TableCell>
                <TableCell><SourceStatus status={event.odds_api_status} /></TableCell>
                <TableCell><SourceStatus status={event.sports_api_status} /></TableCell>
                <TableCell><SourceStatus status={event.sdio_status} /></TableCell>
                <TableCell><SourceStatus status={event.espn_status} /></TableCell>
                <TableCell><FlaggedBadge flagged={event.is_flagged} /></TableCell>
                <TableCell className="font-mono text-[11px] text-zinc-600 whitespace-nowrap">
                  {event.last_prophetx_poll
                    ? format(new Date(event.last_prophetx_poll), "HH:mm:ss")
                    : <span className="text-zinc-700">—</span>}
                </TableCell>
                {canSync && (
                  <TableCell>
                    <button
                      onClick={() => syncMutation.mutate(event.id)}
                      disabled={syncMutation.isPending}
                      className="h-6 px-2.5 rounded text-[11px] font-medium border border-zinc-700 text-zinc-500 hover:text-zinc-200 hover:border-zinc-500 hover:bg-zinc-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Sync
                    </button>
                  </TableCell>
                )}
              </TableRow>
            ))}

            {sorted.length === 0 && (
              <TableRow className="hover:bg-transparent border-0">
                <TableCell
                  colSpan={canSync ? 12 : 11}
                  className="text-center text-zinc-600 py-12 text-sm"
                >
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

/* ─── Section header ─── */

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
