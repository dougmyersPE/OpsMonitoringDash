import { useState, useRef, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import type { IntervalInfo } from "../../api/usage";
import { updateInterval } from "../../api/usage";

const WORKER_DISPLAY_NAMES: Record<string, string> = {
  poll_prophetx: "ProphetX",
  poll_sports_data: "SportsDataIO",
  poll_odds_api: "Odds API",
  poll_espn: "ESPN",
  poll_critical_check: "Critical Check",
};

const WORKER_CONFIG_KEYS: Record<string, string> = {
  poll_prophetx: "poll_interval_prophetx",
  poll_sports_data: "poll_interval_sports_data",
  poll_odds_api: "poll_interval_odds_api",
  poll_espn: "poll_interval_espn",
  poll_critical_check: "poll_interval_critical_check",
};

interface IntervalSectionProps {
  intervals: Record<string, IntervalInfo>;
}

export default function IntervalSection({ intervals }: IntervalSectionProps) {
  const queryClient = useQueryClient();
  const [editingWorker, setEditingWorker] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successWorker, setSuccessWorker] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when entering edit mode
  useEffect(() => {
    if (editingWorker && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingWorker]);

  const mutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) =>
      updateInterval(key, value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["usage"] });
      const worker = editingWorker;
      setEditingWorker(null);
      setEditValue("");
      setErrorMessage(null);

      // Green checkmark flash
      setSuccessWorker(worker);
      setTimeout(() => setSuccessWorker(null), 1500);
    },
    onError: (error: unknown) => {
      // Extract validation error detail from 422 response
      const axiosError = error as { response?: { data?: { detail?: string } } };
      const detail = axiosError?.response?.data?.detail;
      setErrorMessage(detail ?? "Failed to update interval");
    },
  });

  function startEdit(worker: string) {
    setEditingWorker(worker);
    setEditValue(String(intervals[worker]?.current ?? ""));
    setErrorMessage(null);
  }

  function cancelEdit() {
    setEditingWorker(null);
    setEditValue("");
    setErrorMessage(null);
  }

  function saveEdit(worker: string) {
    const configKey = WORKER_CONFIG_KEYS[worker];
    if (!configKey) return;

    const minimum = intervals[worker]?.minimum ?? 0;
    const numValue = parseInt(editValue, 10);
    if (isNaN(numValue) || numValue < minimum) {
      setErrorMessage(`Value must be at least ${minimum} seconds`);
      return;
    }

    mutation.mutate({ key: configKey, value: editValue });
  }

  return (
    <section>
      <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-3">
        Poll Intervals
      </h2>

      <div className="rounded-lg bg-zinc-900 border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left px-5 py-3 text-zinc-400 font-medium">Worker</th>
              <th className="text-left px-5 py-3 text-zinc-400 font-medium">
                Current Interval
              </th>
              <th className="text-left px-5 py-3 text-zinc-400 font-medium">Minimum</th>
              <th className="text-right px-5 py-3 text-zinc-400 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(intervals).map(([worker, info]) => {
              const isEditing = editingWorker === worker;
              const isSuccess = successWorker === worker;

              return (
                <tr key={worker} className="border-b border-zinc-800/50 last:border-0">
                  <td className="px-5 py-3 text-zinc-200">
                    {WORKER_DISPLAY_NAMES[worker] ?? worker}
                  </td>
                  <td className="px-5 py-3">
                    {isEditing ? (
                      <div>
                        <input
                          ref={inputRef}
                          type="number"
                          className="w-24 rounded-md bg-zinc-800 border border-zinc-700 px-2 py-1 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500"
                          value={editValue}
                          onChange={(e) => {
                            setEditValue(e.target.value);
                            setErrorMessage(null);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") saveEdit(worker);
                            if (e.key === "Escape") cancelEdit();
                          }}
                          min={info.minimum}
                        />
                        {errorMessage && (
                          <p className="text-red-400 text-xs mt-1">{errorMessage}</p>
                        )}
                      </div>
                    ) : (
                      <span className="text-zinc-100">{info.current}s</span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-zinc-500">{info.minimum}s</td>
                  <td className="px-5 py-3 text-right">
                    {isEditing ? (
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          className="px-3 py-1 rounded-md bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-500 transition-colors disabled:opacity-50"
                          onClick={() => saveEdit(worker)}
                          disabled={mutation.isPending}
                        >
                          {mutation.isPending ? "..." : "Save"}
                        </button>
                        <button
                          type="button"
                          className="px-3 py-1 rounded-md bg-zinc-800 text-zinc-300 text-xs font-medium hover:bg-zinc-700 transition-colors"
                          onClick={cancelEdit}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-end gap-2">
                        {isSuccess && (
                          <Check className="h-4 w-4 text-emerald-400" />
                        )}
                        <button
                          type="button"
                          className="px-3 py-1 rounded-md bg-zinc-800 text-zinc-300 text-xs font-medium hover:bg-zinc-700 transition-colors"
                          onClick={() => startEdit(worker)}
                        >
                          Edit
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
