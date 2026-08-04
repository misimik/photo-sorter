import { useState, useEffect } from "react";

export function useGridLayout(
  photoCount: number,
  containerRef: React.RefObject<HTMLDivElement | null>,
  targetAspect: number = 1.5
) {
  const [cols, setCols] = useState(1);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || photoCount === 0) return;

    const compute = () => {
      const { width: cw, height: ch } = el.getBoundingClientRect();
      if (cw === 0 || ch === 0) return;

      let bestCols = 1;
      let bestArea = -Infinity;

      for (let c = 1; c <= photoCount; c++) {
        const rows = Math.ceil(photoCount / c);
        const cellW = cw / c;
        const cellH = ch / rows;

        const photoW = Math.min(cellW, cellH * targetAspect);
        const photoH = Math.min(cellH, cellW / targetAspect);
        const area = photoW * photoH * photoCount;

        if (area > bestArea) {
          bestArea = area;
          bestCols = c;
        }
      }

      setCols(bestCols);
    };

    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(el);
    return () => ro.disconnect();
  }, [photoCount, containerRef, targetAspect]);

  return cols;
}
