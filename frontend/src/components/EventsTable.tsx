import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { fetchEvents, syncEventStatus } from "../api/events";
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

  if (isLoading) return <p className="text-slate-500">Loading events...</p>;
  if (error) return <p className="text-red-600">Failed to load events.</p>;

  return (
    <section>
      <h2 className="text-lg font-semibold text-slate-800 mb-3">Events</h2>
      <div className="rounded-lg border bg-white overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Event</TableHead>
              <TableHead>Sport</TableHead>
              <TableHead>ProphetX Status</TableHead>
              <TableHead>Real-World Status</TableHead>
              <TableHead>Flagged</TableHead>
              <TableHead>Last Checked</TableHead>
              {canSync && <TableHead>Action</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.map((event) => (
              <TableRow
                key={event.id}
                className={cn(
                  !event.status_match && "bg-red-50 border-l-4 border-l-red-500"
                )}
              >
                <TableCell className="font-medium">{event.name}</TableCell>
                <TableCell>{event.sport}</TableCell>
                <TableCell>
                  <Badge variant={event.status_match ? "secondary" : "destructive"}>
                    {event.prophetx_status ?? "—"}
                  </Badge>
                </TableCell>
                <TableCell>{event.real_world_status ?? "—"}</TableCell>
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
            {events.length === 0 && (
              <TableRow>
                <TableCell colSpan={canSync ? 7 : 6} className="text-center text-slate-400 py-8">
                  No events yet
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}
