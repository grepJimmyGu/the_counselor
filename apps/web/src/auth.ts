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
      if (account && user) {
        token.providerUserId = account.providerAccountId ?? user.id;
        token.provider = account.provider;
        token.avatarUrl = user.image ?? null;
        token.displayName = user.name ?? null;
        // Credentials flow: backend token already in user object
        if ((user as any).sessionToken) {
          token.backendToken = (user as any).sessionToken;
        }
      }
      return token;
    },

    async session({ session, token }) {
      session.user.id = token.providerUserId as string;
      session.user.provider = token.provider as string;
      session.user.avatarUrl = token.avatarUrl as string | null;
      (session as any).backendToken = token.backendToken ?? null;
      return session;
    },

    async signIn({ user, account }) {
      if (account?.provider === "google") {
        const internalKey = process.env.INTERNAL_API_KEY;
        if (internalKey && API_BASE && user.email) {
          try {
            await fetch(`${API_BASE}/api/auth/sync-user`, {
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
          } catch {
            // Swallowed — sync failure must never block sign-in
          }
        }
      }
      return true;
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
}

