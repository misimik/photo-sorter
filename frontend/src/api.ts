const API_BASE = "/api";

// ---------------------------------------------------------------------------
// Types (current backend contract)
// ---------------------------------------------------------------------------

export interface ScanStatus {
  status: string;       // idle | running | done | error
  folder: string;
  message?: string;
}

export interface Photo {
  id: number;
  path: string;
  filename: string;
  folder: string;
  date_taken: string;
  width: number | null;
  height: number | null;
  dhash: string | null;
  sharpness: number | null;
  is_blurry: number | null;
  stars: number | null;
  is_rejected: number;
  is_favorite: number;
  user_blurry_override: number | null;
  rating: number;
  favorite: boolean;
  rejected: boolean;
  has_thumb: boolean;
  has_raw: boolean;
}

export interface Group {
  id: number;
  folder: string;
  name: string;
  start_time: string | null;
  count: number;
  photos: Photo[];
}

export interface GroupDetail {
  group: Group;
  photos: Photo[];
  group_index: number;
  total_groups: number;
}

export interface TournamentPair {
  status: string;
  pair: {
    photo_a: Photo & { elo: number; view_count: number };
    photo_b: Photo & { elo: number; view_count: number };
    total_photos: number;
    total_views: number;
    max_views: number;
  };
  stats?: TournamentStats;
}

export interface TournamentStats {
  total_photos: number;
  active_photos: number;
  total_views: number;
  max_views: number;
  total_matches: number;
  completed: boolean;
  standings: Array<{
    photo_id: number;
    current_elo: number;
    view_count: number;
    wins: number;
    losses: number;
    filename: string;
  }>;
}

export interface Ranking {
  photo_id: number;
  current_elo: number;
  view_count: number;
  wins: number;
  losses: number;
  filename: string;
  folder: string;
  stars: number | null;
  is_favorite: number;
  rank: number;
  total: number;
  tranche: number;
}

export interface ProgressStage {
  total: number;
  processed: number;
  status: string;
  folder: string;
  error: string | null;
}

export interface ProgressState {
  stages: Record<string, ProgressStage[]>;
}

// ---------------------------------------------------------------------------
// REST client
// ---------------------------------------------------------------------------

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, init);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export function getFolders(): Promise<string[]> {
  return req<{ folders: string[] }>("/folders").then((d) => d.folders);
}

export function startScan(folder?: string): Promise<{ status: string }> {
  const q = folder ? `?folder=${encodeURIComponent(folder)}` : "";
  return req(`/scan${q}`, { method: "POST" });
}

export function startAnalyze(folder?: string): Promise<{ status: string }> {
  const q = folder ? `?folder=${encodeURIComponent(folder)}` : "";
  return req(`/analyze${q}`, { method: "POST" });
}

export function startGroup(folder?: string): Promise<{ status: string }> {
  const q = folder ? `?folder=${encodeURIComponent(folder)}` : "";
  return req(`/group${q}`, { method: "POST" });
}

export function getProgress(): Promise<ProgressState> {
  return req<ProgressState>("/progress");
}

export async function getScanStatus(folder?: string): Promise<ScanStatus> {
  const p = await getProgress();
  const scan = p.stages["scan"]?.find((s) => s.folder === (folder || "")) ?? p.stages["scan"]?.[0];
  if (!scan) return { status: "idle", folder: folder || "" };
  return { status: scan.status, folder: scan.folder, message: `${scan.processed}/${scan.total}` };
}

export async function getStats(folder?: string): Promise<{
  total_photos: number; total_groups: number; rated: number; rejected: number; favorites: number;
}> {
  const q = folder ? `?folder=${encodeURIComponent(folder)}` : "";
  return req(`/stats${q}`);
}

export async function getGroups(folder?: string): Promise<Group[]> {
  const q = folder ? `?folder=${encodeURIComponent(folder)}` : "";
  // Fetch all groups (limit=5000); the review flow needs the full list.
  return req<Group[]>(`/groups${q}${folder ? "&" : "?"}limit=5000`);
}

export async function getGroup(id: number): Promise<GroupDetail> {
  const g = await req<Group>(`/groups/${id}`);
  return {
    group: g,
    photos: g.photos,
    group_index: 0,
    total_groups: 0,
  };
}

export async function updateRating(
  photoId: number,
  data: {
    stars?: number;
    is_rejected?: number;
    is_favorite?: number;
    user_blurry_override?: number;
  }
): Promise<void> {
  const p = data.stars !== undefined
    ? req(`/photo/${photoId}/rate?rating=${data.stars}`, { method: "POST" })
    : Promise.resolve();
  await p;
  if (data.is_rejected !== undefined) {
    await req(`/photo/${photoId}/reject?rejected=${data.is_rejected === 1}`, { method: "POST" });
  }
  if (data.is_favorite !== undefined) {
    await req(`/photo/${photoId}/favorite?favorite=${data.is_favorite === 1}`, { method: "POST" });
  }
}

export function thumbnailUrl(photoId: number): string {
  return `${API_BASE}/photo/${photoId}/thumb`;
}

export function previewUrl(photoId: number): string {
  return `${API_BASE}/photo/${photoId}/preview`;
}

export function fullUrl(photoId: number): string {
  return `${API_BASE}/photo/${photoId}/full`;
}

export async function initTournament(minStars = 3, folder?: string): Promise<{ status: string; photo_count?: number; message?: string }> {
  const q = new URLSearchParams();
  q.set("min_stars", String(minStars));
  if (folder) q.set("folder", folder);
  return req(`/tournament/start?${q.toString()}`, { method: "POST" });
}

export async function getNextPair(folder?: string, minStars = 3): Promise<TournamentPair> {
  const q = new URLSearchParams();
  if (folder) q.set("folder", folder);
  q.set("min_stars", String(minStars));
  const r = await req<{ done: boolean; photos: Array<{ id: number; path: string; elo: number; views: number; has_thumb: boolean }> }>(`/tournament/pair?${q.toString()}`);
  if (r.done || r.photos.length < 2) {
    return { status: "completed", pair: null as unknown as TournamentPair["pair"] };
  }
  const [a, b] = r.photos;
  return {
    status: "playing",
    pair: {
      photo_a: { ...(await getPhoto(a.id)), elo: a.elo, view_count: a.views },
      photo_b: { ...(await getPhoto(b.id)), elo: b.elo, view_count: b.views },
      total_photos: 0,
      total_views: 0,
      max_views: 4,
    },
  };
}

async function getPhoto(id: number): Promise<Photo> {
  const p = await req<Photo & { rating: number; favorite: boolean; rejected: boolean }>(`/photo/${id}`);
  return {
    ...p,
    filename: p.path.split("/").pop() || "",
    date_taken: "",
    width: null,
    height: null,
    dhash: null,
    sharpness: null,
    is_blurry: null,
    stars: p.rating || null,
    is_rejected: p.rejected ? 1 : 0,
    is_favorite: p.favorite ? 1 : 0,
    user_blurry_override: null,
    has_thumb: p.has_thumb !== false,
    has_raw: p.has_raw !== false,
  };
}

export async function submitVote(winnerId: number, loserId: number): Promise<void> {
  await req(`/tournament/vote?winner_id=${winnerId}&loser_id=${loserId}`, { method: "POST" });
}

export async function getTournamentStats(folder?: string, minStars = 3): Promise<TournamentStats> {
  const q = new URLSearchParams();
  if (folder) q.set("folder", folder);
  q.set("min_stars", String(minStars));
  const s = await req<{ total_votes: number; votes_done: number; rated_count: number; max_views: number }>(`/tournament/state?${q.toString()}`);
  return {
    total_photos: s.rated_count,
    active_photos: s.rated_count,
    total_views: s.votes_done,
    max_views: s.max_views,
    total_matches: Math.floor(s.votes_done / 2),
    completed: s.votes_done >= s.total_votes,
    standings: [],
  };
}

export async function getRankings(folder?: string): Promise<Ranking[]> {
  const q = folder ? `?folder=${encodeURIComponent(folder)}` : "";
  const rows = await req<Array<{ photo_id: number; elo: number; filename: string; folder: string; stars: number; is_favorite: boolean; tranche: number }>>(`/rankings${q}`);
  const total = rows.length;
  return rows.map((r, i) => ({
    ...r,
    current_elo: r.elo,
    view_count: 0,
    wins: 0,
    losses: 0,
    width: null,
    height: null,
    is_favorite: r.is_favorite ? 1 : 0,
    rank: i + 1,
    total,
  }));
}

export async function exportPhotos(cutoffTranche: number, folder?: string): Promise<{ exported: number; destination: string; message?: string }> {
  const q = new URLSearchParams();
  q.set("fraction", String(cutoffTranche / 10));
  if (folder) q.set("folder", folder);
  const r = await req<{ status: string; job_id: number }>(`/export?${q.toString()}`, { method: "POST" });
  return { exported: 0, destination: folder ? `Best/${folder}/` : "Best/", message: r.status };
}

export function subscribeProgress(onEvent: (state: ProgressState) => void): () => void {
  const es = new EventSource("/api/events");
  es.addEventListener("progress", (e) => {
    try {
      onEvent(JSON.parse((e as MessageEvent).data) as ProgressState);
    } catch {
      /* ignore malformed frames */
    }
  });
  es.onerror = () => { /* EventSource auto-reconnects */ };
  return () => es.close();
}
