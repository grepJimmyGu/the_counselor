import { describe, expect, it } from "vitest";

import {
  BACKEND_TOKEN_REFRESH_RETRY_SECONDS,
  BACKEND_TOKEN_REFRESH_WINDOW_SECONDS,
  backendTokenNeedsRefresh,
  canAttemptBackendTokenRefresh,
  readJwtExp,
} from "../backend-token";

/**
 * Regression cover for the 2026-08-07 "Couldn't rank by return (Invalid or
 * expired session token.)" bug.
 *
 * `auth.ts` used to re-mint `backendToken` only when it was MISSING. An expired
 * token is still a truthy string, so it slipped through and every sign-in-gated
 * endpoint 401'd for a user NextAuth still reported as authenticated. The case
 * that must never regress is `backendTokenNeedsRefresh(<expired token>) === true`.
 */

const NOW = 1_770_000_000; // fixed clock — no wall-clock flake

/** Builds an unsigned JWT with the given `exp`; only the payload is inspected. */
function tokenWithExp(exp: number | null): string {
  const b64url = (o: unknown) =>
    Buffer.from(JSON.stringify(o)).toString("base64url");
  const payload = exp === null ? { sub: "u1" } : { sub: "u1", exp };
  return `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url(payload)}.sig`;
}

describe("readJwtExp", () => {
  it("reads the exp claim", () => {
    expect(readJwtExp(tokenWithExp(NOW + 500))).toBe(NOW + 500);
  });

  it("returns null when the token has no exp", () => {
    expect(readJwtExp(tokenWithExp(null))).toBeNull();
  });

  it("returns null for a malformed token instead of throwing", () => {
    expect(readJwtExp("not-a-jwt")).toBeNull();
    expect(readJwtExp("a.!!!not-base64!!!.c")).toBeNull();
    expect(readJwtExp("")).toBeNull();
  });

  it("decodes base64url payloads without Buffer (edge-safe)", () => {
    // auth.ts is bundled into Edge middleware, where Buffer does not exist.
    // A payload whose base64 contains '-'/'_' and needs padding must still decode.
    const exp = readJwtExp(tokenWithExp(NOW + 12_345));
    expect(exp).toBe(NOW + 12_345);
  });
});

describe("backendTokenNeedsRefresh", () => {
  it("THE BUG: an expired-but-present token needs refresh", () => {
    // Before the fix this returned false (the token was truthy) and the user
    // was left holding a token the API rejected with 401.
    const expired = tokenWithExp(NOW - 60);
    expect(expired).toBeTruthy();
    expect(backendTokenNeedsRefresh(expired, NOW)).toBe(true);
  });

  it("does not refresh a healthy token", () => {
    const fresh = tokenWithExp(NOW + 30 * 24 * 60 * 60);
    expect(backendTokenNeedsRefresh(fresh, NOW)).toBe(false);
  });

  it("refreshes inside the window, before the token actually expires", () => {
    const nearly = tokenWithExp(NOW + BACKEND_TOKEN_REFRESH_WINDOW_SECONDS - 60);
    expect(backendTokenNeedsRefresh(nearly, NOW)).toBe(true);
  });

  it("does not refresh just outside the window", () => {
    const outside = tokenWithExp(NOW + BACKEND_TOKEN_REFRESH_WINDOW_SECONDS + 60);
    expect(backendTokenNeedsRefresh(outside, NOW)).toBe(false);
  });

  it("still refreshes a missing token (the original self-heal case)", () => {
    expect(backendTokenNeedsRefresh(undefined, NOW)).toBe(true);
    expect(backendTokenNeedsRefresh(null, NOW)).toBe(true);
    expect(backendTokenNeedsRefresh("", NOW)).toBe(true);
  });

  it("refreshes an unreadable token rather than trusting it", () => {
    expect(backendTokenNeedsRefresh("garbage", NOW)).toBe(true);
    expect(backendTokenNeedsRefresh(tokenWithExp(null), NOW)).toBe(true);
  });
});

describe("canAttemptBackendTokenRefresh", () => {
  it("allows the first attempt", () => {
    expect(canAttemptBackendTokenRefresh(undefined, NOW)).toBe(true);
    expect(canAttemptBackendTokenRefresh(null, NOW)).toBe(true);
  });

  it("blocks a retry inside the backoff window", () => {
    // auth.ts runs in Edge middleware matching nearly every route. Without this
    // guard, a failing refresh endpoint would draw one outbound fetch per page
    // navigation per signed-in user.
    expect(canAttemptBackendTokenRefresh(NOW - 30, NOW)).toBe(false);
  });

  it("allows a retry once the backoff has elapsed", () => {
    expect(
      canAttemptBackendTokenRefresh(NOW - BACKEND_TOKEN_REFRESH_RETRY_SECONDS - 1, NOW),
    ).toBe(true);
  });

  it("does not strand the session if the clock jumped backwards", () => {
    expect(canAttemptBackendTokenRefresh(NOW + 10_000, NOW)).toBe(true);
  });
});
