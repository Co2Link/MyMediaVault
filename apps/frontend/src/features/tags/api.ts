import { apiRequest } from "../../shared/api/client";
import { getTestAuthHeaders } from "../auth/testMode";

export type Tag = {
  id: string;
  name: string;
};

const adminHeaders = () => getTestAuthHeaders();

export function listTags() {
  return apiRequest<Tag[]>("/admin/tags", { headers: adminHeaders() });
}

export function createTag(name: string) {
  return apiRequest<Tag>("/admin/tags", { method: "POST", body: { name }, headers: adminHeaders() });
}

export function updateTag(id: string, name: string) {
  return apiRequest<Tag>(`/admin/tags/${id}`, { method: "PATCH", body: { name }, headers: adminHeaders() });
}

export function deleteTag(id: string) {
  return apiRequest<void>(`/admin/tags/${id}`, { method: "DELETE", headers: adminHeaders() });
}
