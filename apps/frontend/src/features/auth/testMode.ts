export function setTestUser(subject: string, isAdmin = false) {
  localStorage.setItem("mmv.testUser", subject);
  localStorage.setItem("mmv.testAdmin", String(isAdmin));
}

export function getTestAuthHeaders(): Record<string, string> {
  return {
    "X-Test-User": localStorage.getItem("mmv.testUser") ?? "test-user-1",
    "X-Test-Admin": localStorage.getItem("mmv.testAdmin") ?? "false",
  };
}
