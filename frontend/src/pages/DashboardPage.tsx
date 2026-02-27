import EventsTable from "../components/EventsTable";
import MarketsTable from "../components/MarketsTable";
import SystemHealth from "../components/SystemHealth";
import SseProvider from "../components/SseProvider";
import NotificationCenter from "../components/NotificationCenter";

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-zinc-950">
      <SseProvider />

      {/* Header */}
      <header className="sticky top-0 z-40 bg-zinc-900/90 backdrop-blur-md border-b border-zinc-800">
        <div className="px-6 py-3 flex items-center justify-between">
          {/* Logo + Title */}
          <div className="flex items-center gap-3">
            <div className="h-7 w-7 rounded-md bg-indigo-600 flex items-center justify-center shrink-0">
              <svg viewBox="0 0 16 16" fill="none" className="h-4 w-4">
                <path d="M8 2L14 13H2L8 2Z" fill="white" fillOpacity="0.9" />
              </svg>
            </div>
            <span className="text-sm font-semibold text-zinc-100 tracking-tight">
              Prophet Monitor
            </span>
          </div>

          {/* Right side */}
          <div className="flex items-center gap-3">
            <SystemHealth />
            <div className="h-4 w-px bg-zinc-700" />
            <NotificationCenter />
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="px-6 py-6 space-y-8 max-w-[1800px] mx-auto">
        <EventsTable />
        <MarketsTable />
      </main>
    </div>
  );
}
