import { useEffect, useState } from "react";
import { api } from "../apiClient";
import type { ExportPreview } from "../api";

export function StageFour() {
  const [fraction, setFraction] = useState(0.3);
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    api.exportPreview(fraction).then(setPreview);
  }, [fraction]);

  const startExport = async () => {
    setExporting(true);
    await api.exportStart(fraction);
  };

  return (
    <div className="p-8 max-w-xl mx-auto">
      <h1 className="text-2xl font-semibold mb-6">Stage 4 — Rankings & Export</h1>

      <label className="block text-sm text-neutral-400 mb-2">Top fraction</label>
      <input
        type="range"
        min={0.05}
        max={1}
        step={0.05}
        value={fraction}
        onChange={(e) => setFraction(Number(e.target.value))}
        className="w-full accent-emerald-500"
      />
      <p className="text-sm mt-2 text-neutral-300">
        {Math.round(fraction * 100)}% —{" "}
        {preview
          ? `Selecting ${preview.jpg_count} JPGs + ${preview.raw_count} ARWs (${preview.total} files)`
          : "…"}
      </p>

      <button
        className="mt-6 px-6 py-3 bg-emerald-600 hover:bg-emerald-500 rounded disabled:opacity-50"
        onClick={startExport}
        disabled={exporting}
      >
        {exporting ? "Export running…" : "Start export"}
      </button>
      <p className="text-xs text-neutral-500 mt-4">
        Non-destructive: files are copied to /export with a manifest.txt. Existing files are skipped, so a failed
        export resumes cleanly. Progress appears on the Stage 1 bar (export stage).
      </p>
    </div>
  );
}
