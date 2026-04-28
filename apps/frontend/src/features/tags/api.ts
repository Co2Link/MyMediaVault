import { apiRequest } from "../../shared/api/client";

export type Tag = {
  id: string;
  name: string;
};

export function listTags() {
  return apiRequest<Tag[]>("/admin/tags");
}

export function createTag(name: string) {
  return apiRequest<Tag>("/admin/tags", { method: "POST", body: { name } });
}

export function updateTag(id: string, name: string) {
  return apiRequest<Tag>(`/admin/tags/${id}`, { method: "PATCH", body: { name } });
}

export function deleteTag(id: string) {
  return apiRequest<void>(`/admin/tags/${id}`, { method: "DELETE" });
}
