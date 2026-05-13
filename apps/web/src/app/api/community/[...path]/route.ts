/**
 * Community BFF catch-all — handles all /api/community/* writes.
 * Verifies the Auth.js session, then forwards to FastAPI with X-Internal-Key.
 */
import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const BACKEND = process.env.INTERNAL_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const KEY = process.env.INTERNAL_API_KEY ?? "";

async function handler(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }
  if (!KEY) {
    return NextResponse.json({ error: "INTERNAL_API_KEY not configured" }, { status: 503 });
  }

  // Strip /api/community prefix to get the FastAPI sub-path
  const url = new URL(req.url);
  const subPath = url.pathname.replace(/^\/api\/community/, "");
  const targetUrl = `${BACKEND}/api/community${subPath}${url.search}`;

  // Forward with user_id injected as query param for FastAPI endpoints that need it
  const targetWithUser = targetUrl.includes("user_id")
    ? targetUrl
    : targetUrl + (url.search ? `&user_id=${session.user.id}` : `?user_id=${session.user.id}`);

  const body = req.method !== "GET" && req.method !== "DELETE"
    ? await req.text()
    : undefined;

  const res = await fetch(targetWithUser, {
    method: req.method,
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Key": KEY,
    },
    body,
  });

  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}

export const GET = handler;
export const POST = handler;
export const DELETE = handler;
