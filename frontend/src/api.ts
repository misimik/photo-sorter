export interface PhotoMeta {
  id: number;
  path: string;
  rating: number;
  favorite: boolean;
  rejected: boolean;
  is_blurry: boolean | null;
  has_thumb: boolean;
  has_raw: boolean;
}

export interface Group {
  id: number;
  start_time: string | null;
  count: number;
  photos: PhotoMeta[];
}

export interface StageProgress {
  total: number;
  processed: number;
  status: "idle" | "running" | "done" | "error";
  error: string | null;
}

export interface ProgressState {
  stages: Record<"scan" | "analyze" | "group" | "export", StageProgress>;
}

export interface PairPhoto {
  id: number;
  path: string;
  elo: number;
  views: number;
  has_thumb: boolean;
}

export interface PairResponse {
  done: boolean;
  photos: PairPhoto[];
}

export interface TournamentState {
  total_votes: number;
  votes_done: number;
  rated_count: number;
  max_views: number;
}

export interface ExportPreview {
  jpg_count: number;
  raw_count: number;
  total: number;
}
