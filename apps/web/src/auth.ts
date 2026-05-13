import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  callbacks: {
    async jwt({ token, user, account }) {
      // On initial sign-in, embed the provider user ID into the JWT
      if (account && user) {
        token.providerUserId = account.providerAccountId;
        token.provider = account.provider;
        token.avatarUrl = user.image ?? null;
        token.displayName = user.name ?? null;
      }
      return token;
    },
    async session({ session, token }) {
      // Surface the provider user ID as the canonical user ID in the session
      session.user.id = token.providerUserId as string;
      session.user.provider = token.provider as string;
      session.user.avatarUrl = token.avatarUrl as string | null;
      return session;
    },
    async signIn({ user, account }) {
      // Sync user to the FastAPI backend (fire-and-forget; never block sign-in)
      const internalKey = process.env.INTERNAL_API_KEY;
      const apiBase =
        process.env.INTERNAL_API_BASE_URL ||
        process.env.NEXT_PUBLIC_API_BASE_URL;
      if (internalKey && apiBase && user.email) {
        try {
          await fetch(`${apiBase}/api/auth/sync-user`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Internal-Key": internalKey,
            },
            body: JSON.stringify({
              email: user.email,
              display_name: user.name ?? null,
              avatar_url: user.image ?? null,
              provider: account?.provider ?? "google",
              provider_user_id: account?.providerAccountId ?? user.id,
            }),
          });
        } catch {
          // Intentionally swallowed — user sync failure must not break auth
        }
      }
      return true;
    },
  },
  pages: {
    signIn: "/auth/signin",
    error: "/auth/error",
  },
});

// Extend next-auth types
declare module "next-auth" {
  interface Session {
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
