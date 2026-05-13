"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { Bookmark, BarChart2, ArrowRight } from "lucide-react";
import type { Route } from "next";
import { getWatchlist } from "@/lib/community-api";
import type { WatchlistItem } from "@/lib/contracts";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { WatchlistButton } from "@/components/community/watchlist-button";

export default function ProfilePage() {
  const { data: session, status } = useSession();
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status !== "authenticated") return;
    getWatchlist()
      .then((r) => setWatchlist(r.symbols))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [status]);

  if (status === "loading") {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-[1200px] px-4 py-8">
          <Skeleton className="h-8 w-48 mb-4" />
          <Skeleton className="h-48 w-full" />
        </div>
      </main>
    );
  }

  if (status === "unauthenticated") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-center space-y-3">
          <p className="text-muted-foreground">You need to sign in to view your profile.</p>
          <Link href={"/auth/signin" as Route} className="text-primary hover:underline text-sm">
            Sign in →
          </Link>
        </div>
      </main>
    );
  }

  const user = session!.user;

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-[1200px] space-y-8 px-4 py-8 md:px-6 lg:px-8">

        {/* Header */}
        <div className="flex items-center gap-4 rounded-xl border border-border bg-white p-5 shadow-sm">
          <div className="h-14 w-14 overflow-hidden rounded-full border border-border bg-primary/10 flex items-center justify-center text-lg font-bold text-primary shrink-0">
            {user.image
              ? <img src={user.image} alt={user.name ?? ""} className="h-full w-full object-cover" />
              : (user.name ?? user.email ?? "?")[0].toUpperCase()}
          </div>
          <div>
            <h1 className="font-heading text-xl font-bold">{user.name ?? "User"}</h1>
            <p className="text-sm text-muted-foreground">{user.email}</p>
            <Badge variant="outline" className="mt-1 text-[10px] capitalize">{user.provider ?? "google"}</Badge>
          </div>
        </div>

        {/* Watchlist */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
            <Bookmark className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Watchlist</h2>
            {watchlist.length > 0 && (
              <Badge variant="outline" className="ml-auto font-mono text-[10px]">
                {watchlist.length}
              </Badge>
            )}
          </div>
          <div className="p-5">
            {loading ? (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)}
              </div>
            ) : watchlist.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Your watchlist is empty.{" "}
                <Link href={"/stocks" as Route} className="text-primary hover:underline">
                  Browse stocks →
                </Link>
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {watchlist.map(({ symbol, added_at }) => (
                  <div key={symbol} className="flex items-center justify-between rounded-lg border border-border bg-muted/20 px-3 py-2.5">
                    <div>
                      <Link href={`/stocks/${symbol}` as Route} className="font-mono text-sm font-bold hover:text-primary transition-colors">
                        {symbol}
                      </Link>
                      <p className="text-[10px] text-muted-foreground">
                        Added {new Date(added_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Link href={`/stocks/${symbol}` as Route}>
                        <ArrowRight className="h-3.5 w-3.5 text-muted-foreground hover:text-primary transition-colors" />
                      </Link>
                      <WatchlistButton symbol={symbol} size="sm" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* Quick links */}
        <section className="grid gap-3 sm:grid-cols-2">
          <Link
            href={"/stocks" as Route}
            className="flex items-center gap-3 rounded-xl border border-border bg-white p-4 shadow-sm hover:border-primary/30 transition-colors"
          >
            <BarChart2 className="h-5 w-5 text-primary" />
            <div>
              <div className="text-sm font-semibold">Browse Stocks</div>
              <div className="text-xs text-muted-foreground">Find stocks to add to your watchlist</div>
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground ml-auto" />
          </Link>
          <Link
            href={"/community" as Route}
            className="flex items-center gap-3 rounded-xl border border-border bg-white p-4 shadow-sm hover:border-primary/30 transition-colors"
          >
            <Bookmark className="h-5 w-5 text-purple-500" />
            <div>
              <div className="text-sm font-semibold">Community Board</div>
              <div className="text-xs text-muted-foreground">See what others are watching</div>
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground ml-auto" />
          </Link>
        </section>

      </div>
    </main>
  );
}
