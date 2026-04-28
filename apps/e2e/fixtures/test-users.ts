export const standardUser = {
  subject: "test-user-1",
  headers: {
    "X-Test-User": "test-user-1",
    "X-Test-Admin": "false",
  },
};

export const secondUser = {
  subject: "test-user-2",
  headers: {
    "X-Test-User": "test-user-2",
    "X-Test-Admin": "false",
  },
};

export const adminUser = {
  subject: "admin",
  headers: {
    "X-Test-User": "admin",
    "X-Test-Admin": "true",
  },
};
