"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { Bookmark, BookmarkCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { addToWatchlist, removeFromWatchlist, getWatchlistStatus } from "@/lib/community-api";
import { cn } from "@/lib/utils";

interface WatchlistButtonProps {
  symbol: string;
  size?: "sm" | "default";
  className?: string;
}

export function WatchlistButton({ symbol, size = "sm", className }: WatchlistButtonProps) {
  const { data: session } = useSession();
  const [inWatchlist, setInWatchlist] = useState(false);
  const [loading, setLoading] = useState(false);
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!session?.user) return;
    getWatchlistStatus(symbol)
      .then((r) => { setInWatchlist(r.in_watchlist); setChecked(true); })
      .catch(() => setChecked(true));
  }, [symbol, session]);

  if (!session?.user) {
    return (
      <Button
        variant="outline"
        size={size}
        className={cn("gap-1.5", className)}
        onClick={() => window.location.href = "/auth/signin"}
        title="Sign in to add to watchlist"
      >
        <Bookmark className="h-3.5 w-3.5" />
        Watchlist
      </Button>
    );
  }

  const toggle = async () => {
    setLoading(true);
    setError(false);
    try {
      if (inWatchlist) {
        await removeFromWatchlist(symbol);
        setInWatchlist(false);
      } else {
        await addToWatchlist(symbol);
        setInWatchlist(true);
      }
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button
      variant={inWatchlist ? "default" : "outline"}
      size={size}
      className={cn("gap-1.5", className)}
      onClick={toggle}
      disabled={loading || !checked}
      title={error ? "Unable to update watchlist. Try again." : inWatchlist ? "Remove from watchlist" : "Add to watchlist"}
    >
      {inWatchlist
        ? <BookmarkCheck className="h-3.5 w-3.5" />
        : <Bookmark className="h-3.5 w-3.5" />}
      {error ? "Try again" : inWatchlist ? "Watching" : "Watchlist"}
    </Button>
  );
}
