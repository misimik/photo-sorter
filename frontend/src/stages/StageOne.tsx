import type { ProgressState } from "../api";

function Bar({ label, data }: { label: string; data?: { total: number; processed: number; status: string; error: string | null } }) {
  const pct = data && data.total > 0 ? Math.round((data.processed / data.total) * 100) : 0;
  return (
    <div className="mb-4">
      <div className="flex justify-between text-xs text-neutral-400 mb-1">
        <span>{label}</span>
        <span>{data ? `${data.processed}/${data.total} · ${data.status}` : "idle"}</span>
      </div>
      <div className="h-2 bg-neutral-800 rounded overflow-hidden">
        <div className="h-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
      {data?.error && <p className="text-xs text-red-400 mt-1">{data.error}</p>}
    </div>
  );
}

export function StageOne({
  progress,
  onRunScan,
  onRunAnalyze,
  onRunGroup,
}: {
  progress: ProgressState | null;
  onRunScan: () => void;
  onRunAnalyze: () => void;
  onRunGroup: () => void;
}) {
  return (
    <div className="p-8 max-w-xl mx-auto">
      <h1 className="text-2xl font-semibold mb-6">Stage 1 — Scan, Analyze, Group</h1>
      <Bar label="Scan (incremental)" data={progress?.stages.scan} />
      <Bar label="Analyze (hashes + sharpness)" data={progress?.stages.analyze} />
      <Bar label="Group (time windows + dHash)" data={progress?.stages.group} />

      <div className="flex gap-3 mt-8">
        <button
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded disabled:opacity-50"
          onClick={onRunScan}
          disabled={progress?.stages.scan.status === "running"}
        >
          Scan
        </button>
        <button
          className="px-4 py-2 bg-neutral-700 hover:bg-neutral-600 rounded disabled:opacity-50"
          onClick={onRunAnalyze}
          disabled={progress?.stages.analyze.status === "running"}
        >
          Analyze
        </button>
        <button
          className="px-4 py-2 bg-neutral-700 hover:bg-neutral-600 rounded disabled:opacity-50"
          onClick={onRunGroup}
          disabled={progress?.stages.group.status === "running"}
        >
          Group
        </button>
      </div>
      <p className="text-xs text-neutral-500 mt-6">
        Scan is idempotent — re-running only processes new/changed files. Progress survives refresh.
      </p>
    </div>
  );
}
