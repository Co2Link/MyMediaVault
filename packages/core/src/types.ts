export const metadataStatuses = ["pending", "processing", "succeeded", "failed"] as const;
export type MetadataStatus = (typeof metadataStatuses)[number];

export const previewStatuses = ["pending", "processing", "succeeded", "partial", "failed"] as const;
export type PreviewStatus = (typeof previewStatuses)[number];

export const jobStatuses = ["queued", "processing", "succeeded", "failed"] as const;
export type JobStatus = (typeof jobStatuses)[number];

export type TagRead = {
  id: string;
  name: string;
};

export type ActorRead = {
  id: string;
  name: string;
  description: string | null;
  hasProfileImage: boolean;
  createdAt: string;
  updatedAt: string;
};

export type TorrentFileRead = {
  path: string;
  sizeBytes: number;
};

export type PreviewFrameRead = {
  key: string;
  width: number;
  height: number;
  timestampSeconds: number;
  score: number;
  metadata: Record<string, string>;
};

export type PreviewSheetRead = {
  key: string;
  width: number;
  height: number;
  mimeType: string;
  metadata: Record<string, string>;
};

export type PreviewDiagnosticsRead = {
  artifactVersion: string | null;
  artifactFingerprint: string | null;
  downloadedBytes: number | null;
  elapsedSeconds: number | null;
  attempts: number | null;
  strategyName: string | null;
  selectedFilePath: string | null;
  selectedFileSizeBytes: number | null;
  failureReason: string | null;
  warnings: string[];
  details: Record<string, unknown>;
};

export type PreviewRead = {
  status: PreviewStatus;
  error: string | null;
  attempts: number;
  lastAttemptAt: string | null;
  updatedAt: string | null;
  frames: PreviewFrameRead[];
  sheet: PreviewSheetRead | null;
  diagnostics: PreviewDiagnosticsRead;
};

export type VideoSummary = {
  id: string;
  displayTitle: string | null;
  title: string | null;
  rating: number | null;
  infoHash: string;
  torrentName: string | null;
  metadataStatus: MetadataStatus;
  preview: PreviewRead;
  tags: TagRead[];
  actors: ActorRead[];
  createdAt: string;
  updatedAt: string;
};

export type TorrentSummary = {
  id: string;
  infoHash: string;
  name: string | null;
  sizeBytes: number | null;
  metadataStatus: MetadataStatus;
  metadataError: string | null;
  preview: PreviewRead;
  videoCount: number;
  createdAt: string;
  updatedAt: string;
};

export type VideoDetail = VideoSummary & {
  description: string | null;
  sizeBytes: number | null;
  metadataError: string | null;
  files: TorrentFileRead[];
};
