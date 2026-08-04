import { useRef, useCallback } from "react";
import { updateRating } from "../api";

interface QueuedRating {
  photoId: number;
  stars?: number;
  is_rejected?: number;
  is_favorite?: number;
  user_blurry_override?: number;
}

export function useRatingQueue() {
  const queueRef = useRef<QueuedRating[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flush = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const batch = queueRef.current.splice(0);
    for (const r of batch) {
      updateRating(r.photoId, {
        stars: r.stars,
        is_rejected: r.is_rejected,
        is_favorite: r.is_favorite,
        user_blurry_override: r.user_blurry_override,
      }).catch(() => {});
    }
  }, []);

  const enqueue = useCallback((rating: QueuedRating) => {
    const existing = queueRef.current.findIndex((r) => r.photoId === rating.photoId);
    if (existing >= 0) {
      queueRef.current[existing] = { ...queueRef.current[existing], ...rating };
    } else {
      queueRef.current.push(rating);
    }

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(flush, 100);
  }, [flush]);

  return { enqueue, flush };
}
