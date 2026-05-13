import { auth } from "@/auth";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export default auth((req: NextRequest & { auth: unknown }) => {
  const isAuthenticated = !!(req as { auth?: { user?: unknown } }).auth?.user;
  const path = req.nextUrl.pathname;

  // Protected routes — require sign-in
  const isProtectedRoute =
    path.startsWith("/profile") ||
    path.startsWith("/watchlist") ||
    path.startsWith("/community");

  if (isProtectedRoute && !isAuthenticated) {
    const signInUrl = new URL("/auth/signin", req.url);
    signInUrl.searchParams.set("callbackUrl", path);
    return NextResponse.redirect(signInUrl);
  }
});

export const config = {
  matcher: [
    "/profile/:path*",
    "/watchlist/:path*",
    "/community/:path*",
    // Exclude API routes, static files, and _next internals
    "/((?!api|_next/static|_next/image|favicon.ico).*)",
  ],
};
