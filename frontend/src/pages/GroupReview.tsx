import { useState, useEffect, useCallback, useRef } from "react";
import { getGroups, previewUrl } from "../api";
import type { Group, Photo } from "../api";
import PhotoCard from "../components/PhotoCard";
import { useRatingQueue } from "../hooks/useRatingQueue";
import { useGamepad } from "../hooks/useGamepad";
import { useGridLayout } from "../hooks/useGridLayout";

function loadSavedIdx(): number {
  try { return parseInt(localStorage.getItem("reviewGroupIdx") || "0"); } catch { return 0; }
}

export default function GroupReviewPage({ folder, onNavigate }: { folder: string; onNavigate: (p: string) => void }) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [currentGroupIdx, setCurrentGroupIdx] = useState(loadSavedIdx());
  const [group, setGroup] = useState<Group | null>(null);
  const [zoomedPhoto, setZoomedPhoto] = useState<Photo | null>(null);
  const [focusedIdx, setFocusedIdx] = useState(0);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const gridContainerRef = useRef<HTMLDivElement | null>(null);

  const { enqueue, flush } = useRatingQueue();
  const n = group?.photos.length ?? 0;
  const gridCols = useGridLayout(n, gridContainerRef);

  const goToGroup = useCallback((idx: number) => {
    flush();
    const clamped = Math.max(0, Math.min(groups.length - 1, idx));
    localStorage.setItem("reviewGroupIdx", String(clamped));
    setCurrentGroupIdx(clamped);
  }, [groups.length, flush]);

  useEffect(() => {
    getGroups(folder || undefined).then((gs) => {
      setGroups(gs);
      const saved = loadSavedIdx();
      const clamped = (saved >= 0 && saved < gs.length) ? saved : 0;
      localStorage.setItem("reviewGroupIdx", String(clamped));
      setCurrentGroupIdx(clamped);
      if (gs.length > 0) {
        setGroup(gs[clamped]);
      } else {
        setGroup(null);
      }
    });
  }, [folder]);

  const apply = useCallback((photoId: number, update: Partial<Photo>) => {
    setGroup((g) => {
      if (!g) return g;
      return { ...g, photos: g.photos.map((p) => (p.id === photoId ? { ...p, ...update } : p)) };
    });
  }, []);

  const rate = useCallback((photoId: number, stars?: number, toggle?: "reject" | "favorite" | "blurry" | "unreject" | "unfavorite" | "unblurry") => {
    const payload: Record<string, number | undefined> = {};
    if (stars !== undefined) payload.stars = stars;
    if (toggle === "reject") payload.is_rejected = 1;
    if (toggle === "favorite") payload.is_favorite = 1;
    if (toggle === "blurry") payload.user_blurry_override = 1;
    if (toggle === "unreject") payload.is_rejected = 0;
    if (toggle === "unfavorite") payload.is_favorite = 0;
    if (toggle === "unblurry") payload.user_blurry_override = 0;

    apply(photoId, {
      stars: stars !== undefined ? stars : undefined,
      is_rejected: payload.is_rejected as number | undefined,
      is_favorite: payload.is_favorite as number | undefined,
      user_blurry_override: payload.user_blurry_override as number | undefined,
    } as Partial<Photo>);

    enqueue({
      photoId,
      stars: payload.stars,
      is_rejected: payload.is_rejected,
      is_favorite: payload.is_favorite,
      user_blurry_override: payload.user_blurry_override,
    });
  }, [apply, enqueue]);

  const focus = useCallback((idx: number) => {
    const clamped = Math.max(0, Math.min(n - 1, idx));
    setFocusedIdx(clamped);
    cardRefs.current[clamped]?.focus();
  }, [n]);

  const moveFocus = useCallback((dx: number, dy: number) => {
    if (gridCols === 0) return;
    const row = Math.floor(focusedIdx / gridCols);
    const col = focusedIdx % gridCols;
    let nr = row + dy;
    let nc = col + dx;
    if (nc >= gridCols) { nc = 0; nr++; }
    if (nc < 0) { nc = gridCols - 1; nr--; }
    if (nr >= Math.ceil(n / gridCols)) { nr = 0; nc++; }
    if (nr < 0) { nr = Math.ceil(n / gridCols) - 1; nc--; }
    const ni = nr * gridCols + nc;
    if (ni >= 0 && ni < n) focus(ni);
  }, [focusedIdx, gridCols, n, focus]);

  const onKey = useCallback((key: string) => {
    if (zoomedPhoto) {
      if (key === "Escape" || key === " ") { setZoomedPhoto(null); return; }
      return;
    }
    const photos = group?.photos;
    if (!photos || photos.length === 0) return;
    const photo = photos[focusedIdx];
    if (!photo) return;

    if (key >= "1" && key <= "5") { rate(photo.id, parseInt(key)); return; }
    if (key === "0") { rate(photo.id, 0); return; }
    if (key === "x" || key === "X") { rate(photo.id, undefined, photo.is_rejected ? "unreject" : "reject"); return; }
    if (key === "f" || key === "F") { rate(photo.id, undefined, photo.is_favorite ? "unfavorite" : "favorite"); return; }
    if (key === "r" || key === "R") { rate(photo.id, undefined, photo.user_blurry_override ? "unblurry" : "blurry"); return; }
    if (key === " ") { setZoomedPhoto(photo); return; }
    if (key === "Enter") {
      flush();
      if (currentGroupIdx < groups.length - 1) {
        goToGroup(currentGroupIdx + 1);
      } else {
        onNavigate("tournament");
      }
      return;
    }
    if (key === "Backspace") {
      flush();
      if (currentGroupIdx > 0) goToGroup(currentGroupIdx - 1);
      return;
    }
    if (key === "ArrowLeft") { moveFocus(-1, 0); return; }
    if (key === "ArrowRight") { moveFocus(1, 0); return; }
    if (key === "ArrowUp") { moveFocus(0, -1); return; }
    if (key === "ArrowDown") { moveFocus(0, 1); return; }
    if (key === "Tab") { focus(focusedIdx + 1); return; }
  }, [zoomedPhoto, group, focusedIdx, currentGroupIdx, groups.length, rate, moveFocus, focus, onNavigate, goToGroup, flush]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Tab", "Enter", " ", "Backspace"].includes(e.key)) {
        e.preventDefault();
      }
      onKey(e.key);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onKey]);

  useGamepad(onKey, !zoomedPhoto);

  if (!group) return <p style={{ color: "#888", padding: 16 }}>No groups yet — run Scan + Analyze + Group on the Home tab.</p>;

  const isLast = currentGroupIdx >= groups.length - 1;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "4px 0 8px", flexShrink: 0 }}>
        <button onClick={() => goToGroup(currentGroupIdx - 1)} disabled={currentGroupIdx === 0} style={navBtn}>
          ← Prev
        </button>
        <h2 style={{ fontSize: "16px", margin: 0, flex: 1, textAlign: "center" }}>
          {group.start_time ? `Group ${currentGroupIdx + 1}: ${group.start_time.slice(0, 16).replace("T", " ")}` : `Group ${currentGroupIdx + 1}`}
        </h2>
        <span style={{ color: "#888", fontSize: "13px" }}>{currentGroupIdx + 1} / {groups.length}</span>
        <button
          onClick={() => isLast ? onNavigate("tournament") : goToGroup(currentGroupIdx + 1)}
          style={{ ...navBtn, background: isLast ? "#2a7" : "#333" }}
        >
          {isLast ? "Tournament →" : "Next →"}
        </button>
      </div>

      <div ref={gridContainerRef} style={{ flex: 1, overflow: "hidden", position: "relative", padding: 4 }}>
        {zoomedPhoto && (
          <div
            onClick={() => setZoomedPhoto(null)}
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.95)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center", cursor: "zoom-out" }}
          >
            <img src={previewUrl(zoomedPhoto.id)} alt="" style={{ maxWidth: "100vw", maxHeight: "100vh", objectFit: "contain" }} />
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: `repeat(${gridCols}, 1fr)`, gridAutoRows: "1fr", gap: 8, height: "100%" }}>
          {group.photos.map((photo, idx) => (
            <PhotoCard
              key={photo.id}
              photo={photo}
              isFocused={idx === focusedIdx}
              onRate={(s) => rate(photo.id, s)}
              onToggle={(t) => rate(photo.id, undefined, t)}
              onZoom={() => setZoomedPhoto(photo)}
              onFocus={() => setFocusedIdx(idx)}
              ref={(el) => { cardRefs.current[idx] = el; }}
            />
          ))}
        </div>
      </div>

      <ShortcutBar>
        <K>1-5</K> Rate <K>0</K> Clear <K>X</K> Reject <K>F</K> Fave <K>R</K> Blur <K>Arrows</K> Move <K>Space</K> Zoom <K>Back</K> Prev <K>Enter</K> {isLast ? "→ Tournament" : "Next"}
      </ShortcutBar>
    </div>
  );
}

function ShortcutBar({ children }: { children: React.ReactNode }) {
  return <div style={{ padding: "6px 8px", background: "#1a1a1a", borderTop: "1px solid #333", fontSize: "12px", color: "#666", display: "flex", gap: 14, flexShrink: 0, flexWrap: "wrap" }}>{children}</div>;
}

function K({ children }: { children: React.ReactNode }) {
  return <span><b style={{ color: "#aaa" }}>{children}</b></span>;
}

const navBtn: React.CSSProperties = {
  padding: "6px 14px", background: "#333", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "13px",
};
