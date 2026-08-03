import type { ExportPreview, Group, PairResponse, ProgressState, TournamentState } from "./api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    throw new Error(`${path}: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  scan: () => req<{ total: number; new: number; pairs: number }>("/api/scan"),
  analyze: () => req<{ status: string }>("/api/analyze"),
  group: () => req<{ status: string; groups: number }>("/api/group"),
  progress: () => req<ProgressState>("/api/progress"),
  groups: (offset = 0) => req<Group[]>(`/api/groups?offset=${offset}`),
  pair: () => req<PairResponse>("/api/tournament/pair"),
  vote: (winnerId: number, loserId: number) =>
    req<{ ok: boolean }>(`/api/tournament/vote?winner_id=${winnerId}&loser_id=${loserId}`, { method: "POST" }),
  tournamentStart: () => req<{ status: string; total_votes: number }>("/api/tournament/start", { method: "POST" }),
  tournamentState: () => req<TournamentState>("/api/tournament/state"),
  exportPreview: (fraction: number) => req<ExportPreview>(`/api/export/preview?fraction=${fraction}`),
  exportStart: (fraction: number) =>
    req<{ status: string; job_id: number }>(`/api/export?fraction=${fraction}`, { method: "POST" }),
  rate: (id: number, rating: number) =>
    req<{ ok: boolean }>(`/api/photo/${id}/rate?rating=${rating}`, { method: "POST" }),
  favorite: (id: number, favorite: boolean) =>
    req<{ ok: boolean }>(`/api/photo/${id}/favorite?favorite=${favorite}`, { method: "POST" }),
  reject: (id: number, rejected: boolean) =>
    req<{ ok: boolean }>(`/api/photo/${id}/reject?rejected=${rejected}`, { method: "POST" }),
};

export function subscribeProgress(onEvent: (state: ProgressState) => void): () => void {
  const es = new EventSource("/api/events");
  es.addEventListener("progress", (e) => {
    try {
      onEvent(JSON.parse((e as MessageEvent).data) as ProgressState);
    } catch {
      /* ignore malformed frames */
    }
  });
  es.onerror = () => {
    // EventSource auto-reconnects; nothing to do.
  };
  return () => es.close();
}
