import { getAppEnv } from "@/lib/env";

export function GET() {
  return Response.json({
    status: "ok",
    commit: getAppEnv().commitSha,
  });
}
