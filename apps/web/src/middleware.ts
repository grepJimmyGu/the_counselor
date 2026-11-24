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

// ONLY the routes this middleware protects — never a catch-all.
//
// Until 2026-11 this list ended with `/((?!api|_next/static|_next/image|favicon.ico).*)`,
// which ran the Auth.js wrapper on every page, every `<Link>` prefetch,
// robots.txt, sitemap.xml and every bot probe for a path that doesn't exist.
// One first-time visit to the (fully static) home page cost 27 middleware
// runs — 1 document + 26 prefetches — and Vercel paused the project for Fluid
// Active CPU. See docs/KNOWN_ISSUES.md (2026-11-11).
//
// Nothing else depends on this running everywhere: the backend-token refresh
// (apps/api/CLAUDE.md trap #23) lives in the `jwt` callback, which also runs
// on the `/api/auth/session` read every page load makes.
// `src/__tests__/vercel-compute-guards.test.ts` fails if a public path matches.
export const config = {
  matcher: ["/profile/:path*", "/watchlist/:path*"],
};
