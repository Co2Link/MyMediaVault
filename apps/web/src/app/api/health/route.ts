import { getEnv } from "@/lib/env";

export function GET() {
  return Response.json({
    status: "ok",
    commit: getEnv().commitSha,
  });
}
