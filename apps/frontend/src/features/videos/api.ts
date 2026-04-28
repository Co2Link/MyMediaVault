import { apiRequest } from "../../shared/api/client";

export type MetadataStatus = "pending" | "processing" | "succeeded" | "failed";

export type Tag = {
  id: string;
  name: string;
};

export type VideoSummary = {
  id: string;
  displayTitle: string | null;
  title: string | null;
  rating: number | null;
  infoHash: string;
  torrentName: string | null;
  metadataStatus: MetadataStatus;
  tags: Tag[];
  createdAt: string;
  updatedAt: string;
};

export type VideoDetail = VideoSummary & {
  description: string | null;
  sizeBytes: number | null;
  metadataError: string | null;
  files: Array<{ path: string; sizeBytes: number }>;
};

export type VideoListResponse = {
  items: VideoSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type CreateVideoInput = {
  infoHash: string;
  title?: string;
  description?: string;
  rating?: number;
  tagIds?: string[];
};

export function createVideo(input: CreateVideoInput) {
  return apiRequest<VideoDetail>("/videos", { method: "POST", body: input });
}

export function searchVideos(params: { q?: string; tag?: string; rating?: string }) {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.tag) search.set("tag", params.tag);
  if (params.rating) search.set("rating", params.rating);
  return apiRequest<VideoListResponse>(`/videos?${search.toString()}`);
}

export function getVideo(videoId: string) {
  return apiRequest<VideoDetail>(`/videos/${videoId}`);
}
