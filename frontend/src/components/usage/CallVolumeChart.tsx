import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { format } from "date-fns";
import type { HistoryEntry } from "../../api/usage";

const WORKER_COLORS: Record<string, string> = {
  poll_prophetx: "#6366f1",
  poll_sports_data: "#22c55e",
  poll_odds_api: "#f59e0b",
  poll_sports_api: "#3b82f6",
  poll_espn: "#ec4899",
};

const WORKER_DISPLAY_NAMES: Record<string, string> = {
  poll_prophetx: "ProphetX",
  poll_sports_data: "SportsDataIO",
  poll_odds_api: "Odds API",
  poll_sports_api: "Sports API",
  poll_espn: "ESPN",
};

const WORKER_KEYS = Object.keys(WORKER_COLORS);

function formatDate(dateStr: string): string {
  try {
    return format(new Date(dateStr + "T00:00:00"), "MMM d");
  } catch {
    return dateStr;
  }
}

interface CallVolumeChartProps {
  data: HistoryEntry[];
}

export default function CallVolumeChart({ data }: CallVolumeChartProps) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
        <XAxis
          dataKey="date"
          tickFormatter={formatDate}
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          axisLine={{ stroke: "#3f3f46" }}
          tickLine={{ stroke: "#3f3f46" }}
        />
        <YAxis
          tick={{ fill: "#a1a1aa", fontSize: 12 }}
          axisLine={{ stroke: "#3f3f46" }}
          tickLine={{ stroke: "#3f3f46" }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#18181b",
            border: "1px solid #3f3f46",
            borderRadius: "0.5rem",
            color: "#e4e4e7",
            fontSize: "0.875rem",
          }}
          labelFormatter={(label) => formatDate(String(label))}
          formatter={(value, name) => [
            Number(value).toLocaleString(),
            WORKER_DISPLAY_NAMES[String(name)] ?? String(name),
          ]}
        />
        <Legend
          formatter={(value: string) => WORKER_DISPLAY_NAMES[value] ?? value}
          wrapperStyle={{ fontSize: "0.75rem", color: "#a1a1aa" }}
        />
        {WORKER_KEYS.map((worker) => (
          <Bar
            key={worker}
            dataKey={worker}
            stackId="calls"
            fill={WORKER_COLORS[worker]}
            radius={[0, 0, 0, 0]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
