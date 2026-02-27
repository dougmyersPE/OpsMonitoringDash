import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Bell } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { fetchNotifications, markRead, markAllRead, type Notification } from "../api/notifications";

export default function NotificationCenter() {
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: fetchNotifications,
    staleTime: 10_000,
  });

  const markReadMutation = useMutation({
    mutationFn: markRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const markAllMutation = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unreadCount = data?.unread_count ?? 0;
  const notifications = data?.notifications ?? [];

  function getTypeLabel(type: string): string {
    return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  return (
    <Sheet>
      <SheetTrigger asChild>
        <button
          className="relative p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
          aria-label="Notifications"
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 h-4 w-4 min-w-0 rounded-full bg-indigo-600 flex items-center justify-center text-[9px] font-bold text-white leading-none">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </button>
      </SheetTrigger>

      <SheetContent side="right" className="w-96 overflow-y-auto bg-zinc-900 border-zinc-800">
        <SheetHeader className="flex flex-row items-center justify-between pr-0 pb-4 border-b border-zinc-800">
          <SheetTitle className="text-zinc-100 text-sm font-semibold">Notifications</SheetTitle>
          {unreadCount > 0 && (
            <button
              onClick={() => markAllMutation.mutate()}
              disabled={markAllMutation.isPending}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-40"
            >
              Mark all read
            </button>
          )}
        </SheetHeader>

        <div className="mt-4 space-y-2">
          {notifications.length === 0 && (
            <p className="text-zinc-600 text-sm text-center py-12">No notifications yet</p>
          )}

          {notifications.map((n: Notification) => (
            <div
              key={n.id}
              className={cn(
                "p-3 rounded-lg border text-sm",
                n.is_read
                  ? "bg-zinc-800/40 border-zinc-800"
                  : "bg-indigo-500/8 border-indigo-500/20"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className={cn(
                    "text-[10px] font-semibold uppercase tracking-wider mb-0.5",
                    n.is_read ? "text-zinc-600" : "text-indigo-400"
                  )}>
                    {getTypeLabel(n.type)}
                  </p>
                  <p className="text-zinc-300 text-xs leading-relaxed">{n.message}</p>
                  {n.entity_type && n.entity_id && (
                    <a
                      href={n.entity_type === "market" ? "/#markets" : "/#events"}
                      className="text-indigo-400 text-[10px] mt-1.5 hover:text-indigo-300 transition-colors block"
                      title={`Go to ${n.entity_type}: ${n.entity_id}`}
                    >
                      {n.entity_type}: {n.entity_id.slice(0, 8)}…
                    </a>
                  )}
                  <p className="text-zinc-600 text-[10px] mt-1">
                    {format(new Date(n.created_at), "MMM d, HH:mm")}
                  </p>
                </div>
                {!n.is_read && (
                  <button
                    className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors whitespace-nowrap shrink-0 mt-0.5"
                    onClick={() => markReadMutation.mutate(n.id)}
                  >
                    Mark read
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
