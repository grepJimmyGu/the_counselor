import { auth } from "@/auth";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export default auth((req: NextRequest & { auth: unknown }) => {
  const isAuthenticated = !!(req as { auth?: { user?: unknown } }).auth?.user;
  const { pathname } = req.nextUrl;

  // Protected routes — require sign-in
  // /community is intentionally PUBLIC (trending board + public strategies are read-only)
  // Only /profile and /watchlist require authentication
  const isProtectedRoute =
    pathname.startsWith("/profile") ||
    pathname.startsWith("/watchlist");

  if (isProtectedRoute && !isAuthenticated) {
    const signInUrl = new URL("/auth/signin", req.url);
    // Only allow same-origin relative paths as callbackUrl (no external redirects)
    if (pathname.startsWith("/")) {
      signInUrl.searchParams.set("callbackUrl", pathname);
    }
    return NextResponse.redirect(signInUrl);
  }
});

export const config = {
  matcher: [
    "/profile/:path*",
    "/watchlist/:path*",
    // Exclude API routes, static files, and _next internals
    "/((?!api|_next/static|_next/image|favicon.ico).*)",
  ],
};
