import { useState, useEffect } from "react";
import { getRankings, exportPhotos, thumbnailUrl, skipPhoto } from "../api";
import type { Ranking } from "../api";

export default function RankingsPage({ folder }: { folder: string }) {
  const [rankings, setRankings] = useState<Ranking[]>([]);
  const [cutoff, setCutoff] = useState(5);
  const [exported, setExported] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    getRankings(folder || undefined).then(setRankings);
  }, [folder]);

  async function handleSkip(r: Ranking) {
    const newSkipped = !r.skipped;
    await skipPhoto(r.photo_id, newSkipped);
    setRankings((prev) =>
      prev.map((p) => (p.photo_id === r.photo_id ? { ...p, skipped: newSkipped } : p))
    );
  }

  if (rankings.length === 0) {
    return (
      <div style={{ textAlign: "center", paddingTop: 40 }}>
        <h2>Rankings</h2>
        <p style={{ color: "#888" }}>
          Complete a tournament first to see rankings.
        </p>
      </div>
    );
  }

  const trancheCounts: Record<number, number> = {};
  rankings.forEach((r) => {
    trancheCounts[r.tranche] = (trancheCounts[r.tranche] || 0) + 1;
  });

  const selectedCount = rankings.filter((r) => r.tranche <= cutoff).length;

  const trancheColors = [
    "#2d2", "#4c4", "#6d6", "#8e8", "#aa8",
    "#cc8", "#ea8", "#f88", "#f44", "#f00",
  ];

  async function handleExport() {
    setExporting(true);
    const result = await exportPhotos(cutoff, folder || undefined);
    setExported(result.exported);
    setExporting(false);
  }

  return (
    <div>
      <h2>Rankings & Export</h2>
      {folder && <p style={{ color: "#888", marginBottom: 12 }}>Folder: {folder}</p>}

      <div style={{
        background: "#1a1a1a",
        padding: 20,
        borderRadius: 12,
        marginBottom: 24,
        display: "flex",
        gap: 24,
        alignItems: "center",
        flexWrap: "wrap",
      }}>
        <div>
          <label style={{ color: "#aaa", display: "block", marginBottom: 4 }}>Cutoff tranche</label>
          <input
            type="range"
            min={1}
            max={10}
            value={cutoff}
            onChange={(e) => setCutoff(Number(e.target.value))}
            style={{ width: 200 }}
          />
        </div>
        <div style={{ fontSize: "16px" }}>
          <span style={{ color: "#4f8" }}>{selectedCount}</span>
          <span style={{ color: "#888" }}> / {rankings.length} photos selected</span>
          <span style={{ color: "#888", marginLeft: 8 }}>(tranches 1–{cutoff})</span>
        </div>
        <button
          onClick={handleExport}
          disabled={exporting}
          style={{
            padding: "12px 24px",
            background: "#2a7",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            cursor: exporting ? "not-allowed" : "pointer",
            fontSize: "14px",
          }}
        >
          {exporting ? "Exporting..." : "Export to Best/"}
        </button>
        {exported !== null && (
          <span style={{ color: "#4f8" }}>Export started ({exported} queued)!</span>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {Array.from({ length: 10 }, (_, i) => i + 1).map((t) => (
          <div
            key={t}
            onClick={() => setCutoff(t)}
            style={{
              padding: "6px 14px",
              background: cutoff >= t ? trancheColors[t - 1] : "#333",
              color: cutoff >= t ? "#000" : "#888",
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "13px",
              fontWeight: cutoff === t ? 700 : 400,
              border: cutoff === t ? "2px solid #fff" : "2px solid transparent",
            }}
          >
            T{t} ({trancheCounts[t] || 0})
          </div>
        ))}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
          gap: 8,
          gridAutoRows: "1fr",
        }}
      >
        {rankings.map((r) => {
          const included = r.tranche <= cutoff;
          return (
            <div
              key={r.photo_id}
              style={{
                background: "#1a1a1a",
                borderRadius: "8px",
                overflow: "hidden",
                opacity: included && !r.skipped ? 1 : r.skipped ? 0.3 : 0.4,
                border: r.skipped ? "1px solid #f44" : included ? `2px solid ${trancheColors[r.tranche - 1]}` : "1px solid #333",
                display: "flex",
                flexDirection: "column",
              }}
            >
              <div style={{ background: "#0a0a0a", display: "flex", alignItems: "center", justifyContent: "center", aspectRatio: "1", position: "relative" }}>
                <img
                  src={thumbnailUrl(r.photo_id)}
                  alt={r.filename}
                  loading="lazy"
                  style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
                />
                <button
                  onClick={(e) => { e.stopPropagation(); handleSkip(r); }}
                  style={{
                    position: "absolute",
                    bottom: 4,
                    right: 4,
                    background: r.skipped ? "#2a7" : "#f44",
                    color: "#fff",
                    border: "none",
                    borderRadius: "4px",
                    padding: "2px 8px",
                    fontSize: "11px",
                    cursor: "pointer",
                  }}
                >
                  {r.skipped ? "Keep" : "Skip"}
                </button>
              </div>
              <div style={{ padding: "8px" }}>
                <div style={{ fontSize: "12px", color: "#aaa", marginBottom: 4 }}>
                  #{r.rank} · {r.filename}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px" }}>
                  <span style={{ color: trancheColors[r.tranche - 1], fontWeight: 700 }}>
                    T{r.tranche}
                  </span>
                  <span style={{ color: "#888" }}>
                    {Math.round(r.current_elo)} ELO
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
