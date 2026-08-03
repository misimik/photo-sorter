import { useEffect, useState } from "react";
import { api, subscribeProgress } from "./apiClient";
import type { ProgressState } from "./api";
import { StageOne } from "./stages/StageOne";
import { StageTwo } from "./stages/StageTwo";
import { StageThree } from "./stages/StageThree";
import { StageFour } from "./stages/StageFour";

type Stage = 0 | 1 | 2 | 3 | 4;

export default function App() {
  const [stage, setStage] = useState<Stage>(0);
  const [progress, setProgress] = useState<ProgressState | null>(null);

  useEffect(() => subscribeProgress(setProgress), []);

  // Derive the current stage from persisted progress so a refresh resumes.
  useEffect(() => {
    if (progress) {
      const { scan, analyze, group } = progress.stages;
      if (scan.status !== "done") setStage(0);
      else if (analyze.status !== "done") setStage(1);
      else if (group.status !== "done") setStage(2);
      else setStage(3);
    }
  }, [progress]);

  const runStage = async (action: () => Promise<unknown>, target: Stage) => {
    await action();
    setStage(target);
  };

  return (
    <div className="h-screen w-screen overflow-hidden bg-neutral-950 text-neutral-100 flex flex-col">
      <header className="flex items-center justify-between px-4 py-2 border-b border-neutral-800 text-sm">
        <span className="font-semibold tracking-wide">PHOTO SORTER</span>
        <nav className="flex gap-2">
          {(["Stage 1: Scan", "Stage 2: Review", "Stage 3: Tournament", "Stage 4: Export"] as const).map(
            (label, i) => (
              <button
                key={label}
                className={`px-2 py-1 rounded ${stage === i ? "bg-neutral-700" : "hover:bg-neutral-800"}`}
                onClick={() => setStage(i as Stage)}
              >
                {label}
              </button>
            )
          )}
        </nav>
      </header>

      <main className="flex-1 min-h-0">
        {stage === 0 && <StageOne onRunScan={() => runStage(() => api.scan(), 0)} onRunAnalyze={() => runStage(() => api.analyze(), 1)} onRunGroup={() => runStage(() => api.group(), 2)} progress={progress} />}
        {stage === 1 && <StageTwo onNext={() => setStage(2)} />}
        {stage === 2 && <StageThree onNext={() => setStage(3)} />}
        {stage === 3 && <StageFour />}
      </main>
    </div>
  );
}
