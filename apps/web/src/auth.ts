import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";

const API_BASE =
  process.env.INTERNAL_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
    Credentials({
      id: "credentials",
      name: "Email",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;
        try {
          const res = await fetch(`${API_BASE}/api/auth/password/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: credentials.email,
              password: credentials.password,
            }),
          });
          if (!res.ok) return null;
          const data = await res.json();
          return {
            id: data.user.id,
            email: credentials.email as string,
            name: data.user.display_name ?? null,
            image: data.user.avatar_url ?? null,
            sessionToken: data.session_token,
          };
        } catch {
          return null;
        }
      },
    }),
  ],

  callbacks: {
    async jwt({ token, user, account }) {
      // Self-healing branch — runs on every request when the token is
      // missing backendToken but we know this was a Google login. Lets
      // existing sessions (minted before sync-user wired its token) recover
      // on their next request instead of having to log out and back in.
      // Only fires once because once backendToken is set, the condition is
      // false. We use token.email (a NextAuth standard claim) as the key.
      // Drop the `token.provider === "google"` precondition that the
      // original version had. Some pre-fix JWTs were minted without a
      // `provider` claim, leaving them unhealable. Credentials users
      // always have backendToken set at login, so "missing backendToken +
      // has email" reliably identifies a Google JWT that needs healing.
      if (
        !account &&
        !user &&
        !token.backendToken &&
        token.email
      ) {
        const internalKey = process.env.INTERNAL_API_KEY;
        if (!internalKey || !API_BASE) {
          // Surfacing this in Vercel server logs so we don't silently
          // strand users with an unhealable JWT. INTERNAL_API_KEY +
          // INTERNAL_API_BASE_URL (or NEXT_PUBLIC_API_BASE_URL) must be
          // set in Vercel env vars for self-healing to work.
          console.warn(
            "[auth] self-heal skipped: missing env",
            { hasInternalKey: !!internalKey, hasApiBase: !!API_BASE, email: token.email },
          );
        } else {
          try {
            const res = await fetch(`${API_BASE}/api/auth/sync-user`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-Internal-Key": internalKey,
              },
              body: JSON.stringify({
                email: token.email,
                display_name: token.displayName ?? token.name ?? null,
                avatar_url: token.avatarUrl ?? token.picture ?? null,
                provider: "google",
                // We may have lost the original providerAccountId by now;
                // sync-user is keyed by email anyway and will resolve to
                // the existing backend user row.
                provider_user_id: (token.providerUserId as string) ?? "",
              }),
            });
            if (res.ok) {
              const data = await res.json();
              token.providerUserId = data.id;
              token.backendToken = data.session_token ?? null;
              if (!data.session_token) {
                console.warn(
                  "[auth] self-heal got 200 but session_token was null",
                  { email: token.email, dataKeys: Object.keys(data) },
                );
              }
            } else {
              console.warn(
                "[auth] self-heal sync-user non-ok",
                { status: res.status, email: token.email },
              );
            }
          } catch (err) {
            console.warn(
              "[auth] self-heal sync-user threw",
              { email: token.email, error: String(err) },
            );
          }
        }
      }

      if (account && user) {
        token.provider = account.provider;
        token.avatarUrl = user.image ?? null;
        token.displayName = user.name ?? null;

        // Credentials flow — backend already minted a session token during
        // authorize(); pass it through.
        if (user.sessionToken) {
          token.providerUserId = user.id;
          token.backendToken = user.sessionToken;
        }

        // Google flow — exchange the OAuth identity for a backend user row
        // and a session token via /api/auth/sync-user. Without this step the
        // workspace + other authed endpoints see backendToken=null and 401.
        // We do this here (not in signIn) so the token is persisted in the
        // JWT cookie; signIn callbacks can't mutate the token.
        if (account.provider === "google") {
          const internalKey = process.env.INTERNAL_API_KEY;
          let synced = false;
          if (internalKey && API_BASE && user.email) {
            try {
              const res = await fetch(`${API_BASE}/api/auth/sync-user`, {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "X-Internal-Key": internalKey,
                },
                body: JSON.stringify({
                  email: user.email,
                  display_name: user.name ?? null,
                  avatar_url: user.image ?? null,
                  provider: "google",
                  provider_user_id: account.providerAccountId ?? user.id,
                }),
              });
              if (res.ok) {
                const data = await res.json();
                // Use the backend's user id (deterministic across logins),
                // not Google's providerAccountId.
                token.providerUserId = data.id;
                token.backendToken = data.session_token ?? null;
                synced = true;
              }
            } catch {
              // Swallowed — sync failure must not block sign-in.
            }
          }
          if (!synced) {
            // Fallback so downstream code still has *some* user id, even if
            // sync-user couldn't run (e.g. missing env). backendToken stays
            // null and authed routes will continue to 401 — which is the
            // right signal that the platform is misconfigured.
            token.providerUserId = account.providerAccountId ?? user.id;
          }
        }
      }
      return token;
    },

    async session({ session, token }) {
      session.user.id = token.providerUserId ?? session.user.id;
      session.user.provider = token.provider;
      session.user.avatarUrl = token.avatarUrl ?? null;
      session.backendToken = token.backendToken ?? null;
      return session;
    },
  },

  pages: {
    signIn: "/login",
    error: "/auth/error",
  },
});

// ── Type augmentation ─────────────────────────────────────────────────────────

declare module "next-auth" {
  interface Session {
    backendToken?: string | null;
    user: {
      id: string;
      name?: string | null;
      email?: string | null;
      image?: string | null;
      provider?: string;
      avatarUrl?: string | null;
    };
  }

  interface User {
    sessionToken?: string;
  }
}

declare module "@auth/core/jwt" {
  interface JWT {
    providerUserId?: string;
    provider?: string;
    avatarUrl?: string | null;
    displayName?: string | null;
    backendToken?: string | null;
  }
}

