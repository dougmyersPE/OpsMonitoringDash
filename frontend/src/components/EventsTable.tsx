import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { ChevronDown, ChevronUp, ChevronsUpDown, GripVertical } from "lucide-react";
import { fetchEvents, refreshAllEvents, type EventRow } from "../api/events";
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

/* ─── Status pill components ─── */

function PxStatusPill({
  status,
  isMismatch,
  isCritical,
}: {
  status: string | null | undefined;
  isMismatch: boolean;
  isCritical: boolean;
}) {
  const display = normalizeStatus(status);

  if (isCritical) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-red-600/20 text-red-400 border border-red-500/40">
        <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse shrink-0" />
        {display}
      </span>
    );
  }

  if (isMismatch) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" />
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

/* ─── Column sort ─── */

type SortCol =
  | "prophetx_event_id"
  | "name"
  | "sport"
  | "scheduled_start"
  | "prophetx_status"
  | "odds_api_status"
  | "sports_api_status"
  | "sdio_status"
  | "espn_status"
  | "is_flagged"
  | "last_real_world_poll";

const DATE_COLS = new Set<SortCol>(["scheduled_start", "last_real_world_poll"]);
const STATUS_COLS = new Set<SortCol>([
  "prophetx_status",
  "odds_api_status",
  "sports_api_status",
  "sdio_status",
  "espn_status",
]);

function applySortCol(events: EventRow[], col: SortCol, dir: "asc" | "desc"): EventRow[] {
  return [...events].sort((a, b) => {
    const av = a[col as keyof EventRow];
    const bv = b[col as keyof EventRow];

    // Nulls always last regardless of direction
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;

    let cmp: number;
    if (DATE_COLS.has(col)) {
      cmp = new Date(av as string).getTime() - new Date(bv as string).getTime();
    } else if (col === "is_flagged") {
      // Flagged first = asc
      cmp = (bv ? 1 : 0) - (av ? 1 : 0);
    } else if (STATUS_COLS.has(col)) {
      cmp = normalizeStatus(av as string).localeCompare(normalizeStatus(bv as string));
    } else {
      cmp = String(av).localeCompare(String(bv));
    }

    return dir === "asc" ? cmp : -cmp;
  });
}

/* ─── Sortable header cell ─── */

function SortableHead({
  col,
  children,
  sortCol,
  sortDir,
  onSort,
  className,
}: {
  col: SortCol;
  children: React.ReactNode;
  sortCol: SortCol | null;
  sortDir: "asc" | "desc";
  onSort: (col: SortCol) => void;
  className?: string;
}) {
  const active = sortCol === col;
  return (
    <TableHead
      onClick={() => onSort(col)}
      className={cn(
        "text-[11px] font-medium uppercase tracking-wider cursor-pointer select-none group transition-colors",
        active ? "text-zinc-300" : "text-zinc-500 hover:text-zinc-300",
        className,
      )}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {active ? (
          sortDir === "asc" ? (
            <ChevronUp className="h-3 w-3 text-indigo-400 shrink-0" />
          ) : (
            <ChevronDown className="h-3 w-3 text-indigo-400 shrink-0" />
          )
        ) : (
          <ChevronsUpDown className="h-3 w-3 shrink-0 opacity-0 group-hover:opacity-30 transition-opacity" />
        )}
      </span>
    </TableHead>
  );
}

/* ─── Group sort logic ─── */

function sortEvents(events: EventRow[], statusOrder: string[]): EventRow[] {
  const now = Date.now();

  const byClosestStart = (a: EventRow, b: EventRow) => {
    const aMs = a.scheduled_start
      ? Math.abs(new Date(a.scheduled_start).getTime() - now)
      : Number.MAX_SAFE_INTEGER;
    const bMs = b.scheduled_start
      ? Math.abs(new Date(b.scheduled_start).getTime() - now)
      : Number.MAX_SAFE_INTEGER;
    return aMs - bMs;
  };

  // Critical events always float to the top, sorted by closest start
  const critical = events.filter((e) => e.is_critical).sort(byClosestStart);
  const rest = events.filter((e) => !e.is_critical);

  // Bucket remaining by normalized status
  const buckets = new Map<string, EventRow[]>();
  const other: EventRow[] = [];

  for (const ev of rest) {
    const display = normalizeStatus(ev.prophetx_status);
    if (statusOrder.includes(display)) {
      if (!buckets.has(display)) buckets.set(display, []);
      buckets.get(display)!.push(ev);
    } else {
      other.push(ev);
    }
  }

  const result: EventRow[] = [...critical];
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
  const canRefresh = role === "admin" || role === "operator";

  const { data: events = [], isLoading, error } = useQuery({
    queryKey: ["events"],
    queryFn: fetchEvents,
  });

  const refreshMutation = useMutation({
    mutationFn: refreshAllEvents,
    onSuccess: () => {
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["events"] }), 3000);
    },
  });

  const [statusFilter, setStatusFilter] = useState("");
  const [sportFilter, setSportFilter] = useState("");
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [mismatchOnly, setMismatchOnly] = useState(false);
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [statusOrder, setStatusOrder] = useState<string[]>(ALL_STATUS_GROUPS);
  const [sortCol, setSortCol] = useState<SortCol | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [dense, setDense] = useState(false);

  function handleSort(col: SortCol) {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
  }

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
      if (criticalOnly && !e.is_critical) return false;
      if (mismatchOnly && e.status_match !== false) return false;
      if (flaggedOnly && !e.is_flagged) return false;
      return true;
    });
  }, [events, statusFilter, sportFilter, criticalOnly, mismatchOnly, flaggedOnly]);

  const sorted = useMemo(
    () => sortCol ? applySortCol(filtered, sortCol, sortDir) : sortEvents(filtered, statusOrder),
    [filtered, statusOrder, sortCol, sortDir]
  );

  const hasActiveFilters = !!statusFilter || !!sportFilter || criticalOnly || mismatchOnly || flaggedOnly || !!sortCol;

  function clearAll() {
    setStatusFilter("");
    setSportFilter("");
    setCriticalOnly(false);
    setMismatchOnly(false);
    setFlaggedOnly(false);
    setSortCol(null);
    setSortDir("asc");
  }

  const selectClass =
    "h-7 rounded-lg border border-zinc-700 bg-zinc-900 px-3 text-xs text-zinc-300 focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/20 cursor-pointer appearance-none";

  if (isLoading)
    return (
      <section>
        <SectionHeader title="Events" count={null} hasActiveFilters={false} onClear={clearAll} />
        <p className="text-zinc-600 text-sm py-8 text-center">Loading…</p>
      </section>
    );

  if (error)
    return (
      <section>
        <SectionHeader title="Events" count={null} hasActiveFilters={false} onClear={clearAll} />
        <p className="text-red-400 text-sm py-8 text-center">Failed to load events.</p>
      </section>
    );

  return (
    <section>
      <SectionHeader
        title="Events"
        count={hasActiveFilters ? `${sorted.length} / ${events.length}` : `${events.length}`}
        hasActiveFilters={hasActiveFilters}
        onClear={clearAll}
        onRefresh={canRefresh ? () => refreshMutation.mutate() : undefined}
        refreshing={refreshMutation.isPending}
        dense={dense}
        onDenseToggle={() => setDense((v) => !v)}
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

          <ToggleButton active={criticalOnly} onClick={() => setCriticalOnly((v) => !v)}>
            Critical
          </ToggleButton>
          <ToggleButton active={mismatchOnly} onClick={() => setMismatchOnly((v) => !v)}>
            Mismatches
          </ToggleButton>
          <ToggleButton active={flaggedOnly} onClick={() => setFlaggedOnly((v) => !v)}>
            Flagged
          </ToggleButton>

        </div>

        {/* Row 2: group order */}
        <GroupOrderControl order={statusOrder} onChange={setStatusOrder} />
      </div>

      {/* Table */}
      <div className={cn(
        "rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden",
        dense
          ? "[&_td]:px-1 [&_td]:py-0.5 [&_th]:px-1 [&_th]:h-7"
          : "[&_td]:px-1.5 [&_td]:py-1 [&_th]:px-1.5 [&_th]:h-8"
      )}>
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800 hover:bg-transparent">
              <SortableHead col="prophetx_event_id" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} className="px-3">PX ID</SortableHead>
              <SortableHead col="name" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>Event</SortableHead>
              <SortableHead col="sport" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>Sport</SortableHead>
              <SortableHead col="scheduled_start" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>Starts</SortableHead>
              <SortableHead col="prophetx_status" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>ProphetX</SortableHead>
              <SortableHead col="odds_api_status" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>Odds API</SortableHead>
              <SortableHead col="sports_api_status" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>Sports API</SortableHead>
              <SortableHead col="sdio_status" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>SDIO</SortableHead>
              <SortableHead col="espn_status" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>ESPN</SortableHead>
              <SortableHead col="is_flagged" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>Flag</SortableHead>
              <SortableHead col="last_real_world_poll" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>Checked</SortableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((event) => (
              <TableRow
                key={event.id}
                className={cn(
                  "border-zinc-800/60 transition-colors",
                  event.is_critical
                    ? "bg-red-600/10 border-l-2 border-l-red-500 hover:bg-red-600/15"
                    : event.status_match === false
                    ? "bg-amber-500/8 border-l-2 border-l-amber-500 hover:bg-amber-500/12"
                    : event.is_flagged
                    ? "bg-amber-500/5 hover:bg-amber-500/8"
                    : "hover:bg-zinc-800/30"
                )}
              >
                <TableCell className="font-mono text-[11px] text-zinc-600 whitespace-nowrap">
                  {event.prophetx_event_id}
                </TableCell>
                <TableCell className={cn(
                  "font-medium text-zinc-200",
                  dense ? "max-w-[200px] text-xs" : "max-w-[280px] text-xs"
                )}>
                  <span className="block truncate" title={event.name}>{event.name}</span>
                </TableCell>
                <TableCell className="text-zinc-400 text-xs">{event.sport}</TableCell>
                <TableCell className="font-mono text-[11px] text-zinc-500 whitespace-nowrap">
                  {event.scheduled_start
                    ? format(new Date(event.scheduled_start), "MM/dd HH:mm")
                    : <span className="text-zinc-700">—</span>}
                </TableCell>
                <TableCell>
                  <PxStatusPill status={event.prophetx_status} isMismatch={event.status_match === false} isCritical={event.is_critical} />
                </TableCell>
                <TableCell><SourceStatus status={event.odds_api_status} /></TableCell>
                <TableCell><SourceStatus status={event.sports_api_status} /></TableCell>
                <TableCell><SourceStatus status={event.sdio_status} /></TableCell>
                <TableCell><SourceStatus status={event.espn_status} /></TableCell>
                <TableCell><FlaggedBadge flagged={event.is_flagged} /></TableCell>
                <TableCell className="font-mono text-[11px] text-zinc-600 whitespace-nowrap">
                  {event.last_real_world_poll
                    ? format(new Date(event.last_real_world_poll), "HH:mm:ss")
                    : <span className="text-zinc-700">—</span>}
                </TableCell>
              </TableRow>
            ))}

            {sorted.length === 0 && (
              <TableRow className="hover:bg-transparent border-0">
                <TableCell
                  colSpan={11}
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

function SectionHeader({
  title,
  count,
  hasActiveFilters,
  onClear,
  onRefresh,
  refreshing,
  dense,
  onDenseToggle,
}: {
  title: string;
  count: string | null;
  hasActiveFilters: boolean;
  onClear: () => void;
  onRefresh?: () => void;
  refreshing?: boolean;
  dense?: boolean;
  onDenseToggle?: () => void;
}) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider shrink-0">{title}</h2>
      <div className="flex-1 h-px bg-zinc-800" />
      {count !== null && (
        <span className="text-xs text-zinc-600 shrink-0">{count}</span>
      )}
      {onDenseToggle && (
        <button
          onClick={onDenseToggle}
          title={dense ? "Switch to comfortable view" : "Switch to dense view"}
          className={cn(
            "h-6 px-2 rounded-md text-[11px] font-medium border transition-colors",
            dense
              ? "bg-zinc-700/60 text-zinc-200 border-zinc-600"
              : "border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-600 hover:bg-zinc-800"
          )}
        >
          Dense
        </button>
      )}
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={refreshing}
          title="Refresh all sources"
          className="h-6 w-6 rounded-md flex items-center justify-center border transition-colors disabled:opacity-40 disabled:cursor-not-allowed border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-500 hover:bg-zinc-800"
        >
          <svg
            viewBox="0 0 16 16"
            fill="none"
            className={cn("h-3.5 w-3.5", refreshing && "animate-spin")}
          >
            <path
              d="M13.5 8A5.5 5.5 0 1 1 8 2.5a5.48 5.48 0 0 1 3.89 1.61L10 6h4V2l-1.46 1.46A7 7 0 1 0 15 8h-1.5Z"
              fill="currentColor"
            />
          </svg>
        </button>
      )}
      <button
        onClick={onClear}
        disabled={!hasActiveFilters}
        className="h-6 px-2.5 rounded-md text-[11px] font-medium border transition-colors disabled:opacity-25 disabled:cursor-default border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-500 hover:bg-zinc-800 disabled:hover:text-zinc-400 disabled:hover:border-zinc-700 disabled:hover:bg-transparent"
      >
        Clear filters
      </button>
    </div>
  );
}
