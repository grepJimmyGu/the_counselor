/**
 * Expiry inspection for the backend-minted session JWT (`session.backendToken`).
 *
 * Why this exists — the 2026-08-07 "Couldn't rank by return" bug:
 *
 * The backend mints session tokens with a 30-day expiry
 * (`auth_service._TOKEN_EXPIRE_DAYS`), once, at sign-in. NextAuth re-signs its
 * OWN session cookie with a fresh 30-day expiry on every session read (see
 * @auth/core `lib/actions/session.js` — "Refresh JWT expiry by re-signing it,
 * with an updated expiry date"), and that re-sign copies `backendToken`
 * through verbatim. So an active user's NextAuth session rolls forward forever
 * while the backend token quietly ages out underneath it.
 *
 * The `auth.ts` self-heal only fired on a *missing* `backendToken`. An expired
 * one is still a truthy string, so nothing ever re-minted it: past day 30 the
 * user was `status === "authenticated"` holding a token every sign-in-gated
 * endpoint rejected with 401 "Invalid or expired session token."
 *
 * Lives in its own module rather than inside `auth.ts` for two reasons: it is
 * unit-testable without booting NextAuth, and `auth.ts` is pulled into Edge
 * middleware — hence `atob` rather than `Buffer`, which Edge does not provide.
 */

/** Re-mint once the token is within this long of its `exp`. */
export const BACKEND_TOKEN_REFRESH_WINDOW_SECONDS = 24 * 60 * 60;

/**
 * Minimum gap between refresh ATTEMPTS for one session.
 *
 * Without this, a refresh endpoint that is failing (API down, INTERNAL_API_KEY
 * unset on Vercel) leaves the "needs refresh" condition permanently true, and
 * `auth.ts` runs inside Edge middleware that matches nearly every route — so
 * every page navigation by every signed-in user would fire another outbound
 * fetch at an API that is already unhealthy. The refresh window is a day wide,
 * so backing off for minutes costs nothing in the happy path.
 */
export const BACKEND_TOKEN_REFRESH_RETRY_SECONDS = 5 * 60;

/**
 * True when enough time has passed since the last refresh attempt to try again.
 * `lastAttemptSeconds` is undefined on a session that has never attempted one.
 */
export function canAttemptBackendTokenRefresh(
  lastAttemptSeconds: number | null | undefined,
  nowSeconds: number = Date.now() / 1000,
): boolean {
  if (typeof lastAttemptSeconds !== "number") return true;
  // A clock that jumped backwards must not lock the user out of refreshing.
  if (lastAttemptSeconds > nowSeconds) return true;
  return nowSeconds - lastAttemptSeconds >= BACKEND_TOKEN_REFRESH_RETRY_SECONDS;
}

/** Decode a base64url segment. Edge-safe (no `Buffer`). */
function decodeBase64Url(segment: string): string {
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
  return atob(padded);
}

/**
 * `exp` (seconds since epoch) from a JWT, or null when it can't be read.
 *
 * The signature is deliberately NOT verified — the backend is the only
 * authority on validity. This answers "when should we refresh", nothing more,
 * so it never needs the signing secret.
 */
export function readJwtExp(token: string): number | null {
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    const exp = (JSON.parse(decodeBase64Url(payload)) as { exp?: unknown }).exp;
    return typeof exp === "number" ? exp : null;
  } catch {
    return null;
  }
}

/**
 * True when the stored backend token is missing, malformed, already expired, or
 * close enough to expiry that the next request could 401.
 *
 * Unreadable tokens return true: a token we can't inspect is one we can't
 * vouch for, and re-minting is cheap next to stranding the user.
 */
export function backendTokenNeedsRefresh(
  token: string | null | undefined,
  nowSeconds: number = Date.now() / 1000,
): boolean {
  if (!token) return true;
  const exp = readJwtExp(token);
  if (exp === null) return true;
  return exp - nowSeconds <= BACKEND_TOKEN_REFRESH_WINDOW_SECONDS;
}
