import { useState, useEffect } from "react";
import { getScanStatus } from "./api";
import SetupPage from "./pages/Setup";
import GroupReviewPage from "./pages/GroupReview";
import TournamentPage from "./pages/Tournament";
import RankingsPage from "./pages/Rankings";

export type Page = "setup" | "review" | "tournament" | "rankings";

function loadSavedFolder(): string {
  try { return localStorage.getItem("selectedFolder") || ""; } catch { return ""; }
}

export default function App() {
  const [page, setPage] = useState<Page>("setup");
  const [folder, setFolder] = useState<string>(loadSavedFolder());

  const selectFolder = (f: string) => {
    setFolder(f);
    try { localStorage.setItem("selectedFolder", f); } catch { /* ignore */ }
  };

  useEffect(() => {
    getScanStatus(folder).then((s) => {
      if (s.status === "done") setPage("review");
    }).catch(() => {});
  }, [folder]);

  return (
    <div style={{ height: "100vh", background: "#111", color: "#eee", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <nav style={{
        padding: "8px 16px",
        background: "#1a1a1a",
        borderBottom: "1px solid #333",
        display: "flex",
        gap: "16px",
        alignItems: "center",
        flexShrink: 0,
      }}>
        <h1 style={{ margin: 0, fontSize: "16px", fontWeight: 600, marginRight: "auto" }}>
          Photo Sorter
        </h1>
        {folder && (
          <span style={{ color: "#888", fontSize: "13px", background: "#2a2a3e", padding: "4px 10px", borderRadius: "4px" }}>
            📁 {folder}
          </span>
        )}
        {(["setup", "review", "tournament", "rankings"] as Page[]).map((p) => (
          <button
            key={p}
            onClick={() => setPage(p)}
            style={{
              background: page === p ? "#444" : "transparent",
              color: page === p ? "#fff" : "#999",
              border: "none",
              padding: "6px 12px",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "13px",
              textTransform: "capitalize",
            }}
          >
            {p === "setup" ? "Home" : p}
          </button>
        ))}
      </nav>
      <main style={{ flex: 1, overflow: "auto", padding: "8px" }}>
        {page === "setup" && (
          <SetupPage folder={folder} onSelectFolder={selectFolder} onNavigate={(p: string) => setPage(p as Page)} />
        )}
        {page === "review" && (
          <GroupReviewPage folder={folder} onNavigate={(p: string) => setPage(p as Page)} />
        )}
        {page === "tournament" && <TournamentPage folder={folder} />}
        {page === "rankings" && <RankingsPage folder={folder} />}
      </main>
    </div>
  );
}
