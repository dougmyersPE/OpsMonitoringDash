import EventsTable from "../components/EventsTable";
import MarketsTable from "../components/MarketsTable";
import SystemHealth from "../components/SystemHealth";
import SseProvider from "../components/SseProvider";
import NotificationCenter from "../components/NotificationCenter";

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-slate-50">
      <SseProvider />
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900">Prophet Monitor</h1>
        <div className="flex items-center gap-4">
          <SystemHealth />
          <NotificationCenter />
        </div>
      </header>
      <main className="p-6 space-y-8">
        <EventsTable />
        <MarketsTable />
      </main>
    </div>
  );
}
