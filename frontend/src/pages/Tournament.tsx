  import { useState, useEffect, useCallback, useRef } from "react";
import {
  initTournament,
  getNextPair,
  submitVote,
  getTournamentStats,
  previewUrl,
} from "../api";
import type { TournamentPair, TournamentStats } from "../api";
import { useGamepad } from "../hooks/useGamepad";

export default function TournamentPage({ folder }: { folder: string }) {
  const [pair, setPair] = useState<TournamentPair | null>(null);
  const [stats, setStats] = useState<TournamentStats | null>(null);
  const [phase, setPhase] = useState<"init" | "playing" | "done">("init");
  const [initMsg, setInitMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [minStars, setMinStars] = useState(1);

  async function handleInit() {
    setLoading(true);
    const result = await initTournament(minStars, folder || undefined);
    setLoading(false);
    if (result.status !== "ok") { setInitMsg(result.message || "Not enough photos."); return; }
    setPhase("playing");
    await loadPair();
  }

  async function loadPair() {
    const p = await getNextPair(folder || undefined, minStars);
    if (p.status === "completed" || !p.pair) {
      setStats(await getTournamentStats(folder || undefined, minStars));
      setPhase("done");
      return;
    }
    setPair(p);
  }

  const vote = useCallback(async (winnerId: number, loserId: number) => {
    await submitVote(winnerId, loserId);
    setPair(null);
    await loadPair();
  }, [minStars, folder]);

  const onKey = useCallback((key: string) => {
    if (!pair?.pair) return;
    if (key === "ArrowLeft") vote(pair.pair.photo_a.id, pair.pair.photo_b.id);
    if (key === "ArrowRight") vote(pair.pair.photo_b.id, pair.pair.photo_a.id);
    if (key === "ArrowUp" || key === "a" || key === "A") vote(pair.pair.photo_a.id, pair.pair.photo_b.id);
    if (key === "ArrowDown" || key === "d" || key === "D") vote(pair.pair.photo_b.id, pair.pair.photo_a.id);
  }, [pair, vote]);

  const onKeyRef = useRef(onKey);
  onKeyRef.current = onKey;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) e.preventDefault();
      onKeyRef.current(e.key);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);  // stable — attached once, never re-binds

  useGamepad(onKey, phase === "playing");

  if (phase === "init") return <InitScreen minStars={minStars} setMinStars={setMinStars} loading={loading} onInit={handleInit} initMsg={initMsg} />;
  if (phase === "done" && stats) return <DoneScreen stats={stats} />;
  if (!pair?.pair) return <p style={{ color: "#888", padding: 16 }}>Loading...</p>;

  const { photo_a, photo_b } = pair.pair;
  const views = pair.pair.total_views ?? 0;
  const max = pair.pair.max_views ?? 5;
  const pct = max > 0 ? Math.round((views / max) * 100) : 0;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <h2 style={{ textAlign: "center", margin: "8px 0", fontSize: "16px" }}>Pick the better photo</h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, flex: 1, minHeight: 0 }}>
        <ImagePanel photoId={photo_a.id} filename={photo_a.filename} onClick={() => vote(photo_a.id, photo_b.id)} />
        <ImagePanel photoId={photo_b.id} filename={photo_b.filename} onClick={() => vote(photo_b.id, photo_a.id)} />
      </div>
      <div style={{ padding: "8px 0", display: "flex", gap: 12, alignItems: "center" }}>
        <span style={{ color: "#888", fontSize: "12px" }}>← Pick left</span>
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 8, padding: "0 16px" }}>
          <div style={{ flex: 1, height: 6, background: "#333", borderRadius: 3, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${pct}%`, background: "#a4f", borderRadius: 3, transition: "width 0.2s" }} />
          </div>
          <span style={{ color: "#888", fontSize: "12px", whiteSpace: "nowrap" }}>
            {views}/{max} views
          </span>
        </div>
        <span style={{ color: "#888", fontSize: "12px", marginLeft: "auto" }}>Pick right →</span>
      </div>
    </div>
  );
}

function ImagePanel({ photoId, filename, onClick }: { photoId: number; filename: string; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      style={{ cursor: "pointer", border: "2px solid #444", borderRadius: "12px", overflow: "hidden", transition: "border-color 0.2s", display: "flex", background: "#0a0a0a", minHeight: 0 }}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#a4f")}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = "#444")}
    >
      <img src={previewUrl(photoId)} alt={filename} style={{ width: "100%", height: "100%", objectFit: "contain" }} />
    </div>
  );
}

function DoneScreen({ stats }: { stats: TournamentStats }) {
  return (
    <div>
      <h2>Tournament Complete!</h2>
      <p style={{ color: "#888" }}>{stats.total_matches} matches across {stats.total_photos} photos.</p>
      <p style={{ color: "#aaa", marginTop: 16 }}>
        See the full rankings on the <b>Rankings</b> tab.
      </p>
    </div>
  );
}

function InitScreen({ minStars, setMinStars, loading, onInit, initMsg }: {
  minStars: number; setMinStars: (v: number) => void; loading: boolean; onInit: () => void; initMsg: string;
}) {
  return (
    <div style={{ textAlign: "center", paddingTop: 40 }}>
      <h2>Tournament</h2>
      <p style={{ color: "#888", marginBottom: 24 }}>Head-to-head comparisons to rank your best photos.</p>
      <div style={{ marginBottom: 16 }}>
        <label style={{ color: "#aaa", marginRight: 8 }}>Minimum stars:</label>
        <select value={minStars} onChange={(e) => setMinStars(Number(e.target.value))} style={{ padding: "6px 12px", borderRadius: "6px", background: "#333", color: "#fff", border: "1px solid #555" }}>
          {[1, 2, 3, 4, 5].map((s) => (<option key={s} value={s}>{s}+ stars</option>))}
        </select>
      </div>
      <button onClick={onInit} disabled={loading} style={{ padding: "14px 32px", background: "#a4f", color: "#fff", border: "none", borderRadius: "8px", fontSize: "16px", cursor: loading ? "not-allowed" : "pointer" }}>
        {loading ? "Starting..." : "Start Tournament"}
      </button>
      {initMsg && <p style={{ color: "#f66", marginTop: 16 }}>{initMsg}</p>}
    </div>
  );
}
