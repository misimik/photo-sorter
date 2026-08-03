import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../apiClient";
import type { PairPhoto } from "../api";

/**
 * Tournament (Stage 3): pick the better photo from each pair.
 * Preloads the next pair into hidden <img> tags for zero flicker.
 */
export function StageThree({ onNext }: { onNext: () => void }) {
  const [pair, setPair] = useState<PairPhoto[] | null>(null);
  const [done, setDone] = useState(false);
  const [state, setState] = useState({ total_votes: 0, votes_done: 0, rated_count: 0 });
  const [nextPair, setNextPair] = useState<PairPhoto[] | null>(null);
  const [zoomLeft, setZoomLeft] = useState(false);
  const [zoomRight, setZoomRight] = useState(false);

  const loadPair = useCallback(async () => {
    const res = await api.pair();
    if (res.done) {
      setDone(true);
      setPair(null);
      return;
    }
    setPair(res.photos);
    api.tournamentState().then(setState);
    // Preload the following pair in the background.
    api.pair().then((r) => setNextPair(r.done ? null : r.photos));
  }, []);

  const vote = useCallback(
    async (winnerId: number, loserId: number) => {
      await api.vote(winnerId, loserId);
      if (nextPair) {
        setPair(nextPair);
        setNextPair(null);
        api.tournamentState().then(setState);
        api.pair().then((r) => setNextPair(r.done ? null : r.photos));
      } else {
        await loadPair();
      }
    },
    [nextPair, loadPair]
  );

  useEffect(() => {
    api.tournamentState().then((s) => {
      setState(s);
      if (s.total_votes === 0) {
        api.tournamentStart().then(() => loadPair());
      } else {
        loadPair();
      }
    });
  }, [loadPair]);

  useControllerAction({
    ArrowLeft: () => pair && vote(pair[0].id, pair[1].id),
    ArrowRight: () => pair && vote(pair[1].id, pair[0].id),
    " ": () => {
      setZoomLeft((z) => !z);
      setZoomRight(false);
    },
  });

  const pct = state.total_votes > 0 ? Math.round((state.votes_done / state.total_votes) * 100) : 0;

  if (done) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-4">
        <h1 className="text-3xl font-semibold">Tournament complete!</h1>
        <button className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 rounded" onClick={onNext}>
          Continue to Export →
        </button>
      </div>
    );
  }

  if (!pair) return <div className="h-full flex items-center justify-center text-neutral-500">Loading…</div>;

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center gap-4 mb-4">
        <div className="flex-1 h-2 bg-neutral-800 rounded overflow-hidden">
          <div className="h-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <span className="text-xs text-neutral-400">
          {state.votes_done}/{state.total_votes} votes
        </span>
      </div>

      <div className="flex-1 grid grid-cols-2 gap-4 min-h-0">
        {pair.map((p, i) => (
          <button
            key={p.id}
            className="relative bg-neutral-900 rounded overflow-hidden focus:outline-none"
            onClick={() => vote(i === 0 ? pair[0].id : pair[1].id, i === 0 ? pair[1].id : pair[0].id)}
          >
            <img
              src={p.has_thumb ? `/api/photo/${p.id}/thumb` : `/api/photo/${p.id}/full`}
              alt={p.path}
              className="w-full h-full object-contain"
            />
            <span className="absolute bottom-2 left-2 bg-black/70 rounded px-2 py-0.5 text-xs">
              ELO {p.elo}
            </span>
          </button>
        ))}
      </div>

      {/* Hidden preload for the next pair */}
      {nextPair?.map((p) => (
        <img key={p.id} src={`/api/photo/${p.id}/thumb`} className="hidden" />
      ))}

      {zoomLeft && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center" onClick={() => setZoomLeft(false)}>
          <img src={`/api/photo/${pair[0].id}/full`} className="max-h-full max-w-full object-contain" />
        </div>
      )}
      {zoomRight && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center" onClick={() => setZoomRight(false)}>
          <img src={`/api/photo/${pair[1].id}/full`} className="max-h-full max-w-full object-contain" />
        </div>
      )}
    </div>
  );
}

/** Minimal keyboard/gamepad hook for the tournament screen. */
function useControllerAction(actions: Record<string, () => void>) {
  const ref = useRef(actions);
  ref.current = actions;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const fn = ref.current[e.key];
      if (fn) {
        e.preventDefault();
        fn();
      }
    };
    window.addEventListener("keydown", onKey);

    let raf = 0;
    let last: boolean[] = [];
    const poll = () => {
      const pads = navigator.getGamepads ? navigator.getGamepads() : [];
      const pad = [...pads].find((p) => p && p.connected);
      if (pad) {
        const a = pad.buttons[0]?.pressed;
        if (a && !last[0]) ref.current.ArrowLeft?.();
        const b = pad.buttons[1]?.pressed;
        if (b && !last[1]) ref.current.ArrowRight?.();
        last = [a, b];
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
