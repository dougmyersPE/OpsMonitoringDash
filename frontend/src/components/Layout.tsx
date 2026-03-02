import { Link, useLocation } from "react-router-dom";
import { Activity, BarChart2, Gauge } from "lucide-react";
import { cn } from "@/lib/utils";
import SystemHealth from "./SystemHealth";
import NotificationCenter from "./NotificationCenter";
import SseProvider from "./SseProvider";

const NAV_ITEMS = [
  { to: "/",        label: "Events",    Icon: Activity  },
  { to: "/markets", label: "Markets",   Icon: BarChart2 },
  { to: "/usage",   label: "API Usage", Icon: Gauge     },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-zinc-950 flex">
      <SseProvider />

      {/* Sidebar */}
      <aside className="w-52 shrink-0 bg-zinc-900 border-r border-zinc-800 sticky top-0 h-screen flex flex-col">
        {/* Logo */}
        <div className="px-4 py-4 border-b border-zinc-800 flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-md bg-indigo-600 flex items-center justify-center shrink-0">
            <svg viewBox="0 0 16 16" fill="none" className="h-4 w-4">
              <path d="M8 2L14 13H2L8 2Z" fill="white" fillOpacity="0.9" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-zinc-100 tracking-tight">Prophet Monitor</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          {NAV_ITEMS.map(({ to, label, Icon }) => {
            const isActive = location.pathname === to;
            return (
              <Link
                key={to}
                to={to}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/50"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Right column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="sticky top-0 z-40 bg-zinc-900/90 backdrop-blur-md border-b border-zinc-800">
          <div className="px-6 py-3 flex items-center justify-end">
            <div className="flex items-center gap-3">
              <SystemHealth />
              <div className="h-4 w-px bg-zinc-700" />
              <NotificationCenter />
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="px-6 py-6 max-w-[1800px] mx-auto w-full">
          {children}
        </main>
      </div>
    </div>
  );
}
