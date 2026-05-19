/**
 * Community BFF catch-all — handles all /api/community/* writes.
 * Verifies the Auth.js session, then forwards to FastAPI with X-Internal-Key.
 */
import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const BACKEND =
  process.env.INTERNAL_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8001";
const KEY = process.env.INTERNAL_API_KEY ?? "";

function requiresSession(method: string, subPath: string) {
  return method !== "GET" || subPath === "/watchlist" || subPath.startsWith("/watchlist/");
}

function rewriteUserPath(subPath: string, userId: string) {
  const encodedUserId = encodeURIComponent(userId);
  const encodedSymbol = "([^/]+)";

  if (subPath === "/watchlist") {
    return `/watchlist/${encodedUserId}`;
  }

  const watchlistStatus = subPath.match(new RegExp(`^/watchlist/${encodedSymbol}/status$`));
  if (watchlistStatus) {
    return `/watchlist/${encodedUserId}/${watchlistStatus[1]}/status`;
  }

  const watchlistSymbol = subPath.match(new RegExp(`^/watchlist/${encodedSymbol}$`));
  if (watchlistSymbol) {
    return `/watchlist/${encodedUserId}/${watchlistSymbol[1]}`;
  }

  const vote = subPath.match(new RegExp(`^/vote/${encodedSymbol}$`));
  if (vote) {
    return `/vote/${encodedUserId}/${vote[1]}`;
  }

  return subPath;
}

async function handler(req: NextRequest) {
  const url = new URL(req.url);
  const subPath = url.pathname.replace(/^\/api\/community/, "");
  const needsSession = requiresSession(req.method, subPath);

  let userId: string | null = null;
  if (needsSession) {
    const session = await auth().catch(() => null);
    userId = session?.user?.id ?? null;
    if (!userId) {
      return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }
    if (!KEY) {
      return NextResponse.json({ error: "INTERNAL_API_KEY not configured" }, { status: 503 });
    }
  }

  if (!BACKEND) {
    return NextResponse.json({ error: "Community API backend is not configured" }, { status: 503 });
  }

  const backendPath = userId ? rewriteUserPath(subPath, userId) : subPath;
  const target = new URL(`${BACKEND.replace(/\/$/, "")}/api/community${backendPath}`);
  url.searchParams.forEach((value, key) => target.searchParams.append(key, value));

  if (userId && !target.searchParams.has("user_id") && backendPath === subPath) {
    target.searchParams.set("user_id", userId);
  }

  const body = req.method !== "GET" && req.method !== "DELETE"
    ? await req.text()
    : undefined;

  const res = await fetch(target, {
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
