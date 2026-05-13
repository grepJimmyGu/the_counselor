"use client";

import { useEffect, useState } from "react";
import { useSession, signIn } from "next-auth/react";
import { ThumbsUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { getUpvotes, toggleUpvote } from "@/lib/community-api";

interface UpvoteButtonProps {
  slug: string;
}

export function UpvoteButton({ slug }: UpvoteButtonProps) {
  const { data: session } = useSession();
  const [count, setCount] = useState(0);
  const [upvoted, setUpvoted] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getUpvotes(slug, session?.user?.id)
      .then((r) => { setCount(r.upvote_count); setUpvoted(r.user_upvoted); })
      .catch(() => {});
  }, [slug, session?.user?.id]);

  const handle = async () => {
    if (!session?.user) { signIn("google"); return; }
    setLoading(true);
    try {
      const r = await toggleUpvote(slug);
      setCount(r.upvote_count);
      setUpvoted(r.user_upvoted);
    } catch {/* silent */}
    finally { setLoading(false); }
  };

  return (
    <button
      onClick={handle}
      disabled={loading}
      className={cn(
        "flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-all",
        upvoted
          ? "border-primary bg-primary/10 text-primary"
          : "border-border bg-white text-muted-foreground hover:border-primary/40 hover:text-primary"
      )}
      title={session?.user ? (upvoted ? "Remove upvote" : "Upvote this strategy") : "Sign in to upvote"}
    >
      <ThumbsUp className="h-3.5 w-3.5" />
      {count > 0 && <span>{count}</span>}
      <span>{upvoted ? "Upvoted" : "Upvote"}</span>
    </button>
  );
}
