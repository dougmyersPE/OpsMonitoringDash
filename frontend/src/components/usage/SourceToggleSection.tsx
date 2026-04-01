import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { updateInterval } from "../../api/usage";

const SOURCE_DISPLAY: Record<string, string> = {
  odds_api: "Odds API",
  sports_data: "SportsDataIO",
  espn: "ESPN",
};

interface SourceToggleSectionProps {
  sourcesEnabled: Record<string, boolean>;
}

export default function SourceToggleSection({ sourcesEnabled }: SourceToggleSectionProps) {
  const queryClient = useQueryClient();
  const [successSource, setSuccessSource] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) =>
      updateInterval(key, value),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["usage"] });
      const src = variables.key.replace("source_enabled_", "");
      setSuccessSource(src);
      setTimeout(() => setSuccessSource(null), 1500);
    },
  });

  function toggle(source: string) {
    const current = sourcesEnabled[source] ?? true;
    mutation.mutate({
      key: `source_enabled_${source}`,
      value: current ? "false" : "true",
    });
  }

  return (
    <section>
      <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-3">
        Data Sources
      </h2>

      <div className="rounded-lg bg-zinc-900 border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left px-5 py-3 text-zinc-400 font-medium">Source</th>
              <th className="text-left px-5 py-3 text-zinc-400 font-medium">Status</th>
              <th className="text-right px-5 py-3 text-zinc-400 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {Object.keys(SOURCE_DISPLAY).map((source) => {
              const enabled = sourcesEnabled[source] ?? true;
              const isSuccess = successSource === source;

              return (
                <tr key={source} className="border-b border-zinc-800/50 last:border-0">
                  <td className="px-5 py-3 text-zinc-200">
                    {SOURCE_DISPLAY[source]}
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className={
                        enabled
                          ? "text-emerald-400 font-medium"
                          : "text-red-400 font-medium"
                      }
                    >
                      {enabled ? "Enabled" : "Disabled"}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {isSuccess && (
                        <Check className="h-4 w-4 text-emerald-400" />
                      )}
                      <button
                        type="button"
                        className={`px-3 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-50 ${
                          enabled
                            ? "bg-red-900/50 text-red-300 hover:bg-red-900/80 border border-red-800"
                            : "bg-emerald-900/50 text-emerald-300 hover:bg-emerald-900/80 border border-emerald-800"
                        }`}
                        onClick={() => toggle(source)}
                        disabled={mutation.isPending}
                      >
                        {enabled ? "Disable" : "Enable"}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-zinc-500 mt-2">
        Disabled sources stop polling and are excluded from mismatch detection.
      </p>
    </section>
  );
}
