import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Bell } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
        <button className="relative p-1 rounded hover:bg-slate-100" aria-label="Notifications">
          <Bell className="h-5 w-5 text-slate-600" />
          {unreadCount > 0 && (
            <Badge
              variant="destructive"
              className="absolute -top-1 -right-1 h-4 w-4 min-w-0 rounded-full p-0 flex items-center justify-center text-[10px]"
            >
              {unreadCount > 99 ? "99+" : unreadCount}
            </Badge>
          )}
        </button>
      </SheetTrigger>
      <SheetContent side="right" className="w-96 overflow-y-auto">
        <SheetHeader className="flex flex-row items-center justify-between pr-0">
          <SheetTitle>Notifications</SheetTitle>
          {unreadCount > 0 && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => markAllMutation.mutate()}
              disabled={markAllMutation.isPending}
              className="text-xs"
            >
              Mark all read
            </Button>
          )}
        </SheetHeader>
        <div className="mt-4 space-y-2">
          {notifications.length === 0 && (
            <p className="text-slate-400 text-sm text-center py-8">No notifications yet</p>
          )}
          {notifications.map((n: Notification) => (
            <div
              key={n.id}
              className={cn(
                "p-3 rounded-lg border text-sm",
                n.is_read ? "bg-white border-slate-200" : "bg-blue-50 border-blue-200"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-slate-900 text-xs uppercase tracking-wide">
                    {getTypeLabel(n.type)}
                  </p>
                  <p className="text-slate-700 mt-0.5">{n.message}</p>
                  {n.entity_type && n.entity_id && (
                    <a
                      href={n.entity_type === "market" ? "/#markets" : "/#events"}
                      className="text-blue-500 text-xs mt-1 hover:text-blue-700 hover:underline block"
                      title={`Go to ${n.entity_type}: ${n.entity_id}`}
                    >
                      {n.entity_type}: {n.entity_id.slice(0, 8)}...
                    </a>
                  )}
                  <p className="text-slate-400 text-xs mt-1">
                    {format(new Date(n.created_at), "MMM d, HH:mm")}
                  </p>
                </div>
                {!n.is_read && (
                  <button
                    className="text-blue-500 text-xs hover:text-blue-700 whitespace-nowrap shrink-0"
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
