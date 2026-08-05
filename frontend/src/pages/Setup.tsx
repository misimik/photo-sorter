import { useState, useEffect } from "react";
import { startScan, startAnalyze, startGroup, getStats, getFolders, subscribeProgress } from "../api";
import type { ProgressState } from "../api";

interface Props {
  folder: string;
  onSelectFolder: (f: string) => void;
  onNavigate: (p: string) => void;
}

export default function SetupPage({ folder, onSelectFolder, onNavigate }: Props) {
  const [stats, setStats] = useState<{ total_photos: number; total_groups: number; rated: number } | null>(null);
  const [folders, setFolders] = useState<string[]>([]);
  const [progress, setProgress] = useState<ProgressState | null>(null);

  useEffect(() => {
    getFolders().then(setFolders).catch(() => {});
    loadStats();
    const unsub = subscribeProgress(setProgress);
    return unsub;
  }, [folder]);

  useEffect(() => {
    loadStats();
  }, [folder, progress?.stages?.group?.[0]?.status]);

  async function loadStats() {
    try {
      const st = await getStats(folder || undefined);
      setStats(st);
    } catch { /* API not running */ }
  }

  const stageFor = (name: string) => {
    const rows = progress?.stages?.[name] || [];
    return rows.find((s) => s.folder === (folder || "")) || rows[0] || { total: 0, processed: 0, status: "idle" as const, folder: folder || "", error: null };
  };
  const scan = stageFor("scan");
  const analyze = stageFor("analyze");
  const grp = stageFor("group");

  async function handleScan() {
    await startScan(folder || undefined);
  }
  async function handleAnalyze() {
    await startAnalyze(folder || undefined);
  }
  async function handleGroup() {
    await startGroup(folder || undefined);
  }

  // Derive running state from actual progress (SSE), not manual flags.
  const scanning = scan.status === "running";
  const analyzing = analyze.status === "running";
  const grouping = grp.status === "running";
  const ready = scan.status === "done";

  function Bar({ label, data, color }: { label: string; data: { total: number; processed: number; status: string }; color: string }) {
    const pct = data.total > 0 ? Math.min(100, Math.round((data.processed / data.total) * 100)) : 0;
    return (
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", marginBottom: 4 }}>
          <span>{label}</span>
          <span style={{ color: "#888" }}>
            {data.total > 0 ? `${data.processed}/${data.total}` : ""} · {data.status}
          </span>
        </div>
        <div style={{ height: 8, background: "#333", borderRadius: 4, overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 4, transition: "width 0.2s" }} />
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 style={{ fontSize: "22px", marginBottom: 8 }}>Home</h2>
      <p style={{ color: "#999", marginBottom: 24 }}>
        {ready
          ? "Scan complete. You can now review groups."
          : "Choose a folder and start scanning."}
      </p>

      {folders.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 6, color: "#aaa", fontSize: "14px" }}>
            Select folder:
          </label>
          <select
            value={folder}
            onChange={(e) => onSelectFolder(e.target.value)}
            style={{
              padding: "8px 12px",
              background: "#2a2a3e",
              color: "#fff",
              border: "1px solid #555",
              borderRadius: "6px",
              fontSize: "14px",
              minWidth: "280px",
            }}
          >
            <option value="">-- All folders --</option>
            {folders.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        </div>
      )}

      <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        <button
          onClick={handleScan}
          disabled={scanning}
          style={{
            padding: "12px 24px",
            background: scanning ? "#555" : "#2a7",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            cursor: scanning ? "not-allowed" : "pointer",
            fontSize: "16px",
          }}
        >
          {scanning ? "Scanning..." : ready ? "Re-scan" : "Start Scan"}
        </button>
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          style={{
            padding: "12px 24px",
            background: analyzing ? "#555" : "#37f",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            cursor: analyzing ? "not-allowed" : "pointer",
            fontSize: "16px",
          }}
        >
          {analyzing ? "Analyzing..." : "Analyze"}
        </button>
        <button
          onClick={handleGroup}
          disabled={grouping}
          style={{
            padding: "12px 24px",
            background: grouping ? "#555" : "#a4f",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            cursor: grouping ? "not-allowed" : "pointer",
            fontSize: "16px",
          }}
        >
          {grouping ? "Grouping..." : "Group"}
        </button>
        {ready && (
          <>
            <button
              onClick={() => onNavigate("review")}
              style={{ padding: "12px 24px", background: "#37f", color: "#fff", border: "none", borderRadius: "8px", cursor: "pointer", fontSize: "16px" }}
            >
              Review Groups →
            </button>
            <button
              onClick={() => onNavigate("tournament")}
              style={{ padding: "12px 24px", background: "#a4f", color: "#fff", border: "none", borderRadius: "8px", cursor: "pointer", fontSize: "16px" }}
            >
              Tournament →
            </button>
          </>
        )}
      </div>

      <div style={{ background: "#1a1a2e", padding: 16, borderRadius: 8, marginBottom: 16 }}>
        <Bar label="Scan" data={scan} color="#2a7" />
        <Bar label="Analyze" data={analyze} color="#37f" />
        <Bar label="Group" data={grp} color="#a4f" />
      </div>

      {ready && stats && (
        <div style={{ background: "#1a2e1a", padding: 16, borderRadius: 8, marginBottom: 16 }}>
          <p style={{ margin: 0, color: "#4f8" }}>Scan complete</p>
          <p style={{ margin: "8px 0 0", color: "#aaa", fontSize: "14px" }}>
            {stats.total_photos} photos in {stats.total_groups} groups · {stats.rated} rated
          </p>
        </div>
      )}
    </div>
  );
}
