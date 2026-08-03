import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../apiClient";
import type { Group } from "../api";

/**
 * Keyboard/Gamepad controller. Polls gamepads in a rAF loop and maps both
 * keyboard and gamepad input onto the same action dispatch.
 */
export function useController(onAction: (action: string) => void) {
  const onActionRef = useRef(onAction);
  onActionRef.current = onAction;

  useEffect(() => {
    const keyMap: Record<string, string> = {
      "1": "rate1",
      "2": "rate2",
      "3": "rate3",
      "4": "rate4",
      "5": "rate5",
      x: "blur",
      X: "blur",
      f: "favorite",
      F: "favorite",
      r: "reject",
      R: "reject",
      ArrowLeft: "prev",
      ArrowRight: "next",
      " ": "zoom",
      Enter: "next",
    };
    const onKey = (e: KeyboardEvent) => {
      const action = keyMap[e.key];
      if (action) {
        e.preventDefault();
        onActionRef.current(action);
      }
    };
    window.addEventListener("keydown", onKey);

    let raf = 0;
    let lastButtons: boolean[] = [];
    const poll = () => {
      const pads = navigator.getGamepads ? navigator.getGamepads() : [];
      const pad = [...pads].find((p) => p && p.connected);
      if (pad) {
        const a = pad.buttons[0]?.pressed;
        const b = pad.buttons[1]?.pressed;
        const xb = pad.buttons[2]?.pressed;
        const y = pad.buttons[3]?.pressed;
        if (a && !lastButtons[0]) onActionRef.current("rate5");
        if (b && !lastButtons[1]) onActionRef.current("favorite");
        if (xb && !lastButtons[2]) onActionRef.current("blur");
        if (y && !lastButtons[3]) onActionRef.current("reject");
        lastButtons = [a, b, xb, y];
        const stick = pad.axes[0] ?? 0;
        if (stick < -0.5) onActionRef.current("prev");
        if (stick > 0.5) onActionRef.current("next");
      }
      raf = requestAnimationFrame(poll);
    };
    raf = requestAnimationFrame(poll);
    return () => {
      window.removeEventListener("keydown", onKey);
      cancelAnimationFrame(raf);
    };
  }, []);
}

function RatingOverlay({ rating }: { rating: number }) {
  if (rating <= 0) return null;
  return <div className="absolute top-2 left-2 bg-black/70 rounded px-2 py-1 text-sm">{rating}★</div>;
}

function GroupCard({ group, index }: { group: Group; index: number }) {
  const [selected, setSelected] = useState<Record<number, string>>({});
  const [overlay, setOverlay] = useState<{ id: number; src: string } | null>(null);

  const zoom = useCallback((id: number) => {
    if (overlay?.id === id) {
      setOverlay(null);
      return;
    }
    setOverlay({ id, src: `/api/photo/${id}/full` });
  }, [overlay]);

  // Controller for this group's cards: rate/blur/fav/reject/zoom actions.
  useController((action) => {
    if (!group.photos.length) return;
    const card = group.photos[Math.min(index, group.photos.length - 1)];
    if (action === "rate1") applyRating(card.id, 1);
    if (action === "rate2") applyRating(card.id, 2);
    if (action === "rate3") applyRating(card.id, 3);
    if (action === "rate4") applyRating(card.id, 4);
    if (action === "rate5") applyRating(card.id, 5);
    if (action === "favorite") api.favorite(card.id, !selected[card.id]);
    if (action === "reject") api.reject(card.id, !selected[card.id]);
    if (action === "zoom") zoom(card.id);
    refreshSelection(card.id);
  });

  const applyRating = async (id: number, rating: number) => {
    await api.rate(id, rating);
  };

  const refreshSelection = async (id: number) => {
    const photo = group.photos.find((p) => p.id === id);
    if (photo) {
      setSelected((s) => ({ ...s, [id]: photo.favorite ? "fav" : photo.rejected ? "rej" : "" }));
    }
  };

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-2">
      <div className="text-xs text-neutral-500 mb-2">
        Group {index + 1} · {group.count} photos · {group.start_time?.slice(0, 16) ?? "unknown"}
      </div>
      <div className="grid grid-cols-2 gap-2">
        {group.photos.map((p) => (
          <div
            key={p.id}
            className="relative aspect-[4/3] bg-neutral-800 rounded overflow-hidden cursor-pointer"
            onClick={() => zoom(p.id)}
          >
            {p.has_thumb ? (
              <img
                src={`/api/photo/${p.id}/thumb`}
                alt={p.path}
                className="w-full h-full object-cover"
                loading="lazy"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-xs text-neutral-500">RAW</div>
            )}
            <RatingOverlay rating={p.rating} />
            {p.is_blurry && <div className="absolute top-2 right-2 text-amber-400 text-sm">⚠️</div>}
            {p.favorite && <div className="absolute bottom-2 left-2 text-yellow-300 text-xs">★</div>}
            {p.rejected && <div className="absolute bottom-2 right-2 bg-red-600 text-white text-xs px-1 rounded">✕</div>}
          </div>
        ))}
      </div>
      {overlay && (
        <div className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center" onClick={() => setOverlay(null)}>
          <img src={overlay.src} className="max-h-full max-w-full object-contain" />
        </div>
      )}
    </div>
  );
}

export function StageTwo({ onNext }: { onNext: () => void }) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.groups().then((g) => {
      setGroups(g);
      setLoading(false);
    });
  }, []);

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">Stage 2 — Group Review</h1>
        <button className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded" onClick={onNext}>
          Continue to Tournament →
        </button>
      </div>
      {loading ? (
        <p className="text-neutral-500">Loading groups…</p>
      ) : groups.length === 0 ? (
        <p className="text-neutral-500">No groups yet — run Stage 1 first.</p>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {groups.map((g, i) => (
            <GroupCard key={g.id} group={g} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
