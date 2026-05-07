export const metadataStatuses = ["pending", "processing", "succeeded", "failed"] as const;
export type MetadataStatus = (typeof metadataStatuses)[number];

export const jobStatuses = ["queued", "processing", "succeeded", "failed", "dead_lettered"] as const;
export type JobStatus = (typeof jobStatuses)[number];

export type TagRead = {
  id: string;
  name: string;
};

export type TorrentFileRead = {
  path: string;
  sizeBytes: number;
};

export type VideoSummary = {
  id: string;
  displayTitle: string | null;
  title: string | null;
  rating: number | null;
  infoHash: string;
  torrentName: string | null;
  metadataStatus: MetadataStatus;
  tags: TagRead[];
  createdAt: string;
  updatedAt: string;
};

export type VideoDetail = VideoSummary & {
  description: string | null;
  sizeBytes: number | null;
  metadataError: string | null;
  files: TorrentFileRead[];
};
